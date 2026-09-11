import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/apps/personal/pages/WallDashboardPage.tsx', import.meta.url), 'utf8');
const parsed = ts.createSourceFile('WallDashboardPage.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = new Set(['avg', 'normalizeArea', 'sameArea', 'isRoomTemperatureSensor', 'roomClimateValue', 'roomTemperature', 'roomHumidity']);
const functions = parsed.statements
    .filter((node) => ts.isFunctionDeclaration(node) && names.has(node.name?.text))
    .map((node) => node.getText(parsed)).join('\n');
assert.equal(parsed.statements.filter((node) => ts.isFunctionDeclaration(node) && names.has(node.name?.text)).length, names.size);
const context = vm.createContext({});
vm.runInContext(ts.transpileModule(functions, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context);
const { roomTemperature, roomHumidity } = context;

function sensor(entity_id, values, area = 'Office') {
    return { entity_id, area, state: '23.9', ...values };
}

function dashboard(temperature_sensors = [], climate = []) {
    return { temperature_sensors, climate };
}

const officeClimate = sensor('climate.office_ac', { state: 'off', current_temperature: 24, humidity: 55 });
const officeTemperature = sensor('sensor.office_air_quality_monitor_temperature', { temperature: 23.9 });
const officeHumidity = sensor('sensor.office_air_quality_monitor_humidity', { humidity: 48 });

test('Office uses its air quality monitor instead of averaging AC and outdoor measurements', () => {
    const data = dashboard([
        officeTemperature, officeHumidity,
        sensor('sensor.office_ac_outdoor_temperature', { temperature: 13.9 }),
        sensor('sensor.office_ac_outdoor_humidity', { humidity: 80 }),
    ], [officeClimate]);
    assert.equal(roomTemperature(data, 'Office'), 23.9);
    assert.equal(roomHumidity(data, 'Office'), 48);
});

test('outdoor and technical measurements are excluded by ID or friendly name', () => {
    for (const label of ['Outside Temperature', 'Außentemperatur', 'Aussengeraet', 'Outdoor unit', 'Coil temperature', 'Compressor temperature', 'Router temperature']) {
        const data = dashboard([sensor('sensor.office_measurement', { name: label, temperature: 14, humidity: 80 })], [officeClimate]);
        assert.equal(roomTemperature(data, 'Office'), 24, label);
        assert.equal(roomHumidity(data, 'Office'), 55, label);
    }
});

test('HVAC fallback is selected independently for each missing metric', () => {
    const temperatureOnly = dashboard([officeTemperature], [officeClimate]);
    assert.equal(roomTemperature(temperatureOnly, 'Office'), 23.9);
    assert.equal(roomHumidity(temperatureOnly, 'Office'), 55);
    const humidityOnly = dashboard([officeHumidity], [officeClimate]);
    assert.equal(roomTemperature(humidityOnly, 'Office'), 24);
    assert.equal(roomHumidity(humidityOnly, 'Office'), 48);
});

test('missing and invalid sensor values do not become zero or prevent fallback', () => {
    for (const value of [null, undefined, '', ' ', 'unknown', 'unavailable', NaN, Infinity, false]) {
        const data = dashboard([sensor('sensor.office_air_quality', { temperature: value, humidity: value })], [officeClimate]);
        assert.equal(roomTemperature(data, 'Office'), 24);
        assert.equal(roomHumidity(data, 'Office'), 55);
    }
});

test('unavailable entities cannot supply stale measurements', () => {
    for (const state of ['unknown', 'unavailable']) {
        const data = dashboard([{ ...officeTemperature, state }, { ...officeHumidity, state }], [officeClimate]);
        assert.equal(roomTemperature(data, 'Office'), 24);
        assert.equal(roomHumidity(data, 'Office'), 55);
        assert.equal(roomTemperature(dashboard([], [{ ...officeClimate, state }]), 'Office'), null);
    }
});

test('room matching remains isolated and multiple valid room sensors are averaged', () => {
    const data = dashboard([
        sensor('sensor.office_first', { temperature: 22, humidity: 40 }),
        sensor('sensor.office_second', { temperature: 24, humidity: 50 }, ' office '),
        sensor('sensor.kitchen', { temperature: 30, humidity: 80 }, 'Kitchen'),
    ], [officeClimate]);
    assert.equal(roomTemperature(data, 'Office'), 23);
    assert.equal(roomHumidity(data, 'Office'), 45);
    assert.equal(roomTemperature(data, 'Bedroom'), null);
    assert.equal(roomHumidity(data, 'Bedroom'), null);
});

test('zero is a valid measurement and absent data stays absent', () => {
    const data = dashboard([sensor('sensor.office_room', { temperature: 0, humidity: 0 })], [officeClimate]);
    assert.equal(roomTemperature(data, 'Office'), 0);
    assert.equal(roomHumidity(data, 'Office'), 0);
    assert.equal(roomTemperature(dashboard(), 'Office'), null);
    assert.equal(roomHumidity(dashboard(), 'Office'), null);
});
