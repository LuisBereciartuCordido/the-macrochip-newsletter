# The Macrochip

[![Tests](https://github.com/LuisBereciartuCordido/the-macrochip-newsletter/actions/workflows/tests.yml/badge.svg)](https://github.com/LuisBereciartuCordido/the-macrochip-newsletter/actions/workflows/tests.yml)

A weekly newsletter in Spanish explaining the global economic and geopolitical context driving the markets — for someone with no background in economics, never giving investment advice.

The product (the newsletter itself) is in Spanish; this README, the code, and all comments are in English.

Every Sunday, a Claude Code scheduled task downloads hard data from official sources, researches and writes the week's report, verifies it against its own sources by re-reading them (not from memory), validates it with deterministic rules, and creates a **draft** — never sends it — in Buttondown. A human reviews it and sends it.

## The pipeline

```
fetch_data.py → datos.json
      ↓
[writing + verification — require judgment, done by Claude]
      ↓
validate.py → valid informe.json, or stops without publishing
      ↓
render.py → informe.md (email) + transparencia.md (internal use)
      ↓
publish.py → draft in Buttondown
```

The line is deliberate: anything that can be decided by a fixed rule is Python code with tests (downloading, validation, rendering, publishing). Anything that needs real judgment — what counts as news, whether a source says what it appears to say, whether a figure checks out — is done by Claude inside the scheduled task, following versioned instructions in the repo, not code trying to simulate judgment.

A single `informe.schema.json` is the source of truth: the email, the AI context package carrying every figure, and the transparency summary all come from the same JSON — never written separately.

## Engineering decisions

**Where there's no official source, the risk gets documented instead of pretended away.** ECB, Eurostat, INE and FRED cover interest rates and inflation with no friction. For the Nikkei 225, gold and the MSCI indices there's no free official API; Yahoo Finance's unofficial endpoint is used instead, with the risk explicitly noted instead of ignored, and no speculative backup source for a failure that hasn't happened — if it does, the pipeline stops without publishing, same as any other failure.

**Verification is a real second pass, not a formality.** After writing, a separate session re-reads every source from scratch — without trusting what the writing step remembered — and checks every figure against the hard data before signing off on the report.

**Transparency is generated, but not sent.** The report records which sources were used, which were discarded, and what the verifier corrected. But showing that list of corrections to every subscriber signals "this has flaws" rather than reliability, so that section is written separately, for internal use only, never in the email.

**Unit tests + one real end-to-end run.** Besides unit tests (validation logic, data parsing, mocked HTTP calls), the pipeline was tested in full with real data and a real draft created in Buttondown — that's what surfaces the integration failures a single isolated test never sees.

## Architecture

```
config/        # Everything editable without touching code: modules, sources, markets, style
prompts/        # Writer, verifier, style — the versioned judgment
schema/          # informe.schema.json, the core data contract
scripts/          # Thin CLIs
src/briefing/      # The real logic, with tests
data/AAAA-Sww/      # One folder per week: data, draft, report, email, log
```

The project's full conventions — why each decision was made, what was ruled out and why — live in [`CLAUDE.md`](./CLAUDE.md).

## Stack

Python 3.11+, minimal dependencies (`requests`, `PyYAML`, `jsonschema`), no frameworks, with unit tests.

## A real issue

[`data/2026-S42/informe.md`](./data/2026-S42/informe.md) is a real, published issue — not a mock-up. [`transparencia.md`](./data/2026-S42/transparencia.md) in that same folder shows what the deterministic checks and the verifier actually found that week, and [`log.json`](./data/2026-S42/log.json) has the full detail behind it.

## Running it locally

You'll need a `.env` (or exported environment variables) with `FRED_API_KEY` (free, see [FRED's docs](https://fred.stlouisfed.org/docs/api/api_key.html)) and `BUTTONDOWN_API_KEY` (free plan works, see [Buttondown's docs](https://docs.buttondown.com/api-authentication)) — `fetch_data.py` and `publish.py` fail fast and explain which one is missing if you skip this.

```
pip install -e .
python scripts/fetch_data.py --semana 2026-S99
# write data/2026-S99/informe.json by hand, or copy one from a past week
./scripts/run_week.sh 2026-S99 --sin-publicar
```

`run_week.sh` chains `validate.py` → `render.py` → `publish.py` for local testing only — it assumes `informe.json` already exists (writing and verification require real judgment, so they're not scriptable: that's what the Claude Code Routine does, see `TAREA_SEMANAL.md`). `--sin-publicar` stops before creating a real Buttondown draft.

## Known limitations and next steps

- **The verifier isn't a fully independent pass.** It re-reads every source from scratch and is instructed to act as a skeptical reviewer, but it runs in the same Claude Code session as the writer, not a separate subagent with a clean context. Splitting it out would be a real architecture change, not yet done.
- **Figures cited without `ref_datos`** (a number from a press article, not from `datos.json`) are counted and surfaced as a warning, but never checked against anything — there's no automated way to verify a number that isn't in the hard data.
- **No push notification if a Sunday run fails.** The Routine always ends with a summary, but someone still has to go check it; nothing proactively alerts if a week's draft never got created.
- **Yahoo Finance's unofficial endpoint has no backup source** for the instruments it's the only free option for (Nikkei 225, gold, the MSCI proxies) — documented as an accepted risk, not a gap waiting to be closed.

## License

[MIT](./LICENSE)

## Disclaimer

Informational content. Not investment advice.
