import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, type Intake, type Meta } from "../api";

const EXAMPLES: { label: string; intake: Intake }[] = [
  { label: "Budget smartphone, Lagos", intake: { name: "Zip 5", description: "A budget smartphone with a large battery and a good camera for everyday use.", category: "smartphone", product_type: "smartphone", price: 40000, currency: "NGN", location: "Lagos", purchase_type: "one_off", features: [], competitors: ["Tecno", "Infinix"], max_personas: 4, age_focus: [] } },
  { label: "Toothpaste, Lagos", intake: { name: "BrightSmile", description: "A whitening toothpaste with fluoride, sold in supermarkets and pharmacies.", category: "beauty_personal_care", product_type: "toothpaste", price: 1500, currency: "NGN", location: "Lagos", purchase_type: "repeat", purchases_per_year: 12, features: [], competitors: ["Colgate", "Close-Up"], max_personas: 4, age_focus: [] } },
  { label: "Skincare, Lagos", intake: { name: "GlowSkin", description: "A vitamin C face serum for dark spots, made for deeper skin tones.", category: "beauty_personal_care", product_type: "face serum", price: 9000, currency: "NGN", location: "Lagos", purchase_type: "repeat", purchases_per_year: 4, features: [], competitors: ["The Ordinary"], max_personas: 4, age_focus: [] } },
];
const AGES = [["24_and_younger", "Under 25"], ["25_to_29", "25–29"], ["30_to_34", "30–34"], ["35_to_44", "35–44"], ["45_to_54", "45–54"], ["55_and_older", "55+"]];
const blank: Intake = { name: "", description: "", category: "", product_type: "", price: 0, currency: "USD", location: "", purchase_type: "one_off", features: [], competitors: [], max_personas: 4, age_focus: [] };
const list = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

export default function NewAnalysis() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const fromId = params.get("from");
  const [again, setAgain] = useState<{ productId: string; productName: string; runNumber: number; basedOn: string } | null>(null);
  const [separate, setSeparate] = useState(false);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [f, setF] = useState<Intake>(blank);
  const [comp, setComp] = useState("");
  const [feat, setFeat] = useState("");
  const [priceTxt, setPriceTxt] = useState("");
  const [useAgent, setUseAgent] = useState(true);
  const [discover, setDiscover] = useState(true);
  const [more, setMore] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.meta().then(setMeta).catch((e) => setErr(e.message)); }, []);
  useEffect(() => {  // "Run again with changes": start from an earlier run's details
    if (!fromId) { setAgain(null); return; }
    api.get(fromId).then((a) => {
      fill({ ...blank, ...a.intake, features: a.intake.features ?? [], competitors: a.intake.competitors ?? [], age_focus: a.intake.age_focus ?? [] });
      setUseAgent(a.options.use_agent !== false); setDiscover(a.options.discover !== false);
      if (a.product_id) setAgain({ productId: a.product_id, productName: a.product_name ?? a.intake.name, runNumber: a.run_number, basedOn: a.id });
    }).catch((e) => setErr(e.message));
  }, [fromId]);
  const currencies = useMemo(() => Array.from(new Set(["USD", "NGN", ...(meta?.markets.map((m) => m.currency) ?? [])])).sort(), [meta]);
  const set = <K extends keyof Intake>(k: K, v: Intake[K]) => setF((o) => ({ ...o, [k]: v }));
  const fill = (i: Intake) => { setF(i); setComp(i.competitors.join(", ")); setFeat(i.features.join(", ")); setPriceTxt(String(i.price)); };

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const intake: Intake = { ...f, price: Number(priceTxt), competitors: list(comp), features: list(feat), country: null };
      if (intake.purchase_type !== "repeat") delete intake.purchases_per_year;
      const link = again && !separate ? { product_id: again.productId, based_on: again.basedOn } : undefined;
      const r = await api.create(intake, { use_agent: useAgent, discover }, link);
      nav(`/analysis/${r.id}`);
    } catch (e2) { setErr((e2 as Error).message); setBusy(false); }
  };

  return (
    <div className="page">
      <div className="pagehead">
        <h1>{again ? "Try something different" : "Who is your product for?"}</h1>
        <p className="lede">{again ? "Change what you want to test, such as the price, the place or the competitors, then run it again." : "Tell us what you sell and where. It takes about 3 to 4 minutes to read the market, and you can leave the page while it works."}</p>
      </div>
      {again && (
        <div className="again card">
          <p>{separate ? <>This will be saved as a <strong>new product</strong>.</> : <>This will be added to <strong>{again.productName}</strong> as a new analysis, started from analysis {again.runNumber}.</>}</p>
          <label className="check"><input type="checkbox" checked={separate} onChange={(e) => setSeparate(e.target.checked)} />Save it as a separate product instead</label>
        </div>
      )}
      {!again && <div className="examples">
        <span>Try an example:</span>
        {EXAMPLES.map((x) => <button key={x.label} type="button" className="pill" onClick={() => fill(x.intake)}>{x.label}</button>)}
      </div>}
      <form className="intake" onSubmit={submit}>
        <fieldset>
          <legend>1 · The product</legend>
          <label>Product name<input required maxLength={120} value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. BrightSmile whitening toothpaste" /></label>
          <label>What is it, and who is it made for?
            <textarea required minLength={10} maxLength={1000} rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} placeholder="A sentence or two: what it does, what makes it different." />
          </label>
          <div className="grid2">
            <label>Category
              <select required value={f.category} onChange={(e) => set("category", e.target.value)}>
                <option value="" disabled>Choose…</option>
                {meta?.categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
            </label>
            <label>What exactly is it? <small>(a few words)</small><input maxLength={80} value={f.product_type} onChange={(e) => set("product_type", e.target.value)} placeholder="e.g. toothpaste, face serum" /></label>
          </div>
        </fieldset>
        <fieldset>
          <legend>2 · Price and place</legend>
          <div className="grid3">
            <label>Price<input required inputMode="decimal" value={priceTxt} onChange={(e) => setPriceTxt(e.target.value)} placeholder="0" /></label>
            <label>Currency<select value={f.currency} onChange={(e) => set("currency", e.target.value)}>{currencies.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label>Bought<select value={f.purchase_type} onChange={(e) => set("purchase_type", e.target.value)}>{meta?.purchase_types.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
          </div>
          {f.purchase_type === "repeat" && (
            <label>Times per year<input type="number" min={1} max={365} value={f.purchases_per_year ?? ""} onChange={(e) => set("purchases_per_year", e.target.value ? Number(e.target.value) : null)} /></label>
          )}
          <label>City or area<input required maxLength={120} value={f.location} onChange={(e) => set("location", e.target.value)} placeholder="e.g. Lagos" /></label>
        </fieldset>
        <fieldset>
          <legend>3 · The competition <small>(optional)</small></legend>
          <label>Competitor brands you know of
            <input value={comp} onChange={(e) => setComp(e.target.value)} placeholder="Comma separated, e.g. Colgate, Close-Up" />
            <small>We also look for competitors and alternatives in market data, and only keep the ones it confirms.</small>
          </label>
        </fieldset>
        <button type="button" className="link" onClick={() => setMore(!more)}>{more ? "Hide" : "Show"} more options</button>
        {more && (
          <fieldset className="adv">
            <legend>More options</legend>
            <label>Key features <small>(comma separated)</small><input value={feat} onChange={(e) => setFeat(e.target.value)} placeholder="e.g. long battery, fluoride" /></label>
            <div className="grid3">
              <label>Personas<input type="number" min={1} max={10} value={f.max_personas} onChange={(e) => set("max_personas", Number(e.target.value))} /></label>
              <label>Focus on gender<select value={f.gender_focus ?? ""} onChange={(e) => set("gender_focus", e.target.value || null)}><option value="">Any</option><option value="female">Women</option><option value="male">Men</option></select></label>
            </div>
            <div className="ages">Focus on ages
              {AGES.map(([k, l]) => (
                <label key={k} className="check"><input type="checkbox" checked={f.age_focus.includes(k)} onChange={(e) => set("age_focus", e.target.checked ? [...f.age_focus, k] : f.age_focus.filter((x) => x !== k))} />{l}</label>
              ))}
            </div>
            <label className="check"><input type="checkbox" checked={useAgent} onChange={(e) => setUseAgent(e.target.checked)} />Explore the market in more depth first <small>(slower, can find more)</small></label>
            <label className="check"><input type="checkbox" checked={discover} onChange={(e) => setDiscover(e.target.checked)} />Look for more competitors than I listed</label>
          </fieldset>
        )}
        {err && <p className="err" role="alert">{err}</p>}
        <div className="submitrow">
          <button className="primary big" disabled={busy || !meta}>{busy ? "Starting…" : again ? "Find my audience again" : "Find my audience"}</button>
        </div>
      </form>
    </div>
  );
}
