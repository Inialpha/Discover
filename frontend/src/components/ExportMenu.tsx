import { useState } from "react";
import { api } from "../api";

const FORMATS = [
  { id: "pptx", label: "Slides (.pptx)", hint: "One title slide, two per persona, a summary" },
  { id: "docx", label: "Document (.docx)", hint: "Full written brief" },
] as const;

export default function ExportMenu({ id, filename }: { id: string; filename: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const go = async (f: (typeof FORMATS)[number]["id"]) => {
    setBusy(f); setErr("");
    try { await api.download(id, f, filename); setOpen(false); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  return (
    <div className="export">
      <button className="primary" onClick={() => setOpen(!open)} aria-expanded={open}>Export ▾</button>
      {open && (
        <div className="menu" role="menu">
          {FORMATS.map((f) => (
            <button key={f.id} role="menuitem" onClick={() => go(f.id)} disabled={busy !== null}>
              <strong>{busy === f.id ? "Preparing…" : f.label}</strong><small>{f.hint}</small>
            </button>
          ))}
          {err && <p className="err">{err}</p>}
        </div>
      )}
    </div>
  );
}
