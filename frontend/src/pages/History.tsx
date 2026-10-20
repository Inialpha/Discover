import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ProductItem } from "../api";

const when = (s: string) => new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export default function History() {
  const [items, setItems] = useState<ProductItem[] | null>(null);
  const [err, setErr] = useState("");
  const load = () => api.products().then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const del = async (p: ProductItem) => {
    if (confirm(`Delete "${p.name}" and its ${p.run_count} ${p.run_count === 1 ? "analysis" : "analyses"}?`)) {
      await api.removeProduct(p.id).catch((e) => setErr(e.message));
      load();
    }
  };
  return (
    <div className="page narrow">
      <h1>My analyses</h1>
      <p className="lede">Each product keeps all of its analyses together, so you can try a new price or place and compare.</p>
      {err && <p className="err">{err}</p>}
      {items === null && !err && <p className="muted">Loading…</p>}
      {items?.length === 0 && <div className="empty"><p>Nothing here yet.</p><Link className="primary" to="/">Start your first analysis</Link></div>}
      <ul className="hist">
        {items?.map((p) => (
          <li key={p.id}>
            <Link to={p.run_count === 1 ? `/analysis/${p.latest_run_id}` : `/product/${p.id}`}>
              <strong>{p.name}</strong>
              <span>{p.location} · {p.price.toLocaleString()} {p.currency} · {p.run_count} {p.run_count === 1 ? "analysis" : "analyses"} · {when(p.updated_at)}</span>
            </Link>
            <span className={`st st-${p.latest_status}`}>{p.latest_status}</span>
            <button className="link small" onClick={() => del(p)}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
