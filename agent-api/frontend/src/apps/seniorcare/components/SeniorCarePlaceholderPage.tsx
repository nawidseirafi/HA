type Props = {
  eyebrow: string;
  title: string;
  description: string;
  items?: string[];
};

export function SeniorCarePlaceholderPage({ eyebrow, title, description, items = [] }: Props) {
  return (
    <section className="seniorcare-page">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{description}</p>
      {items.length > 0 && (
        <div className="seniorcare-card-grid">
          {items.map((item) => (
            <article className="seniorcare-card" key={item}>
              <span>aktiv</span>
              <h3>{item}</h3>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
