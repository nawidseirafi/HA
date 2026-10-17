import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {transform} from 'esbuild';
const {code} = await transform(await readFile(new URL('../src/apps/personal/components/agentMapLayout.ts', import.meta.url), 'utf8'), {loader: 'ts', format: 'esm'});
const {positionsForNodes} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const nodes = [{id: 'orchestrator', kind: 'orchestrator'}, ...['scheduler', 'market', 'invoices', 'vacation', 'telegram', 'mywellness', 'garden', 'music'].map(id => ({id, kind: 'agent'})), ...['messaging', 'household', 'openai', 'database', 'homeassistant'].map(id => ({id, kind: 'service'}))];
test('all current nodes have non-overlapping positions, including Music', () => {
    const positions = positionsForNodes(nodes);
    assert.equal(Object.keys(positions).length, nodes.length);
    for (const [i, a] of nodes.entries()) for (const b of nodes.slice(i + 1)) {
        const p = positions[a.id], q = positions[b.id];
        assert.ok(Math.abs(p.x - q.x) >= 250 || Math.abs(p.y - q.y) >= 110, `${a.id} overlaps ${b.id}`);
    }
    assert.ok(positions.music.y < positions.homeassistant.y);
});
test('layout is stable across API ordering and accommodates future agents', () => {
    const extended = [...nodes, {id: 'new-agent', kind: 'agent'}];
    assert.deepEqual(positionsForNodes(extended), positionsForNodes([...extended].reverse()));
    const p = positionsForNodes(extended);
    assert.notDeepEqual(p.music, p['new-agent']);
});
