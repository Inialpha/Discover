import type { Basis } from "../api";

const LABEL: Record<Basis, string> = { evidence: "Backed by data", calculated: "From the numbers", interpretation: "Our suggestion" };
const HINT: Record<Basis, string> = {
  evidence: "Supported by taste and market data for this audience.",
  calculated: "Worked out from your price and public income figures.",
  interpretation: "Our reasoning from the data. Treat it as an idea to test.",
};

export default function Badge({ basis }: { basis: Basis }) {
  return <span className={`badge b-${basis}`} title={HINT[basis]}>{LABEL[basis]}</span>;
}
