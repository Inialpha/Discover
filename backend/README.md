# Discover backend — Business workflow CLI

Runs the **Discover for Business** (market discovery) workflow end to end from the command line and saves
every request, raw response, evidence item and report into one run folder. Spec: `REQUIREMENTS.md` §1a, §11.3.

## Install
```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Python 3.10+
pip install -e ".[dev]"
cp ../.env.example .env                                # then fill in keys
```
`.env` (read from the current directory): `QLOO_API_KEY`, `QLOO_BASE_URL` (default `https://hackathon.api.qloo.com`),
optional LLM: `LLM_API_KEY`, `LLM_BASE_URL` (e.g. `https://api.openai.com/v1`), `LLM_MODEL`.

## Try it offline first (synthetic data, no keys)
```bash
discover run "what do women from 25 to 35 in Lagos like, what media do they like?" --mock
```

## Real runs
```bash
discover probe                                         # key/base-URL check (2 calls)
discover run "what do women from 25 to 35 in Lagos like? what media do they like?"
discover run "Advise on advertising for my sneaker brand" --own-brand "Nike" --brand Adidas \
    --keyword streetwear --gender women --age 25-35 --location Lagos
discover run "..." --segment "Young women:female:25-35" --segment "Young men:male:25-35" --location Lagos
discover run "..." --dry-run        # write the planned requests, call nothing
discover run "..." --steps resolve,taste --max-calls 20
```
Experiment: `--location-mode signal|filter|both` changes how the location is sent (default tries a sensible order per call).
The LLM only sees a compact view of the evidence (`LLM_MAX_INPUT_CHARS`, default 9000); full data stays in `03_evidence.json`.

Without LLM settings the planner is heuristic and the report is a plain template. With them, an LLM plans the
brief and writes the evidence-cited report (claims citing no valid evidence are removed).

## Which markets does Qloo cover well?
```bash
discover coverage --location Lagos --location "New York" --location London --location Mumbai --location Tokyo \
    --gender women --age 25-35
```
Writes `coverage.md/json`: per city, how local the results are (share of movies/TV/brands whose own metadata names the market's country),
place/heatmap counts, and overlap between cities. Send the zip back; we choose demo markets from this.
Multi-market questions: `discover run "what content should I create for women 25-35?" --location Tokyo --location "New York"`.

## Run folder (`runs/<timestamp>_<slug>/`, plus a `.zip`)
| File | Content |
|---|---|
| `00_input.json`, `01_brief.json` | options and the structured brief (segments + age buckets) |
| `qloo/NNN_<step>_<label>_vN.json` | **every HTTP attempt**: params, status, raw response, which variant |
| `llm/*.json` | planner / synthesis exchanges |
| `02_resolved.json`, `03_evidence.json` | resolved entities/tags; evidence items E001… (failures included) |
| `04_report.md/.json` | the report |
| `calls.jsonl`, `99_run_summary.json` | per-call log; status, variants that worked, failures |

API keys are never written. **Send back the `.zip`** (and tell me what looks wrong); `99_run_summary.json`
lists which parameter spellings worked.

## Correcting mistakes
Unverified spellings (location param placement, `types` vs `filter.type`, tag query name, age buckets,
compare params) live in `discover/qloo/calls.py` and `discover/qloo/demographics.py`. Response parsing is in
`discover/qloo/normalize.py`. Exit codes: 0 ok, 1 partial, 2 all Qloo calls failed, 3 config/auth.

## Tests
`pytest` (offline; uses a mock transport and `entity_examples/`).
