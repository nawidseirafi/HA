import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {transform} from 'esbuild';
const source = await readFile(new URL('../src/apps/personal/features/music/audioAnalyzer.ts', import.meta.url), 'utf8');
const {code} = await transform(source, {loader: 'ts', format: 'esm'});
const {createAnalyzer} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
function fixture() {
    let disconnected = 0;
    let fill = () => {};
    const analyzer = {frequencyBinCount: 1024, fftSize: 0, smoothingTimeConstant: 0, getByteFrequencyData: bins => fill(bins), disconnect: () => disconnected++};
    const context = {sampleRate: 48000, createMediaStreamSource: () => ({connect: target => assert.equal(target, analyzer), disconnect: () => disconnected++}), createAnalyser: () => analyzer};
    return {engine: createAnalyzer(context, {}), set: fn => {fill = fn;}, disconnected: () => disconnected};
}
test('silence produces zero aggregate values, no raw samples', () => {
    const {engine} = fixture();
    assert.deepEqual(engine.sample(), {bass: 0, mid: 0, high: 0, level: 0, beat: false});
});
test('bass energy remains in bass band and output is bounded', () => {
    const {engine, set} = fixture();
    set(bins => { bins.fill(0); for(let i = 2; i < 10; i++) bins[i] = 255; });
    const frame = engine.sample();
    assert.ok(frame.bass > .5);
    assert.equal(frame.mid, 0);
    assert.equal(frame.high, 0);
    assert.deepEqual(Object.keys(frame).sort(), ['bass', 'beat', 'high', 'level', 'mid']);
    for(const key of ['bass', 'mid', 'high', 'level']) assert.ok(frame[key] >= 0 && frame[key] <= 1);
});
test('cleanup disconnects audio processing nodes', () => {
    const f = fixture(); f.engine.close(); assert.equal(f.disconnected(), 2);
});
test('local spectrum responds to input without extending transmitted features', () => {
    const {engine, set} = fixture();
    engine.sample();
    assert.deepEqual(engine.spectrum(), Array(48).fill(0));
    set(bins => bins.fill(255));
    const frame = engine.sample();
    assert.deepEqual(engine.spectrum(), Array(48).fill(1));
    assert.deepEqual(Object.keys(frame).sort(), ['bass', 'beat', 'high', 'level', 'mid']);
});
