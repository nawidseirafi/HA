import {useCallback, useEffect, useRef, useState} from 'react';
import {AUTH_EXPIRED_EVENT} from '@shared/api/client';
import {createAnalyzer} from './audioAnalyzer';
import {musicControl, musicStatus, musicTicket, socketUrl, MusicStatus} from './musicClient';

export function useMusicSession() {
    const [status, setStatus] = useState<MusicStatus | null>(null);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const [microphone, setMicrophone] = useState(false);
    const cleanup = useRef<() => void>(() => {});
    const generation = useRef(0);
    const mounted = useRef(true);
    const ownSession = useRef('');
    const spectrum = useRef<number[]>([]);
    const release = useCallback(() => {
        generation.current++;
        spectrum.current = [];
        cleanup.current(); cleanup.current = () => {};
        ownSession.current = '';
        if (mounted.current) setMicrophone(false);
    }, []);
    const refresh = useCallback(async () => {
        const next = await musicStatus();
        if (!mounted.current) return;
        setStatus(next);
        if (ownSession.current && (!next.is_running || next.session !== ownSession.current)) release();
    }, [release]);
    const stop = useCallback(async () => {
        release(); setBusy(false);
        try { setStatus(await musicControl('stop')); }
        catch (e) { setError(String(e)); }
    }, [release]);
    useEffect(() => {
        mounted.current = true;
        let pending = false;
        const poll = async () => {
            if (pending) return;
            pending = true;
            try { await refresh(); } catch (e) { if (mounted.current) setError(String(e)); }
            finally { pending = false; }
        };
        void poll();
        const timer = window.setInterval(poll, 2000);
        const lost = () => { release(); };
        const hidden = () => { if (document.hidden) lost(); };
        window.addEventListener('pagehide', lost);
        window.addEventListener(AUTH_EXPIRED_EVENT, lost);
        document.addEventListener('visibilitychange', hidden);
        return () => {
            mounted.current = false; release(); window.clearInterval(timer);
            window.removeEventListener('pagehide', lost);
            window.removeEventListener(AUTH_EXPIRED_EVENT, lost);
            document.removeEventListener('visibilitychange', hidden);
        };
    }, [refresh, release]);
    const start = async () => {
        if (busy || microphone) return;
        setBusy(true); setError('');
        const attempt = ++generation.current;
        let stream: MediaStream | undefined;
        let context: AudioContext | undefined;
        let socket: WebSocket | undefined;
        let timer: number | undefined;
        let analyzer: ReturnType<typeof createAnalyzer> | undefined;
        const dispose = () => {
            if (timer) window.clearInterval(timer);
            socket?.close(); analyzer?.close(); stream?.getTracks().forEach(t => t.stop());
            if (context && context.state !== 'closed') void context.close();
        };
        cleanup.current = dispose;
        try {
            if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Bitte HTTPS ohne Zertifikatswarnung öffnen.');
            context = new AudioContext();
            await context.resume(); // Invoked directly from the explicit tap; failures enter cleanup.
            stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: false}, video: false});
            if (attempt !== generation.current) { dispose(); return; }
            const started = await musicControl('start');
            if (attempt !== generation.current) { dispose(); await musicControl('stop'); return; }
            ownSession.current = started.session;
            setStatus(started);
            const {ticket} = await musicTicket();
            if (attempt !== generation.current) { dispose(); return; }
            analyzer = createAnalyzer(context, stream);
            socket = new WebSocket(socketUrl());
            let seq = 0;
            socket.onopen = () => socket?.send(JSON.stringify({ticket, session: started.session}));
            socket.onmessage = event => {
                if (!JSON.parse(event.data).ready || timer) return;
                setMicrophone(true);
                timer = window.setInterval(() => {
                    if (context?.state !== 'running') { release(); return; }
                    if (socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < 2048) {
                        socket.send(JSON.stringify({version: 1, session: started.session, seq: seq++, ...analyzer!.sample()}));
                        spectrum.current = analyzer!.spectrum();
                    }
                }, 50);
            };
            socket.onclose = () => { if (attempt === generation.current) { release(); void refresh(); } };
            socket.onerror = () => { if (mounted.current) setError('Audioverbindung unterbrochen.'); release(); };
            stream.getAudioTracks().forEach(track => { track.onended = () => release(); });
        } catch (e) {
            dispose();
            if (ownSession.current) { ownSession.current = ''; void musicControl('stop').catch(() => {}); }
            if (mounted.current) setError(e instanceof Error ? e.message : String(e));
        } finally {
            if (mounted.current) setBusy(false);
        }
    };
    return {spectrum, status, error, setError, busy, microphone, start, stop, refresh};
}
