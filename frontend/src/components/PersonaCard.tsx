import { Link } from "react-router-dom";
import type { Persona } from "../api";
import Avatar, { paletteOf } from "./Avatar";

export default function PersonaCard({ p, analysisId, index }: { p: Persona; analysisId: string; index: number }) {
  const pal = paletteOf(p.avatar);
  const tastes = p.tastes.slice(0, 4);
  return (
    <article className="pcard" style={{ ["--pbg" as string]: pal.bg, ["--pfig" as string]: pal.fig, ["--pink" as string]: pal.ink }}>
      <div className="band">
        <span className="rank">#{p.rank}</span>
        <Avatar avatarKey={p.avatar} size={96} alt={`Illustration of ${p.display_name}`} />
      </div>
      <div className="pbody">
        <h3>{p.display_name}</h3>
        <p className="ptitle">{p.title}</p>
        <div className="chips">
          <span className="chip">{p.age_label}</span>
          <span className="chip cap" title={p.gender_basis === "qloo" ? "From Qloo's gender skew" : "Illustrative only: not a finding"}>{p.gender}{p.gender_basis === "qloo" ? "" : " *"}</span>
          <span className={`chip conf c-${p.confidence}`}>{p.confidence} confidence</span>
        </div>
        <p className="psum">{p.summary}</p>
        {tastes.length > 0 && (
          <div className="tastes">
            {tastes.map((t) => <span key={t.name}>{t.name}</span>)}
          </div>
        )}
        <Link className="more" to={`/analysis/${analysisId}/persona/${index}`}>View more →</Link>
      </div>
    </article>
  );
}
