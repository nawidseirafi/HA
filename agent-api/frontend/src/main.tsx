import React from 'react';
import ReactDOM from 'react-dom/client';
import '@shared/styles/global.css';

type FrontendEdition = 'personal' | 'sentero';

const root = ReactDOM.createRoot(document.getElementById('root')!);
const buildEdition = normalizeEdition(import.meta.env.VITE_ROBOTERSTEVE_EDITION);

if (buildEdition === 'sentero') {
  import('@sentero/main').then((module) => render(module.SenteroApp));
} else if (buildEdition === 'personal') {
  import('@personal/main').then((module) => render(module.PersonalApp));
} else {
  resolveRuntimeEdition().then((edition) => (
    edition === 'sentero'
      ? import('@sentero/main').then((module) => module.SenteroApp)
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
  return value === 'sentero' || value === 'personal' ? value : null;
}
