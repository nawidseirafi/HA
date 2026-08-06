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

test('wall home dashboard uses the redesigned important-now layout', () => {
  assert.doesNotMatch(app, /wallSteve/);
  assert.doesNotMatch(app, /WallStevePage/);
  assert.doesNotMatch(wallDashboard, /aria-label="Steve"/);
  assert.match(wallDashboard, /data-testid="wall-home-overview"/);
  assert.match(wallDashboard, /data-testid="wall-important-now"/);
  assert.match(wallDashboard, /data-testid="wall-important-steve"/);
  assert.doesNotMatch(wallDashboard, /data-testid="wall-home-status-badge"/);
  assert.doesNotMatch(wallDashboard, /data-testid="wall-steve-thought-card"/);
  assert.match(wallDashboard, /data-testid="wall-home-status-bar"/);
  assert.match(wallCss, /\.wall-important-steve/);
  assert.doesNotMatch(wallCss, /\.wall-steve-summary-card/);
  assert.match(wallDashboard, /steveThoughtSummary\(status, items\)/);
  assert.match(wallDashboard, /Ich sehe \${items\.length} offene Punkte/);
  assert.match(wallDashboard, /Wichtig zuerst/);
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

test('live update polling is implemented for context and wall dashboard data', () => {
  assert.match(contextPage, /POLL_INTERVAL_MS = 10000/);
  assert.match(contextPage, /window\.setInterval\(\(\) => void load\(true\), POLL_INTERVAL_MS\)/);
  assert.match(wallDashboard, /void loadWallSecondaryData\(\)/);
});

test('wall home badge and important list share one derived state', () => {
  assert.match(wallDashboard, /const homeImportantState = data \? buildImportantNowState/);
  assert.doesNotMatch(wallDashboard, /function StatusBadge/);
  assert.match(wallDashboard, /important=\{homeImportantState\}/);
  assert.match(wallDashboard, /id: 'openings'/);
  assert.match(wallDashboard, /const openCount = items\.length/);
});

test('wall home includes mower and climate control surfaces', () => {
  assert.match(wallDashboard, /function WeatherCard/);
  assert.match(wallDashboard, /wall-home-climate-toggle/);
  assert.match(wallDashboard, /preferredClimateStartMode/);
  assert.match(wallDashboard, /onOpenClimateRoom/);
  assert.match(wallDashboard, /const openPrimaryClimateRoom = \(\) => \{/);
  assert.match(wallDashboard, /Haus/);
  assert.match(wallDashboard, /Keller/);
  assert.match(wallCss, /\.wall-home-weather-metrics/);
  assert.match(wallDashboard, /function BottomStatusBar/);
  assert.match(wallDashboard, /label="Mäher"/);
  assert.match(wallDashboard, /mowerIsImportant/);
});

test('wall home bottom bar keeps routine controls out of important-now', () => {
  const bottomBar = wallDashboard.match(/function BottomStatusBar[\s\S]*?function StatusBarItem/)?.[0] ?? '';
  assert.doesNotMatch(bottomBar, /label="Licht"/);
  assert.doesNotMatch(bottomBar, /label="Zugänge"/);
  assert.doesNotMatch(bottomBar, /label="System"/);
  assert.match(bottomBar, /detail=\{internetInfo\.cardDetail\}/);
  assert.match(bottomBar, /label="Vacation"/);
  assert.match(bottomBar, /onClick=\{onVacation\}/);
  assert.match(bottomBar, /label="Garage"/);
  assert.match(bottomBar, /garagePrimaryAction/);
  assert.match(bottomBar, /label="Mäher"[\s\S]*onClick=\{mower\?\.area \? onMowerRoom : undefined\}/);
  assert.match(wallDashboard, /const openMowerRoom = \(\) => \{/);
  assert.match(wallDashboard, /openRoom\(floor, room\)/);
  assert.match(wallDashboard, /id: 'garage-open'/);
  assert.match(wallDashboard, /id: 'low-batteries'/);
  assert.match(wallDashboard, /id: 'active-lights'/);
  assert.match(wallDashboard, /id: `irrigation:\$\{gardenZoneId\(zone\)\}`/);
  assert.match(wallDashboard, /gardenActiveIrrigationZones/);
  assert.match(wallDashboard, /cutting/);
  assert.match(wallDashboard, /in_operation/);
  assert.match(wallDashboard, /onBatteries/);
});

test('responsive and wall-specific styles are present', () => {
  assert.match(globalCss, /@media \(max-width: 1180px\)[\s\S]*context-card-grid/);
  assert.match(globalCss, /@media \(max-width: 720px\)[\s\S]*context-steve-card/);
  assert.match(wallCss, /\.wall-home-dashboard-grid/);
  assert.match(wallCss, /\.wall-important-card/);
  assert.match(wallCss, /@media \(max-width: 1100px\)[\s\S]*wall-home-status-bar/);
});

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
}
