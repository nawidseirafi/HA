import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/apps/personal/pages/WallDashboardPage.tsx', import.meta.url), 'utf8');
const parsed = ts.createSourceFile('wall.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = new Set(['outletCurrent', 'outletMeasurementSensor', 'isCurrentSensor', 'outletPower', 'outletGroupPower', 'roomPowerSensors', 'isPowerSensor', 'powerFromSensor',
    'outletPowerFromWatts', 'outletMatchTokens', 'powerSensorMatchTokens', 'normalizedEntityBase',
    'uniqueTokens', 'outletNoiseTokens', '_numericWallState', 'normalizeOutletName', 'escapeRegExp',
    'normalizeArea', 'sameArea', 'formatNumber', 'washingMachineImportantItem', 'steveThoughtSummary']);
const functions = parsed.statements.filter((node) => ts.isFunctionDeclaration(node) && names.has(node.name?.text));
assert.equal(functions.length, names.size);
const context = vm.createContext({ React: { createElement: () => null }, WashingMachine: () => null });
vm.runInContext(ts.transpileModule(functions.map((node) => node.getText(parsed)).join('\n'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React },
}).outputText, context);
const { outletCurrent, outletPower, outletGroupPower, washingMachineImportantItem, steveThoughtSummary } = context;
const room = 'Laundry Room';
const outlet = { entity_id: 'switch.laundry_room_washing_machine_plug', name: 'Laundry Room Washing Machine plug', area: room, state: 'on' };
const power = { entity_id: 'sensor.laundry_room_washing_machine_plug_power', name: 'Laundry Room Washing Machine plug Power', area: room, device_class: 'power', unit: 'W', state: '2353' };
const housePower = { ...power, entity_id: 'sensor.laundry_room_house_power', name: 'House Power', state: '2600' };

test('washing machine uses its own power sensor regardless of order', () => {
    for (const sensors of [[housePower, power], [power, housePower]]) {
        assert.equal(outletPower({ sensors }, room, outlet).watts, 2353);
    }
});

test('house power is never a fallback for a missing appliance reading', () => {
    assert.equal(outletPower({ sensors: [housePower] }, room, outlet), null);
    assert.equal(outletGroupPower({ sensors: [housePower] }, room, 'washing machine', [outlet]), null);
    assert.equal(outletPower({ sensors: [housePower, { ...power, state: 'unavailable' }] }, room, outlet), null);
});

test('voltage, current and energy are not treated as watts even with power in their names', () => {
    for (const [unit, device_class, state] of [['V', 'voltage', '238'], ['A', 'current', '9.56'], ['kWh', 'energy', '0.10']]) {
        assert.equal(outletPower({ sensors: [{ ...power, unit, device_class, state }] }, room, outlet), null);
    }
});

test('kW is converted to watts and zero remains valid', () => {
    assert.equal(outletPower({ sensors: [{ ...power, unit: 'kW', state: '2.353' }] }, room, outlet).watts, 2353);
    assert.equal(outletPower({ sensors: [{ ...power, state: '0' }] }, room, outlet).watts, 0);
});

test('fallback requires appliance identity and declines ambiguous sensors', () => {
    const alternate = { ...power, entity_id: 'sensor.meter_42', name: 'Washing Machine Leistung' };
    assert.equal(outletPower({ sensors: [housePower, alternate] }, room, outlet).watts, 2353);
    assert.equal(outletPower({ sensors: [alternate, { ...alternate, entity_id: 'sensor.meter_43' }] }, room, outlet), null);
    assert.equal(outletPower({ sensors: [{ ...alternate, area: 'Kitchen' }] }, room, outlet), null);
});

test('exact device identity works even when the sensor has no registered room', () => {
    assert.equal(outletPower({ sensors: [{ ...power, area: 'Laundry' }] }, room, outlet).watts, 2353);
});

test('washing machine shows measured watts and amps separately without losing precision', () => {
    const current = { ...power, entity_id: 'sensor.laundry_room_washing_machine_plug_current', name: 'Current', unit: 'A', device_class: 'current', state: '0.63' };
    const data = { sensors: [housePower, { ...power, state: '97' }, current] };
    assert.equal(outletPower(data, room, outlet).label, '97 W');
    assert.equal(outletCurrent(data, room, outlet), '0,63 A');
    assert.equal(outletCurrent({ sensors: [{ ...current, unit: 'mA', state: '630' }] }, room, outlet), '0,63 A');
    assert.equal(outletCurrent({ sensors: [{ ...current, state: '0' }] }, room, outlet), '0 A');
    assert.equal(outletCurrent({ sensors: [{ ...current, state: 'unavailable' }] }, room, outlet), null);
    assert.equal(outletCurrent({ sensors: [{ ...current, entity_id: 'sensor.house_current', name: 'House Current' }] }, room, outlet), null);
});

function dataWithState(state) {
    return { sensors: [{ entity_id: 'sensor.laundry_room_washing_machine_status', state }] };
}

test('running and finished washing machine appear in Steve summary alongside critical alerts', () => {
    const alert = { id: 'openings', title: '3 Zugänge geöffnet', critical: true };
    for (const [state, expected] of [['Läuft', 'Die Waschmaschine läuft gerade'], ['Beendet', 'Die Waschmaschine ist fertig']]) {
        const item = washingMachineImportantItem(dataWithState(state), null);
        assert.equal(item.title, expected);
        const summary = steveThoughtSummary(null, [alert, item]);
        assert.ok(summary.includes(alert.title));
        assert.ok(summary.includes(expected));
        assert.equal(steveThoughtSummary(null, [item]).split(expected).length, 2);
    }
});

test('current wall status overrides stale context and does not infer a cycle from plug power', () => {
    const status = { washing_machine: { state: 'running' } };
    for (const state of ['Standby', 'unknown', 'unavailable']) {
        assert.equal(washingMachineImportantItem(dataWithState(state), status), null);
    }
    assert.equal(washingMachineImportantItem({ sensors: [power] }, null), null);
    assert.equal(washingMachineImportantItem({ sensors: [] }, status).id, 'washing-machine');
});
