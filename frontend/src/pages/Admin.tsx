import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api, type AdminOverview } from "../api";
import { useAuth } from "../auth";

const when = (s: string | null) => (s ? new Date(s).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "—");
const pct = (x: number | null) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return <div className="stat"><b>{value}</b><span>{label}</span>{hint && <small>{hint}</small>}</div>;
}

export default function Admin() {
  const { user } = useAuth();
  const [d, setD] = useState<AdminOverview | null>(null);
  const [err, setErr] = useState("");
  const load = () => api.adminOverview().then(setD).catch((e) => setErr(e.message));
  useEffect(() => { if (user?.is_admin) load(); }, [user?.is_admin]);
  if (!user?.is_admin) return <Navigate to="/" replace />;
  const max = Math.max(1, ...(d?.per_day.map((x) => x.analyses) ?? [1]));
  return (
    <div className="page">
      <div className="pagehead">
        <h1>Admin</h1>
        <p className="lede">Who is using Discover and whether analyses are finishing. Counts and timings only: results are never shown here.</p>
        <button className="ghost" onClick={load}>Refresh</button>
      </div>
      {err && <p className="err">{err}</p>}
      {!d && !err && <p className="muted">Loading…</p>}
      {d && (<>
        <div className="stats">
          <Stat label="Users" value={d.totals.users} hint={`${d.totals.active_users_7d} active in 7 days`} />
          <Stat label="Analyses" value={d.totals.analyses} hint={`${d.totals.users_with_analyses} users have run one`} />
          <Stat label="Success rate" value={pct(d.totals.success_rate)} hint={`${d.totals.complete} done, ${d.totals.failed} failed, ${d.totals.running} running`} />
          <Stat label="Avg time" value={d.totals.avg_seconds == null ? "—" : `${Math.round(d.totals.avg_seconds)}s`} />
          <Stat label="Qloo calls" value={d.totals.qloo_calls_total} hint={`avg ${d.totals.avg_qloo_calls ?? "—"} per analysis`} />
          <Stat label="LLM calls / analysis" value={d.totals.avg_llm_calls ?? "—"} />
        </div>

        <h2>Last {d.per_day.length} days</h2>
        <div className="bars" role="img" aria-label="Analyses per day">
          {d.per_day.map((x) => (
            <div key={x.day} className="bar" title={`${x.day}: ${x.analyses} analyses (${x.failed} failed), ${x.signups} sign-ups`}>
              <i style={{ height: `${(x.analyses / max) * 100}%` }} className={x.failed ? "has-fail" : ""} />
              <span>{x.day.slice(8)}</span>
            </div>
          ))}
        </div>
        <p className="muted small">Bars are analyses started per day; a red tip means at least one failed. Hover for sign-ups.</p>

        <div className="two">
          <div><h2>Where</h2><ul className="plain">{d.top_locations.map((x) => <li key={x.label}>{x.label} <b>{x.count}</b></li>)}</ul></div>
          <div><h2>What</h2><ul className="plain">{d.top_categories.map((x) => <li key={x.label}>{x.label} <b>{x.count}</b></li>)}</ul></div>
        </div>

        {d.recent_failures.length > 0 && (<>
          <h2>Recent failures</h2>
          <ul className="plain">{d.recent_failures.map((r) => <li key={r.id}><b>{r.product}</b> · {r.user} · {when(r.created_at)}<br /><span className="err small">{r.error || "no message"}</span></li>)}</ul>
        </>)}

        <h2>Recent analyses</h2>
        <div className="tablewrap"><table className="data">
          <thead><tr><th>When</th><th>User</th><th>Product</th><th>Where</th><th>Status</th><th>Time</th><th>Qloo</th><th>LLM</th></tr></thead>
          <tbody>{d.recent.map((r) => (
            <tr key={r.id}>
              <td>{when(r.created_at)}</td><td>{r.user}</td><td>{r.product}{r.run > 1 ? ` #${r.run}` : ""}</td><td>{r.location}</td>
              <td className={`st-${r.status}`}>{r.status}{r.warnings ? ` (${r.warnings} warn)` : ""}</td>
              <td>{r.seconds != null ? `${Math.round(r.seconds)}s` : "—"}</td><td>{r.qloo_calls ?? "—"}</td><td>{r.llm_calls ?? "—"}</td>
            </tr>))}</tbody>
        </table></div>

        <h2>Users</h2>
        <div className="tablewrap"><table className="data">
          <thead><tr><th>Email</th><th>Name</th><th>Joined</th><th>Analyses</th><th>Last analysis</th></tr></thead>
          <tbody>{d.users.map((u) => <tr key={u.email}><td>{u.email}</td><td>{u.name}</td><td>{when(u.joined)}</td><td>{u.analyses}</td><td>{when(u.last_analysis)}</td></tr>)}</tbody>
        </table></div>
        <p className="muted small"><Link to="/">Back to the app</Link> · generated {when(d.generated_at)}</p>
      </>)}
    </div>
  );
}
