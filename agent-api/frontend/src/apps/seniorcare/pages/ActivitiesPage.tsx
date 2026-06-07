export function ActivitiesPage() {
  return (
    <section className="seniorcare-page">
      <p className="eyebrow">Aktivitaeten</p>
      <h2>Tagesaktivitaeten</h2>
      <p className="seniorcare-page-lead">Alltagssignale werden ruhig und verstaendlich zusammengefasst.</p>
      <div className="seniorcare-panel">
        <ul className="seniorcare-timeline">
          <li><span>08:14</span> Bewegung im Wohnbereich erkannt</li>
          <li><span>09:02</span> Badezimmer genutzt</li>
          <li><span>12:05</span> Kueche genutzt</li>
          <li><span>17:30</span> Eingangstuer geoeffnet</li>
          <li><span>18:52</span> Letzte Aktivitaet im Wohnzimmer</li>
        </ul>
      </div>
    </section>
  );
}
