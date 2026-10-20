import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ProductOut } from "../api";
import EditableText from "../components/EditableText";

const when = (s: string) => new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export default function ProductPage() {
  const { id = "" } = useParams();
  const [p, setP] = useState<ProductOut | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.product(id).then(setP).catch((e) => setErr(e.message)); }, [id]);
  if (err) return <div className="page narrow"><p className="err">{err}</p><Link to="/history">Back to my analyses</Link></div>;
  if (!p) return <div className="page narrow"><p className="muted">Loading…</p></div>;
  const latest = p.runs[0];
  return (
    <div className="page narrow">
      <p className="crumb"><Link to="/history">My analyses</Link></p>
      <div className="row between">
        <EditableText as="h1" value={p.name} max={120} onSave={async (v) => { if (v) setP(await api.renameProduct(p.id, v)); }} />
        <Link className="primary" to={`/?from=${latest.id}`}>Run again with changes</Link>
      </div>
      <p className="lede">{p.runs.length} {p.runs.length === 1 ? "analysis" : "analyses"} of this product. Open one to see its personas, or run it again with a different price, place or competitors.</p>
      <ol className="runs">
        {p.runs.map((r) => (
          <li key={r.id} className="card run">
            <div className="runhead">
              <h3>Analysis {r.run_number}{r === latest ? <span className="chip">latest</span> : null}</h3>
              <span className={`st st-${r.status}`}>{r.status}</span>
            </div>
            <p className="muted small">{r.location} · {r.price.toLocaleString()} {r.currency} · {when(r.created_at)}</p>
            {r.run_number > 1 && (
              <p className="changes">{r.changes.length ? r.changes.map((c) => <span key={c} className="chg">{c}</span>) : <span className="muted">Nothing changed from the previous analysis.</span>}</p>
            )}
            {r.persona_count > 0 && <p className="muted small">{r.persona_count} personas: {r.persona_names.join(", ")}</p>}
            <div className="row">
              <Link className="primary small" to={`/analysis/${r.id}`}>View</Link>
              <Link className="ghost small" to={`/?from=${r.id}`}>Run again from this one</Link>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
