import React from 'react';
import ReactDOM from 'react-dom/client';
import '@shared/styles/global.css';

const root = ReactDOM.createRoot(document.getElementById('root')!);
import('@personal/main').then((module) => render(module.PersonalApp));

function render(RootApp: React.ComponentType) {
  root.render(
    <React.StrictMode>
      <RootApp />
    </React.StrictMode>,
  );
}
