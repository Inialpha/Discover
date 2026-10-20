const NAMES: Record<string, string> = {
  "24_and_younger": "<25", "25_to_29": "25–29", "30_to_34": "30–34", "35_to_44": "35–44", "45_to_54": "45–54", "55_and_older": "55+",
};

export default function AgeSkew({ index, highlight = [] }: { index: Record<string, number>; highlight?: string[] }) {
  const keys = Object.keys(NAMES).filter((k) => k in index);
  const max = Math.max(...keys.map((k) => index[k]), 0.0001);
  return (
    <div className="ageskew" role="img" aria-label="Share of the audience by age group">
      {keys.map((k) => (
        <div key={k} className={`ag ${highlight.includes(k) ? "on" : ""}`}>
          <div className="bar" style={{ height: `${Math.max(6, (index[k] / max) * 100)}%` }} />
          <span className="pct">{Math.round(index[k] * 100)}%</span>
          <span className="lbl">{NAMES[k]}</span>
        </div>
      ))}
    </div>
  );
}
