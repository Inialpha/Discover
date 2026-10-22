import { useEffect, useRef, useState } from "react";

const CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined) || "";
const SRC = "https://accounts.google.com/gsi/client";

interface GoogleId {
  initialize(o: { client_id: string; callback: (r: { credential: string }) => void }): void;
  renderButton(el: HTMLElement, o: Record<string, unknown>): void;
}
declare global { interface Window { google?: { accounts: { id: GoogleId } } } }

function loadScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts) return resolve();
    const existing = document.querySelector(`script[src="${SRC}"]`) as HTMLScriptElement | null;
    const s = existing ?? Object.assign(document.createElement("script"), { src: SRC, async: true, defer: true });
    s.addEventListener("load", () => resolve());
    s.addEventListener("error", () => reject(new Error("Could not load Google sign-in.")));
    if (!existing) document.head.appendChild(s);
  });
}

/** "Continue with Google". Renders nothing when VITE_GOOGLE_CLIENT_ID is not set. */
export default function GoogleButton({ onCredential, onError }: { onCredential: (credential: string) => void; onError: (m: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [ok, setOk] = useState(true);
  useEffect(() => {
    if (!CLIENT_ID) return;
    let live = true;
    loadScript().then(() => {
      if (!live || !box.current || !window.google) return;
      window.google.accounts.id.initialize({ client_id: CLIENT_ID, callback: (r) => onCredential(r.credential) });
      window.google.accounts.id.renderButton(box.current, { theme: "outline", size: "large", width: 320, text: "continue_with" });
    }).catch((e: Error) => { if (live) { setOk(false); onError(e.message); } });
    return () => { live = false; };
  }, [onCredential, onError]);
  if (!CLIENT_ID || !ok) return null;
  return <div className="google"><div ref={box} /><p className="or"><span>or use your email</span></p></div>;
}
