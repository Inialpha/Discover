# Fixtures

| Folder | Contents | Created by |
|---|---|---|
| `scenarios/` | Deterministic scripted runs for the `mock` profile (events + normalized results). **Synthetic.** | Hand-authored |
| `recorded/` | Sanitized real provider traffic for `replay` tests. | `DISCOVER_PROFILE=record` once keys exist |
| `evals/` | Golden prompts with behavioral assertions (≥ 15). | Hand-authored, refined with `live` runs |

Rules (REQUIREMENTS §11):
- Mock data is synthetic and must be labelled as such everywhere it can surface (TST-003, UX-105).
- Mock Qloo operates at the normalized-model level; only recorded fixtures prove real wire formats (TST-012).
- Recorded fixtures are sanitized (no keys, tokens, or personal identifiers) and carry `captured_at` and API-version metadata (TST-021).
- Required scenarios: `self`, `someone_else_gift`, `group`, `community`, `business`, `compare`, `trend`, `ambiguous_entity`, `thin_results`, `provider_failure`, `timeout` (TST-010).
