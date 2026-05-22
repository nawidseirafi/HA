import type { MarketNews } from '../../api/client';

export function MarketNewsList({ news }: { news: MarketNews[] }) {
  return (
    <div className="market-news-list">
      {news.length === 0 && <p className="muted">Keine Nachrichten gespeichert.</p>}
      {news.map((item, index) => (
        <article key={`${item.title}-${index}`}>
          <div>
            <strong>{item.title}</strong>
            <small>{item.source || 'Quelle unbekannt'} · {item.published_at ? new Date(item.published_at).toLocaleString('de-DE') : 'ohne Datum'}</small>
          </div>
          <p>{item.summary}</p>
        </article>
      ))}
    </div>
  );
}
