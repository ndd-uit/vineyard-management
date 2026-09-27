export default function StatCard({ label, value, hint, tone = "plain" }: {
  label: string;
  value: string;
  hint?: string;
  tone?: "plain" | "green" | "gold";
}) {
  return (
    <article className={`stat-card stat-${tone}`}>
      <p className="stat-label">{label}</p>
      <strong className="stat-value">{value}</strong>
      {hint && <p className="stat-hint">{hint}</p>}
    </article>
  );
}
