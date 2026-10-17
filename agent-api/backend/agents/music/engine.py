"""Pure deterministic light calculation; no IO, randomness or wall clock."""
from .protocol import Frame

PROFILES = {"ambient": (30, 35, 0.35), "dynamic": (210, 140, 0.3), "party": (280, 220, 0.25)}
# Smooth gain curves retain headroom instead of clipping normal room audio.
RESPONSE = {"ambient": (1.0, 0.35, 0.0), "dynamic": (3.0, 0.55, 0.12), "party": (4.0, 0.7, 0.18)}


def render(frame: Frame, profile: str, intensity: float, previous: float = 0.0) -> tuple[dict, float]:
    base, span, transition = PROFILES[profile]
    gain, response, beat_accent = RESPONSE[profile]
    energy = min(1.0, max(0.0, 0.6 * frame.bass + 0.3 * frame.mid + 0.1 * frame.high))
    enhanced = 1 - (1 - energy) ** gain
    smooth = min(1.0, max(0.0, previous * (1 - response) + enhanced * response))
    # Beats accent brightness gently; never toggle lamps or generate strobe effects.
    accent = beat_accent if frame.beat and energy > 0.015 else 0
    brightness = round(20 + 180 * intensity * min(1, smooth + accent))
    hue = (base + span * smooth) % 360
    return {"brightness": brightness, "hs_color": [round(hue, 1), 65], "transition": transition}, smooth
