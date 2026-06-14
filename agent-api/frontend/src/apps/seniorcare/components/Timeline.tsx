type SeniorCareTimelineItem = {
  id: string;
  time: string;
  title: string;
  text: string;
  tone?: 'calm' | 'note' | 'warm';
};

export function Timeline({ items }: { items: SeniorCareTimelineItem[] }) {
  return <div className="sc-timeline">{items.map((item) => <TimelineItem item={item} key={item.id} />)}</div>;
}

export function TimelineItem({ item }: { item: SeniorCareTimelineItem }) {
  return (
    <article className={`sc-timeline-item ${item.tone || 'calm'}`}>
      <time>{item.time}</time>
      <div>
        <strong>{item.title}</strong>
        <p>{item.text}</p>
      </div>
    </article>
  );
}
