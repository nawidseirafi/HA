import React from 'react';
import ReactDOM from 'react-dom/client';
import '@shared/styles/global.css';

type FrontendEdition = 'personal' | 'seniorcare';

const root = ReactDOM.createRoot(document.getElementById('root')!);
const buildEdition = normalizeEdition(import.meta.env.VITE_ROBOTERSTEVE_EDITION);

if (buildEdition === 'seniorcare') {
  import('@seniorcare/main').then((module) => render(module.SeniorCareApp));
} else if (buildEdition === 'personal') {
  import('@personal/main').then((module) => render(module.PersonalApp));
} else {
  resolveRuntimeEdition().then((edition) => (
    edition === 'seniorcare'
      ? import('@seniorcare/main').then((module) => module.SeniorCareApp)
      : import('@personal/main').then((module) => module.PersonalApp)
  )).then(render);
}

function render(RootApp: React.ComponentType) {
  root.render(
    <React.StrictMode>
      <RootApp />
    </React.StrictMode>,
  );
}

async function resolveRuntimeEdition(): Promise<FrontendEdition> {
  try {
    const response = await fetch('/api/edition');
    if (response.ok) {
      const data = await response.json() as { name?: string };
      return normalizeEdition(data.name) ?? 'personal';
    }
  } catch {
    // Vite dev without backend should still be able to use VITE_ROBOTERSTEVE_EDITION.
  }
  return 'personal';
}

function normalizeEdition(value: unknown): FrontendEdition | null {
  return value === 'seniorcare' || value === 'personal' ? value : null;
}
