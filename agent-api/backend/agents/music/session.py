"""Single-owner session with serialized device IO and durable recovery journal."""
import logging
import errno
import socket
import httpx
import os
import re
import secrets
import threading
import time
from .engine import render
from .protocol import Frame, Settings
from .store import Store


def failure_detail(exc):
    """Only exception classes/status codes; never URLs, tokens or response bodies."""
    parts = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        label = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            label += f" HTTP {exc.response.status_code}"
        if isinstance(exc, OSError) and exc.errno is not None:
            names = {getattr(socket, key): key for key in dir(socket) if key.startswith("EAI_")}
            code = names.get(exc.errno) if isinstance(exc, socket.gaierror) else errno.errorcode.get(exc.errno)
            label += f" [{code or exc.errno}]"
        parts.append(label)
        exc = exc.__cause__ or exc.__context__
    return " → ".join(parts)


def matches(state, expected):
    if state.get("state") != expected.get("state"):
        return False
    # Off lights may retain old colors or expose null attributes. Those values
    # do not indicate a manual change while the power state is still off.
    if state.get("state") == "off":
        return True
    attrs = state.get("attributes", {})
    wanted = expected.get("attributes", {})
    if wanted.get("brightness") is not None:
        actual_brightness = attrs.get("brightness")
        if actual_brightness is None or abs(float(actual_brightness) - wanted["brightness"]) > 5:
            return False
    if wanted.get("hs_color") is not None:
        actual = attrs.get("hs_color")
        if not actual or min(abs(actual[0] - wanted["hs_color"][0]), 360 - abs(actual[0] - wanted["hs_color"][0])) > 8 or abs(actual[1] - wanted["hs_color"][1]) > 8:
            return False
    return True


class MusicSession:
    def __init__(self, backend, store=None, clock=time.monotonic):
        self.backend = backend
        self.store = store or Store()
        self.clock = clock
        self.lock = threading.RLock()
        self.input_lock = threading.Lock()
        self.stop_requested = threading.Event()
        self.settings = Settings.model_validate(self.store.read("settings", {}))
        self.journal = self.store.read("journal", {})
        self.session = ""
        self.phase = "recovery_pending" if self.journal else "idle"
        self.reason = ""
        self.frame = None
        self.last_frame = 0.0
        self.last_seq = -1
        self.last_write = 0.0
        self.last_output = float("-inf")
        self.last_player = float("-inf")
        self.index = 0
        self.smooth = 0.0
        self.released = []
        self.error = ""
        self.diagnostic = ""
        self.pending_since = {}
        self.pending_beat = False
        self.output_count = 0
        self.last_command = None

    def status(self):
        return {"status": self.phase, "is_running": self.phase in {"preparing", "running", "stopping"}, "session": self.session,
                "settings": self.settings.model_dump(), "active_lights": list(self.journal), "released": list(self.released),
                "reason": self.reason, "error": self.error, "diagnostic": self.diagnostic,
                "telemetry": {"audio_seq": self.last_seq, "commands": self.output_count,
                              "level": self.frame.level if self.frame else None,
                              "bass": self.frame.bass if self.frame else None,
                              "last_command": self.last_command}}

    def configure(self, data):
        with self.lock:
            if self.phase != "idle":
                raise ValueError("Bitte zuerst stoppen und Wiederherstellung abschließen.")
            settings = Settings.model_validate(data)
            if len(settings.lights) != len(set(settings.lights)) or any(not re.fullmatch(r"light\.[a-z0-9_]{1,150}", x) for x in settings.lights):
                raise ValueError("Ungültige Lampenauswahl.")
            if settings.player and not re.fullmatch(r"media_player\.[a-z0-9_]{1,150}", settings.player):
                raise ValueError("Ungültiger Media-Player.")
            self.store.write("settings", settings.model_dump())
            self.settings = settings
            return self.status()

    def start(self):
        with self.lock:
            if os.getenv("ROBOTERSTEVE_MONITOR_ONLY") == "1":
                raise ValueError("Beobachtungsmodus: Musiklicht ist gesperrt.")
            if self.phase != "idle":
                raise ValueError("Eine Sitzung oder Wiederherstellung ist bereits aktiv.")
            if not self.settings.lights or not self.settings.player:
                raise ValueError("Bitte Lampen und Sonos-/Media-Player auswählen.")
            self.stop_requested.clear()
            deadline = time.monotonic() + 20
            if self.backend.state(self.settings.player)["state"] != "playing":
                raise ValueError("Der gewählte Player spielt momentan keine Musik.")
            snapshot = {}
            for entity in self.settings.lights:
                if self.stop_requested.is_set() or time.monotonic() > deadline:
                    raise ValueError("Vorbereitung abgebrochen oder Home Assistant zu langsam.")
                state = self.backend.state(entity)
                attrs = state.get("attributes", {})
                if attrs.get("entity_id") or attrs.get("is_hue_group"):
                    raise ValueError("Bitte einzelne Lampen statt Lichtgruppen auswählen.")
                if state["state"] not in {"on", "off"}:
                    raise ValueError("Unbekannter Lichtzustand.")
                modes = attrs.get("supported_color_modes", [])
                if not any(x in modes for x in ("brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white")):
                    raise ValueError(f"Lampe ist nicht dimmbar: {entity}")
                snapshot[entity] = {"original": state, "expected": None, "saved_at": time.time()}
            self.store.write("journal", snapshot)  # durable before first device mutation
            self.journal = snapshot
            self.session = secrets.token_urlsafe(24)
            self.phase = "stopping" if self.stop_requested.is_set() else "preparing"
            self.last_frame = self.clock()
            self.last_seq = -1
            self.frame = None
            self.released = []
            self.error = self.reason = self.diagnostic = ""
            self.smooth = 0.0
            self.pending_since.clear()
            self.pending_beat = False
            self.output_count = 0
            self.last_command = None
            return self.status()

    def receive(self, frame: Frame):
        with self.input_lock:
            if self.stop_requested.is_set() or self.phase not in {"preparing", "running"} or frame.session != self.session:
                raise ValueError("Sitzung ist nicht aktiv.")
            if frame.seq <= self.last_seq:
                raise ValueError("Veraltete Sequenz.")
            self.last_seq = frame.seq
            self.last_frame = self.clock()
            self.frame = frame
            self.pending_beat = self.pending_beat or frame.beat

    def stop(self, reason="manual"):
        if self.phase in {"preparing", "running", "stopping"} and not self.stop_requested.is_set():
            self.reason = reason
        self.stop_requested.set()  # never wait for an HA request to inhibit new output
        if self.phase in {"preparing", "running"}:
            self.phase = "stopping"
        return self.status()

    def release(self, entities):
        # IO barrier: after returning, no in-flight music command can win over a manual one.
        with self.lock:
            for entity in entities:
                if entity in self.journal:
                    self.journal.pop(entity)
                    self.pending_since.pop(entity, None)
                    self.released.append(entity)
            self.store.write("journal", self.journal)
            if not self.journal and self.phase in {"preparing", "running"}:
                self.stop("manual_override")
            return self.status()

    def recover(self):
        with self.lock:
            if self.phase != "recovery_pending":
                raise ValueError("Keine ausstehende Wiederherstellung.")
            self.phase = "stopping"
            self.stop_requested.set()
            return self.status()

    def _pace_write(self):
        # Global write limit, not a guarantee that HA has reported the new state.
        remaining = 0.5 - (time.monotonic() - self.last_write)
        if remaining > 0:
            time.sleep(remaining)
        self.last_write = time.monotonic()

    def _restore(self):
        self.error = ""
        deadline = time.monotonic() + 15
        for entity, entry in list(self.journal.items()):
            if time.monotonic() > deadline:
                self.error = "Wiederherstellung dauert zu lange. Bitte erneut prüfen."
                break
            try:
                expected = entry.get("expected")
                # Never replay an old snapshot after a long outage or overwrite a changed lamp.
                if expected and time.time() - entry["saved_at"] < 300:
                    self._pace_write()
                    current = self.backend.state(entity)
                    if matches(current, expected) or matches(current, entry.get("previous") or expected):
                        self.backend.restore(entity, entry["original"])
                    else:
                        self.released.append(entity)
                if expected and time.time() - entry["saved_at"] >= 300:
                    self.released.append(entity)
                self.journal.pop(entity)
                self.store.write("journal", self.journal)
            except Exception:
                self.error = "Wiederherstellung unvollständig. Verbindung prüfen und erneut versuchen."
        self.phase = "recovery_pending" if self.journal else "idle"
        self.session = ""
        self.frame = None
        self.stop_requested.clear()

    def tick(self):
        with self.lock:
            if self.phase not in {"preparing", "running", "stopping"}:
                return
            now = self.clock()
            timeout = 12 if self.phase == "preparing" else 3
            if now - self.last_frame > timeout:
                self.stop("audio_timeout")
            if self.stop_requested.is_set():
                self._restore()
                return
            if now - self.last_player >= 2:
                self.last_player = now
                try:
                    if self.backend.state(self.settings.player)["state"] != "playing":
                        self.stop("player_paused")
                except Exception:
                    self.stop("player_unavailable")
                if self.stop_requested.is_set():
                    self._restore()
                    return
            frame = self.frame
            if not frame or not self.journal or now - self.last_output < 0.5:
                return
            entity = list(self.journal)[self.index % len(self.journal)]
            self.index += 1
            entry = self.journal[entity]
            operation = "Lampenstatus lesen"
            try:
                current = self.backend.state(entity)
                expected = entry.get("expected")
                reference = expected or entry["original"]
                if not matches(current, reference):
                    # A successful service call may precede the state update.
                    # Wait without sending more commands while the exact prior
                    # state is still reported. Never extend this deadline.
                    previous = entry.get("previous")
                    pending = self.pending_since.get(entity)
                    if expected and previous and pending is not None and now - pending < 2 and matches(current, previous):
                        return
                    self.diagnostic = "Lampe freigegeben: Rückmeldung weicht vom erwarteten Zustand ab."
                    self.release([entity])
                    return
                self.pending_since.pop(entity, None)
                operation = "Lichtwerte berechnen"
                # Audio arrives faster than the rate-limited light loop. Keep
                # beat events until an output consumes them, rather than losing
                # them whenever the next non-beat audio frame arrives.
                with self.input_lock:
                    frame = self.frame.model_copy(update={"beat": self.pending_beat})
                    self.pending_beat = False
                payload, self.smooth = render(frame, self.settings.profile, self.settings.intensity, self.smooth)
                modes = current.get("attributes", {}).get("supported_color_modes", [])
                if not any(x in modes for x in ("hs", "xy", "rgb", "rgbw", "rgbww")):
                    payload.pop("hs_color")
                if self.stop_requested.is_set() or self.clock() - self.last_frame > 3:
                    return
                self._pace_write()
                if self.stop_requested.is_set() or self.clock() - self.last_frame > 3:
                    return
                entry["previous"] = entry.get("expected") or entry["original"]
                entry["expected"] = {"state": "on", "attributes": {k: v for k, v in payload.items() if k != "transition"}}
                entry["saved_at"] = time.time()
                operation = "Lichtzustand sichern"
                self.store.write("journal", self.journal)
                if self.stop_requested.is_set():
                    return
                self.last_output = self.clock()
                operation = "Lampenbefehl senden"
                self.backend.apply(entity, payload)
                self.output_count += 1
                self.last_command = {"entity_id": entity, **payload}
                self.pending_since[entity] = self.clock()
                self.phase = "running" if not self.stop_requested.is_set() else "stopping"
            except Exception as exc:
                self.diagnostic = f"{operation}: {failure_detail(exc)}"
                logging.getLogger(__name__).error("Music output failed: %s", self.diagnostic)
                self.error = "Lichtsteuerung unterbrochen. Wiederherstellung wird versucht."
                self.stop("ha_error")
