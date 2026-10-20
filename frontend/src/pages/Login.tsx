import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Logo } from "../components/Shell";
import Avatar from "../components/Avatar";
import Footer from "../components/Footer";

export default function Login() {
  const { user, signIn } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const r = mode === "login" ? await api.login(email, password) : await api.signup(email, password, name);
      signIn(r.token, r.user);
      nav(loc.state?.from || "/", { replace: true });
    } catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  };

  return (
    <>
    <div className="login">
      <section className="hero">
        <Logo />
        <h1>Know who you're really selling to.</h1>
        <p>Describe your product. Discover reads real taste data for your market and returns audience personas: who they are, what they like, what might stop them buying, and where to reach them.</p>
        <div className="faces" aria-hidden="true">
          {["f-27-3", "m-41-5", "f-52-4", "m-23-1", "f-35-2"].map((k, i) => (
            <div key={k} style={{ transform: `translateY(${i % 2 ? 14 : 0}px)` }}><Avatar avatarKey={k} size={72} /></div>
          ))}
        </div>
        <ul className="points">
          <li><b>Grounded.</b> Tastes, places and competitors are confirmed in market data, not guessed.</li>
          <li><b>Honest.</b> Every point is marked Confirmed, Calculated or Suggestion.</li>
          <li><b>Ready to use.</b> Export slides or a written brief.</li>
        </ul>
      </section>
      <form className="authcard" onSubmit={submit}>
        <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
        <div className="tabs2">
          <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Sign in</button>
          <button type="button" className={mode === "signup" ? "on" : ""} onClick={() => setMode("signup")}>Sign up</button>
        </div>
        {mode === "signup" && (
          <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
        )}
        <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
        <label>Password<input type="password" required minLength={mode === "signup" ? 8 : 1} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          {mode === "signup" && <small>At least 8 characters.</small>}
        </label>
        {err && <p className="err" role="alert">{err}</p>}
        <button className="primary wide" disabled={busy}>{busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}</button>
        <p className="fine">An account lets us keep your analyses and limit usage fairly.</p>
      </form>
    </div>
    <Footer />
    </>
  );
}
