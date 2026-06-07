import React from 'react';
import ReactDOM from 'react-dom/client';
import { PersonalApp } from '@personal/main';
import { SeniorCareApp } from '@seniorcare/main';
import '@shared/styles/global.css';

const edition = import.meta.env.VITE_ROBOTERSTEVE_EDITION || 'personal';
const RootApp = edition === 'seniorcare' ? SeniorCareApp : PersonalApp;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RootApp />
  </React.StrictMode>,
);
