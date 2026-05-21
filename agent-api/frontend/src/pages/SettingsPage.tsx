export function SettingsPage() {
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">System</span>
          <h1>Settings</h1>
        </div>
      </header>
      <section className="panel settings-list">
        <div><strong>API</strong><span>FastAPI auf Port 8080</span></div>
        <div><strong>Frontend</strong><span>Vite auf Port 5173, Produktion aus frontend/dist</span></div>
        <div><strong>Auth</strong><span>V1 ohne Login; API-Key kann als Middleware ergänzt werden</span></div>
        <div><strong>ELSTER</strong><span>Direktversand nicht implementiert</span></div>
      </section>
    </div>
  );
}
