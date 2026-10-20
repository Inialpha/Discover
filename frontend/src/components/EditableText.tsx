import { useState } from "react";

export default function EditableText({ value, onSave, as = "p", className = "", max = 400, edited = false }: {
  value: string; onSave: (v: string) => Promise<void>; as?: "p" | "h1" | "h2"; className?: string; max?: number; edited?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const Tag = as;
  const save = async (v: string) => { setBusy(true); try { await onSave(v.trim()); setEditing(false); } finally { setBusy(false); } };
  if (!editing) {
    return (
      <div className="editable">
        <Tag className={className}>{value}</Tag>
        <button className="link small" onClick={() => { setDraft(value); setEditing(true); }}>Edit</button>
        {edited && <button className="link small" onClick={() => save("")} title="Go back to the generated text">Reset</button>}
      </div>
    );
  }
  return (
    <div className="editing">
      <textarea value={draft} maxLength={max} rows={as === "p" ? 3 : 1} onChange={(e) => setDraft(e.target.value)} autoFocus />
      <div className="row">
        <button className="primary small" disabled={busy || !draft.trim()} onClick={() => save(draft)}>Save</button>
        <button className="link small" onClick={() => setEditing(false)}>Cancel</button>
      </div>
    </div>
  );
}
