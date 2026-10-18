import { type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export function Logo() {
  return (
    <span className="logo">
      <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
        <rect width="32" height="32" rx="9" fill="var(--teal)" />
        <circle cx="16" cy="16" r="7" fill="none" stroke="var(--sun)" strokeWidth="3" />
        <circle cx="21" cy="11" r="3" fill="var(--sun)" />
      </svg>
      Discover
    </span>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const nav = useNavigate();
  return (
    <div className="shell">
      <header className="top">
        <Link to="/" className="brand"><Logo /></Link>
        <nav>
          <NavLink to="/" end>New analysis</NavLink>
          <NavLink to="/history">My analyses</NavLink>
        </nav>
        <div className="who">
          <span>{user?.name || user?.email}</span>
          <button className="ghost" onClick={() => { signOut(); nav("/login"); }}>Sign out</button>
        </div>
      </header>
      <main>{children}</main>
      <footer className="foot">Audience data from Qloo. Messages, platforms and events are AI interpretation and are labelled as such.</footer>
    </div>
  );
}
