import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const app = read('src/apps/personal/App.tsx');
const sidebar = read('src/apps/personal/components/Sidebar.tsx');
const contextPage = read('src/apps/personal/pages/context/ContextDashboardPage.tsx');
const wallStevePage = read('src/apps/personal/pages/context/WallStevePage.tsx');
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

test('wall Steve route and wall navigation are registered', () => {
  assert.match(app, /wallSteve/);
  assert.match(app, /\/wall\/steve/);
  assert.match(wallDashboard, /aria-label="Steve"/);
  assert.match(wallStevePage, /wall-nav/);
  assert.match(wallStevePage, /wall-header/);
  assert.match(wallStevePage, /wall-header-side/);
  assert.match(wallStevePage, /className="active" type="button" aria-label="Steve"/);
});

test('context UI uses only ContextService APIs', () => {
  assert.match(apiClient, /contextStatus: \(\) => request<ContextStatus>\('\/api\/context\/status'\)/);
  assert.match(apiClient, /contextHistory: \(limit = 100\) => request<ContextHistory>/);
  assert.match(apiClient, /contextDebug: \(\) => request<ContextDebug>\('\/api\/context\/debug'\)/);
  assert.doesNotMatch(contextPage, /wallDashboard|homeassistant|callHomeAssistantService/);
  assert.doesNotMatch(wallStevePage, /wallDashboard|homeassistant|callHomeAssistantService/);
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
  assert.match(wallStevePage, /wall-steve-state error/);
});

test('live update polling is implemented for context and wall Steve', () => {
  assert.match(contextPage, /POLL_INTERVAL_MS = 10000/);
  assert.match(contextPage, /window\.setInterval\(\(\) => void load\(true\), POLL_INTERVAL_MS\)/);
  assert.match(wallStevePage, /WALL_CONTEXT_POLL_MS = 10000/);
});

test('responsive and wall-specific styles are present', () => {
  assert.match(globalCss, /@media \(max-width: 1180px\)[\s\S]*context-card-grid/);
  assert.match(globalCss, /@media \(max-width: 720px\)[\s\S]*context-steve-card/);
  assert.match(wallCss, /\.wall-steve-shell/);
  assert.match(wallCss, /@media \(max-width: 720px\)[\s\S]*wall-steve-grid/);
});

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
}
