import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Analysis, type Claim } from "../api";
import Avatar, { paletteOf } from "../components/Avatar";
import Badge from "../components/Badge";
import EditableText from "../components/EditableText";
import AgeSkew from "../components/AgeSkew";
import ExportMenu from "../components/ExportMenu";

function Claims({ items, lead }: { items: Claim[]; lead?: "angle" | "platform" | "idea" }) {
  if (!items.length) return <p className="muted">Nothing to show here.</p>;
  return (
    <ul className="claims">
      {items.map((c, i) => (
        <li key={i}>
          {lead && c[lead] && <strong>{c[lead]}</strong>}
          <p>{c.text ?? c.why}</p>
          {c.text && c.why && <p className="muted">{c.why}</p>}
          <div className="meta"><Badge basis={c.basis} />{(c.evidence?.length ?? 0) > 0 && <code>{c.evidence!.join(", ")}</code>}</div>
        </li>
      ))}
    </ul>
  );
}

export default function PersonaPage() {
  const { id = "", index = "0" } = useParams();
  const idx = Number(index);
  const [a, setA] = useState<Analysis | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get(id).then(setA).catch((e) => setErr(e.message)); }, [id]);
  const p = a?.result?.personas[idx];
  if (err) return <div className="page narrow"><p className="err">{err}</p></div>;
  if (!a) return <div className="page narrow"><p className="muted">Loading…</p></div>;
  if (!p || !a.result) return <div className="page narrow"><p>Persona not found.</p><Link to={`/analysis/${id}`}>Back</Link></div>;
  const pal = paletteOf(p.avatar);
  const save = (field: "display_name" | "title" | "summary") => async (v: string) => setA(await api.edit(id, idx, { [field]: v }));
  const edited = (f: string) => p.edited_fields?.includes(f) ?? false;
  const nextIdx = (idx + 1) % a.result.personas.length;

  return (
    <div className="page persona" style={{ ["--pbg" as string]: pal.bg, ["--pfig" as string]: pal.fig, ["--pink" as string]: pal.ink }}>
      <p className="crumb"><Link to={`/analysis/${id}`}>← {a.intake.name}</Link></p>
      <header className="phero">
        <div className="pface"><Avatar avatarKey={p.avatar} size={150} alt={`Illustration of ${p.display_name}`} /></div>
        <div className="ptext">
          <span className="rank">Persona #{p.rank}</span>
          <EditableText as="h1" value={p.display_name} max={40} onSave={save("display_name")} edited={edited("display_name")} />
          <EditableText as="h2" className="ptitle" value={p.title} max={120} onSave={save("title")} edited={edited("title")} />
          <EditableText value={p.summary} onSave={save("summary")} edited={edited("summary")} />
          <div className="chips">
            <span className="chip">{p.age_label}</span>
            <span className="chip cap">{p.gender}{p.gender_basis === "qloo" ? "" : " *"}</span>
            <span className={`chip conf c-${p.confidence}`}>{p.confidence} confidence</span>
          </div>
        </div>
        <ExportMenu id={a.id} filename={`${a.intake.name}_${p.display_name}`.replace(/[^\w-]+/g, "_")} />
      </header>

      <div className="pcols">
        <section className="card"><h3>What drives them</h3><Claims items={p.motivations} /></section>
        <section className="card"><h3>What might stop them</h3><Claims items={p.objections} /></section>
      </div>

      <section className="card">
        <h3>Messages to try</h3>
        <p className="muted small">Ideas from the model, inspired by the tastes below. Test them, don't treat them as findings.</p>
        <Claims items={p.messages} lead="angle" />
      </section>

      <div className="pcols">
        <section className="card">
          <h3>Where to reach them</h3>
          <h4>Platforms <Badge basis="interpretation" /></h4>
          <Claims items={p.platforms} lead="platform" />
          <h4>Places in {a.intake.location} <Badge basis="evidence" /></h4>
          {p.where_to_reach.length ? (
            <ul className="places">{p.where_to_reach.map((pl) => <li key={pl.place}><span>{pl.place}</span>{pl.affinity != null && <small>{Math.round(pl.affinity * 100)}% match</small>}</li>)}</ul>
          ) : <p className="muted">No places were confirmed for this group.</p>}
          {p.events.length > 0 && (<><h4>Event ideas <Badge basis="interpretation" /></h4><Claims items={p.events} lead="idea" /></>)}
        </section>
        <section className="card">
          <h3>What they like <Badge basis="evidence" /></h3>
          {p.tastes.length ? (
            <ul className="taste-list">{p.tastes.map((t) => <li key={t.name}><b>{t.name}</b><small>{t.kind.replace(/_/g, " ")}</small></li>)}</ul>
          ) : <p className="muted">No tastes returned.</p>}
          <h4>Age profile of the market</h4>
          <AgeSkew index={a.result.anchor_audience.age_index} highlight={(p as unknown as { ages?: string[] }).ages ?? []} />
        </section>
      </div>

      {p.caveats.length > 0 && (
        <section className="card caveats"><h3>Worth knowing</h3><ul>{p.caveats.map((c) => <li key={c}>{c}</li>)}</ul></section>
      )}
      <p className="muted small">* Name, gender and avatar are illustrative. Only the age and gender figures are data.</p>
      {a.result.personas.length > 1 && <p className="next"><Link to={`/analysis/${id}/persona/${nextIdx}`}>Next persona: {a.result.personas[nextIdx].display_name} →</Link></p>}
    </div>
  );
}
