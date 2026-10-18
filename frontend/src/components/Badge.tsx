import type { Basis } from "../api";

const LABEL: Record<Basis, string> = { evidence: "Qloo data", calculated: "Calculated", interpretation: "AI interpretation" };
const HINT: Record<Basis, string> = {
  evidence: "Returned by Qloo for this audience.",
  calculated: "Worked out from the price and public income data.",
  interpretation: "The model's reasoning. Treat it as an idea to test, not a finding.",
};

export default function Badge({ basis }: { basis: Basis }) {
  return <span className={`badge b-${basis}`} title={HINT[basis]}>{LABEL[basis]}</span>;
}
