import type { Basis } from "../api";

const LABEL: Record<Basis, string> = { evidence: "Confirmed", calculated: "Calculated", interpretation: "Suggestion" };
const HINT: Record<Basis, string> = {
  evidence: "Confirmed by market data for this audience.",
  calculated: "Worked out from the price and public income data.",
  interpretation: "Our reasoning from the data. Not confirmed by data: treat it as an idea to test.",
};

export default function Badge({ basis }: { basis: Basis }) {
  return <span className={`badge b-${basis}`} title={HINT[basis]}>{LABEL[basis]}</span>;
}
