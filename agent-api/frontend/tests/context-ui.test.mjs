import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const app = read('src/apps/personal/App.tsx');
const sidebar = read('src/apps/personal/components/Sidebar.tsx');
const contextPage = read('src/apps/personal/pages/context/ContextDashboardPage.tsx');
const apiClient = read('src/shared/api/client.ts');
const globalCss = read('src/shared/styles/global.css');
const wallCss = read('src/shared/styles/wall.css');
const wallDashboard = read('src/apps/personal/pages/WallDashboardPage.tsx');

test('context route and navigation are registered', () => {
  assert.match(app, /contextDashboard/);
  assert.match(app, /\/context/);
  assert.match(sidebar, /Context/);
  assert.match(sidebar, /BrainCircuit/);
});

test('wall Steve thought is integrated into the wall dashboard', () => {
  assert.doesNotMatch(app, /wallSteve/);
  assert.doesNotMatch(app, /WallStevePage/);
  assert.doesNotMatch(wallDashboard, /aria-label="Steve"/);
  assert.match(wallDashboard, /data-testid="wall-steve-thought-card"/);
  assert.match(wallDashboard, /api\.contextStatus\(\)/);
  assert.match(wallDashboard, /Steve denkt \.\.\./);
});

test('context UI uses only ContextService APIs', () => {
  assert.match(apiClient, /contextStatus: \(\) => request<ContextStatus>\('\/api\/context\/status'\)/);
  assert.match(apiClient, /contextHistory: \(limit = 100\) => request<ContextHistory>/);
  assert.match(apiClient, /contextDebug: \(\) => request<ContextDebug>\('\/api\/context\/debug'\)/);
  assert.doesNotMatch(contextPage, /wallDashboard|homeassistant|callHomeAssistantService/);
  assert.match(wallDashboard, /api\.contextStatus\(\)/);
});

test('rendering surfaces cover status, timeline, history, confidence and debug', () => {
  for (const id of [
    'context-page',
    'steve-thinking',
    'context-status-cards',
    'context-live-state',
    'context-explanations',
    'context-confidence',
    'context-timeline',
    'context-history',
    'context-debug',
  ]) {
    assert.match(contextPage, new RegExp(`data-testid="${id}"`));
  }
});

test('loading and error states are present', () => {
  assert.match(contextPage, /data-testid="context-loading"/);
  assert.match(contextPage, /data-testid="context-error"/);
  assert.match(wallDashboard, /Steve liest den aktuellen Kontext/);
});

test('live update polling is implemented for context and wall dashboard Steve card', () => {
  assert.match(contextPage, /POLL_INTERVAL_MS = 10000/);
  assert.match(contextPage, /window\.setInterval\(\(\) => void load\(true\), POLL_INTERVAL_MS\)/);
  assert.match(wallDashboard, /void loadWallSecondaryData\(\)/);
});

test('responsive and wall-specific styles are present', () => {
  assert.match(globalCss, /@media \(max-width: 1180px\)[\s\S]*context-card-grid/);
  assert.match(globalCss, /@media \(max-width: 720px\)[\s\S]*context-steve-card/);
  assert.match(wallCss, /\.wall-steve-summary-card/);
  assert.match(wallCss, /@media \(max-width: 720px\)[\s\S]*wall-steve-summary-card/);
});

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
}
