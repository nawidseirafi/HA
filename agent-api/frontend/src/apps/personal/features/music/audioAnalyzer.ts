/** Audio never leaves this analyser; only five aggregate features are returned. */
export function createAnalyzer(context: AudioContext, stream: MediaStream) {
    const source = context.createMediaStreamSource(stream);
    const analyzer = context.createAnalyser();
    analyzer.fftSize = 2048;
    analyzer.smoothingTimeConstant = .65;
    source.connect(analyzer); // Intentionally no connection to speakers.
    const bins = new Uint8Array(analyzer.frequencyBinCount);
    let baseline = .1;
    let lastBeat = 0;
    const band = (lo: number, hi: number) => {
        const step = context.sampleRate / analyzer.fftSize;
        const begin = Math.max(1, Math.floor(lo / step));
        const end = Math.min(bins.length, Math.ceil(hi / step));
        let sum = 0;
        for (let i = begin; i < end; i++) sum += bins[i] / 255;
        return sum / Math.max(1, end - begin);
    };
    return {
        sample() {
            analyzer.getByteFrequencyData(bins);
            const bass = band(40, 250), mid = band(250, 2000), high = band(2000, 12000);
            const level = (bass + mid + high) / 3;
            const now = performance.now();
            const beat = bass > Math.max(.15, baseline * 1.35) && now - lastBeat > 300;
            baseline = .96 * baseline + .04 * bass;
            if (beat) lastBeat = now;
            return {bass, mid, high, level, beat};
        },
        spectrum() {
            // Local visualization only: never included in the WebSocket payload.
            return Array.from({length: 48}, (_, i) => {
                const lo = 40 * Math.pow(300, i / 48);
                return band(lo, 40 * Math.pow(300, (i + 1) / 48));
            });
        },
        close() { source.disconnect(); analyzer.disconnect(); },
    };
}
