import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ListItem } from "../api";

const when = (s: string) => new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export default function History() {
  const [items, setItems] = useState<ListItem[] | null>(null);
  const [err, setErr] = useState("");
  const load = () => api.list().then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const del = async (id: string) => { if (confirm("Delete this analysis?")) { await api.remove(id).catch((e) => setErr(e.message)); load(); } };
  return (
    <div className="page narrow">
      <h1>My analyses</h1>
      {err && <p className="err">{err}</p>}
      {items === null && !err && <p className="muted">Loading…</p>}
      {items?.length === 0 && <div className="empty"><p>Nothing here yet.</p><Link className="primary" to="/">Start your first analysis</Link></div>}
      <ul className="hist">
        {items?.map((a) => (
          <li key={a.id}>
            <Link to={`/analysis/${a.id}`}>
              <strong>{a.product}</strong>
              <span>{a.location} · {a.status === "complete" ? `${a.persona_count} personas` : a.status} · {when(a.created_at)}</span>
            </Link>
            <span className={`st st-${a.status}`}>{a.status}</span>
            <button className="link small" onClick={() => del(a.id)}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
