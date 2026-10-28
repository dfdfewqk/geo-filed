# GeoField A10 → Antigravity: DeepSeek integration handoff (2026-10-28)

## Responsibility and safety
- ChatGPT A10: existing backend optional LLM path with DeepSeek provider, one-shot explicit request, minimized payload, 60-second network/socket timeout, sanitized error states, exact-run response/SQLite snapshot association (read-only), tests.
- Antigravity B05/B07: Windows env setup, frontend opt-in/one-click cancel-before-call UI, correct provider rendering and 65-second-or-more **frontend** response timeout, actual paid API call only with user approval at the final Windows check.
- **Do not** add a second LLM service, persist keys, launch calls automatically, treat generated text as structural safety evidence, overwrite STEP/FRD/SQLite/weights, or change CAD/FEA calculations.

## Windows environment variables (not committed)
Set in the Windows user's environment, not project files:
- `GEOFIELD_AGENT_LLM_ENABLED=1`
- `GEOFIELD_AGENT_LLM_PROVIDER=deepseek`
- `DEEPSEEK_API_KEY=<user-provided-secret>`
- Optional `GEOFIELD_AGENT_LLM_MODEL=deepseek-flash` (default), or `deepseek-v4-pro`.

Currently supported official DeepSeek OpenAI-compatible models: `deepseek-flash` and `deepseek-v4-pro` (official documentation observed 2026-10-28). Retired model IDs `deepseek-chat`, `deepseek-reasoner` and old `deepseek-v4-flash` are **not selected by this backend**.
Official sources: https://api-docs.deepseek.com/quick_start/agent_integrations/ and https://api-docs.deepseek.com/api/create-chat-completion/

## API request/response contract
- `GET /api/agent/evidence/<cad_job_id>` with **no** explicit paid opt-in: rules-only. No call, even if a key exists.
- `GET /api/agent/evidence/<cad_job_id>?llm=1` AND `X-GeoField-LLM-Opt-In: 1` AND same-origin browser checks: one explicit paid call only. Clear the checkbox immediately before the request, so the next call always requires new consent. Closing/revoking BEFORE sending makes no external call. There is **no automatic re-call** on 401/402/429/network/timeout/invalid output.
- DeepSeek HTTPS backend URL is fixed to `https://api.deepseek.com/chat/completions`, request `model=deepseek-flash` by default, `thinking.type=disabled`, `max_tokens=220`, `stream=false`, 60-second socket timeout, blocked redirects.
- Outbound **fixed allowlist**: measured CAD review count, enum ML research status, verified-FEA status, numerical maximum stress MPa, displacement mm, verified element type, convergence-not-verified, safety-not-certified. **No original STEP, FRD, geometry vertices, CAD filename, filesystem path, ZIP contents, user-entered text, run_id, job_id, case SHA, CAD SHA, or stored report.** API key is in Authorization header only.
- Backend reply `llm.provider='deepseek'`, `status='external_explanation_only'`, `connected=true`, `executed=true`, `opt_in=true` only on provider completion; `external_text_unverified=true`, `persisted=false`. Verified FEA reply carries internal `run_id`, `case_sha256`, `cad_sha256` and `evidence_bound=true`; these are **NOT transmitted** to DeepSeek.
- `llm.history_binding.status='verified_existing_snapshot'` and `snapshot_id` ONLY if an existing SQLite FEA summary is **reread** and run ID + CAD SHA + case SHA match. Otherwise `run_only_not_persisted`. No automatic paid-text archiving. The local AI output itself is an unverified description, not design certification.
- Failure `llm.status` enum: `not_configured`, `invalid_evidence`, `authentication_failed`, `insufficient_balance`, `access_denied`, `unsupported_model`, `rate_limited`, `timeout`, `network_unavailable`, `invalid_response`, `provider_error`, `unavailable`. Never show raw provider error bodies or credentials. Continue displaying original rules-only CAD/FEA.
- Backend refuses returning paid text if CAD, FEA, R12, ML run, signed case or restored session changes while awaiting the provider.

## B05 frontend change required — NOT included in A10
`src/payload/frontend/cad.js` currently tests `llm.provider==='openai'` when displaying a connected external response, and uses `get(...,20000,...)` for consented LLM requests. **Antigravity must** allow both `openai` and `deepseek` when their response is actually executed and opt-in accepted, display provider name and failure enums, and increase its opted-in fetch timeout to at least 65,000ms (provider can take 60 seconds). Preserve the one-request checkbox reset; no new standalone DeepSeek menu required. Ensure no automatic reload/retry of a paid request. Update the UI's static text currently saying "DeepSeek API는 추후 연결".
The pre-existing HTML report/optional A08 save path does NOT make a paid call and must never claim DeepSeek output was included when its bound response is not supplied.

## Verification boundaries
GitHub Actions tests run actual production Python configuration/transport functions against stub HTTP/SQLite and synthetic FEA evidence. They check one request only, URL, model, HTTP status classification, no data leakage, opt-in required, and exact run+snapshot binding; they do not possess a real key or make a paid call.
The one-time Windows actual test belongs to B07, not the A10 code implementation phase.
