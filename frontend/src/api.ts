// Typed client for the Discover API. The token lives in localStorage (wrapped: it can be unavailable).
export const API_URL = ((import.meta.env.VITE_API_URL as string | undefined) || "").replace(/\/$/, "");

const KEY = "discover.token";
export const tokenStore = {
  get(): string | null { try { return localStorage.getItem(KEY); } catch { return null; } },
  set(t: string) { try { localStorage.setItem(KEY, t); } catch { /* ignore */ } },
  clear() { try { localStorage.removeItem(KEY); } catch { /* ignore */ } },
};

export type Basis = "evidence" | "calculated" | "interpretation";
export interface User { id: string; email: string; name: string }
export interface Meta {
  categories: { id: string; label: string; profile: string }[];
  purchase_types: { id: string; label: string }[];
  markets: { iso2: string; name: string; currency: string }[];
  [k: string]: unknown;
}
export interface Intake {
  name: string; description: string; category: string; price: number; currency: string; location: string;
  purchase_type: string; purchases_per_year?: number | null; country?: string | null; features: string[];
  competitors: string[]; product_type: string; max_personas: number; gender_focus?: string | null; age_focus: string[];
}
export interface Claim { text?: string; angle?: string; platform?: string; idea?: string; why?: string; basis: Basis; evidence?: string[] }
export interface Taste { name: string; kind: string; basis: Basis; evidence: string[] }
export interface Place { place: string; affinity?: number; basis: Basis; evidence: string[] }
export interface Persona {
  rank: number; segment_id: string; name: string; display_name: string; name_basis: string; gender: "female" | "male" | "neutral" | string;
  gender_basis: string; age_label: string; avatar: string; title: string; summary: string; headline: string; who: string;
  motivations: Claim[]; objections: Claim[]; messages: Claim[]; platforms: Claim[]; events: Claim[];
  tastes: Taste[]; where_to_reach: Place[]; caveats: string[]; source: string; score: number; confidence: string;
  edited_fields?: string[];
}
export interface Result {
  synthetic: boolean; personas: Persona[]; evidence_notes: string[]; attribution: string[];
  affordability: { tier: string; country_name: string; local_currency: string; local_price: number; ratio: number | null; [k: string]: unknown };
  anchor_audience: { anchors: { name: string; source: string; query: string }[]; age_index: Record<string, number>; gender_index: Record<string, number> };
  agent: { goals?: string[]; steps?: number } | null;
  scoring: { notes: string[] };
}
export interface Analysis {
  id: string; title: string; status: "queued" | "running" | "complete" | "failed"; intake: Intake; options: Record<string, unknown>;
  result: Result | null; summary: Record<string, unknown> | null; error: string | null; created_at: string; finished_at: string | null;
}
export interface ListItem { id: string; title: string; status: Analysis["status"]; product: string; location: string; persona_count: number; created_at: string; finished_at: string | null }
export interface Ev { seq: number; stage: string; message: string; data: Record<string, unknown>; created_at: string }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function readable(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      const loc = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== "body" && x !== "intake").join(" › ") : "";
      return `${loc ? loc + ": " : ""}${d?.msg ?? d}`;
    }).join("; ");
  }
  return "Something went wrong.";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const t = tokenStore.get();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try { res = await fetch(API_URL + path, { ...init, headers }); }
  catch { throw new ApiError(0, "Can't reach the server. If this is the first request in a while the server may be waking up, so try again in a moment."); }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { /* not json */ }
  if (!res.ok) throw new ApiError(res.status, readable(body?.detail ?? res.statusText));
  return body as T;
}

export const api = {
  meta: () => call<Meta>("/api/meta"),
  signup: (email: string, password: string, name: string) => call<{ token: string; user: User }>("/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password, name }) }),
  login: (email: string, password: string) => call<{ token: string; user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => call<User>("/api/auth/me"),
  create: (intake: Intake, options: { use_agent: boolean; discover: boolean }) => call<{ id: string; status: string }>("/api/analyses", { method: "POST", body: JSON.stringify({ intake, options }) }),
  list: () => call<ListItem[]>("/api/analyses"),
  get: (id: string) => call<Analysis>(`/api/analyses/${id}`),
  events: (id: string, since: number) => call<{ status: Analysis["status"]; events: Ev[] }>(`/api/analyses/${id}/events?since=${since}`),
  edit: (id: string, index: number, body: { display_name?: string; title?: string; summary?: string }) => call<Analysis>(`/api/analyses/${id}/personas/${index}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => call<void>(`/api/analyses/${id}`, { method: "DELETE" }),
  async download(id: string, format: "pptx" | "docx" | "md" | "json", filename: string) {
    const headers: Record<string, string> = {};
    const t = tokenStore.get();
    if (t) headers.Authorization = `Bearer ${t}`;
    const res = await fetch(`${API_URL}/api/analyses/${id}/export?format=${format}`, { headers });
    if (!res.ok) throw new ApiError(res.status, "Export failed.");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = `${filename}.${format}`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  },
};
