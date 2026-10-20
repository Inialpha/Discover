import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Analysis as A, type Ev, type Market, type MarketRow } from "../api";
import Badge from "../components/Badge";
import PersonaCard from "../components/PersonaCard";
import ExportMenu from "../components/ExportMenu";
import AgeSkew from "../components/AgeSkew";

const STAGES: [string, string][] = [
  ["affordability", "Checking what the price means locally"],
  ["agent", "Exploring the market in depth"],
  ["competitors", "Confirming competitors"],
  ["market", "Mapping alternatives and the wider market"],
  ["audience", "Reading who buys from them"],
  ["segments", "Splitting the audience"],
  ["personas", "Writing the personas"],
  ["report", "Putting it together"],
];

function Progress({ events, failed }: { events: Ev[]; failed: boolean }) {
  const seen = new Set(events.map((e) => e.stage));
  const last = events[events.length - 1];
  const currentIdx = STAGES.reduce((acc, [s], i) => (seen.has(s) ? i : acc), -1);
  return (
    <div className="progress card">
      <h2>{failed ? "This analysis stopped" : "Reading the market…"}</h2>
      <ol className="steps">
        {STAGES.map(([s, label], i) => {
          const skipped = i < currentIdx && !seen.has(s);
          if (skipped) return null;
          const state = failed && i === currentIdx ? "fail" : i < currentIdx ? "done" : i === currentIdx ? "now" : "todo";
          return <li key={s} className={state}><span className="dot" />{label}</li>;
        })}
      </ol>
      {last && !failed && <p className="live" aria-live="polite">{last.message}</p>}
      {!failed && <p className="muted small">You can leave this page. Your analysis keeps running and will be in My analyses.</p>}
    </div>
  );
}

function MarketCard({ m }: { m: Market }) {
  const groups: [string, MarketRow[]][] = [
    ["Direct competitors", m.tiers.direct], ["What customers use instead", m.tiers.alternative], ["The wider sector", m.tiers.sector],
  ];
  const any = groups.some(([, rows]) => rows.length);
  return (
    <section className="card market">
      <h2>The market around your product</h2>
      {m.need && <p className="need">The problem your customers are solving: <strong>{m.need}</strong></p>}
      {any ? (
        <div className="tiers">
          {groups.map(([title, rows]) => rows.length > 0 && (
            <div key={title}>
              <h4>{title} <Badge basis="evidence" /></h4>
              {rows.map((row) => (
                <p key={row.label}><span className="muted">{row.label}</span><br />{row.brands.map((b) => b.name).join(", ")}</p>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <p><span className="badge b-notconfirmed">Not confirmed</span> We could not confirm competing or alternative brands for this market, so the personas rest on income data and the audience profile only.</p>
      )}
      {m.alternatives_audience && (
        <div>
          <h4>Who buys the alternatives <Badge basis="evidence" /></h4>
          <p className="muted small">People using {m.alternatives_audience.brands.slice(0, 4).join(", ")} today. Reach them with a message that shows how your product solves the same problem better.</p>
          <AgeSkew index={m.alternatives_audience.age_index} />
        </div>
      )}
    </section>
  );
}

export default function Analysis() {
  const { id = "" } = useParams();
  const [a, setA] = useState<A | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [err, setErr] = useState("");
  const since = useRef(0);

  const load = useCallback(() => api.get(id).then(setA).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { since.current = 0; setEvents([]); setA(null); load(); }, [id, load]);

  const active = a && (a.status === "queued" || a.status === "running");
  useEffect(() => {
    if (!active) return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await api.events(id, since.current);
        if (stop) return;
        if (r.events.length) { since.current = r.events[r.events.length - 1].seq; setEvents((o) => [...o, ...r.events]); }
        if (r.status !== "queued" && r.status !== "running") { load(); return; }
      } catch { /* transient: keep polling */ }
      if (!stop) setTimeout(tick, 2000);
    };
    tick();
    return () => { stop = true; };
  }, [active, id, load]);

  if (err) return <div className="page narrow"><p className="err">{err}</p><Link to="/history">Back to my analyses</Link></div>;
  if (!a) return <div className="page narrow"><p className="muted">Loading…</p></div>;
  const r = a.result;

  return (
    <div className="page">
      <div className="pagehead row between">
        <div>
          <p className="crumb">
            <Link to="/history">My analyses</Link>
            {a.product_id && <> / <Link to={`/product/${a.product_id}`}>{a.product_name}</Link> / Analysis {a.run_number} of {a.run_count}</>}
          </p>
          <h1>{a.intake.name}</h1>
          <p className="lede">{a.intake.location} · {a.intake.price.toLocaleString()} {a.intake.currency}</p>
          {a.run_number > 1 && a.changes.length > 0 && <p className="changes">{a.changes.map((c) => <span key={c} className="chg">{c}</span>)}</p>}
        </div>
        {(r || a.status === "failed") && (
          <div className="row">
            <Link className="ghost" to={`/?from=${a.id}`}>Run again with changes</Link>
            {r && <ExportMenu id={a.id} filename={a.intake.name.replace(/[^\w-]+/g, "_")} />}
          </div>
        )}
      </div>

      {(active || a.status === "failed") && <Progress events={events} failed={a.status === "failed"} />}
      {a.status === "failed" && (
        <div className="card errcard"><p>{a.error || "Something went wrong."}</p><Link className="primary" to="/">Try again</Link></div>
      )}

      {r && (
        <>
          {r.synthetic && <p className="note">Demo data: this analysis ran on built-in sample data, not live market data.</p>}
          <section className="overview card">
            <div>
              <h2>The market at a glance</h2>
              <p>
                At {r.affordability.local_price.toLocaleString()} {r.affordability.local_currency} in {r.affordability.country_name}, this reads as a{" "}
                <strong>{r.affordability.tier}</strong> price{r.affordability.ratio != null && <> ({(r.affordability.ratio * 100).toFixed(1)}% of average yearly income)</>}.
              </p>
              {r.anchor_audience.anchors.length > 0 && (
                <p className="muted">Audience read from the buyers of: {r.anchor_audience.anchors.slice(0, 8).map((x) => x.name).join(", ")}.</p>
              )}
              {r.evidence_notes.map((n) => <p key={n} className="muted small">{n}</p>)}
            </div>
            <div>
              <h3>Who buys from competitors</h3>
              <AgeSkew index={r.anchor_audience.age_index} />
            </div>
          </section>
          {r.market && <MarketCard m={r.market} />}
          <h2 className="sect">Your audience personas</h2>
          <div className="pgrid">
            {r.personas.map((p, i) => <PersonaCard key={p.segment_id + i} p={p} analysisId={a.id} index={i} />)}
          </div>
          <p className="muted small">* Name, gender and avatar are illustrative. Only the age and gender figures are data.</p>
          {r.attribution.length > 0 && <p className="muted small">Sources: market data by Qloo; {r.attribution.join("; ")}.</p>}
        </>
      )}
    </div>
  );
}
