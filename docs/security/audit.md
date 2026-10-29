# Security audit (ASVS-lite) · T-6.5

> Scope: the FastAPI service, the run store, upload handling and the browser client as
> built through T-5.5. Method: ASVS-style checklist + targeted tests in
> `tests/security/audit/` + tooling (pip-audit, npm audit, gitleaks). Each finding has an
> id, a severity, and either a fixing commit or a tracked follow-up.

## Verdict

| Severity | Open | Accepted (time-boxed) | Fixed |
|---|---|---|---|
| Critical | 0 | 0 | 0 |
| High | 0 | 0 | 1 (F-15) |
| Medium | 1 | 0 | 2 (F-09, F-10) |
| Low | 0 | 1 (F-11) | 1 (F-15 selector-parser) |

Critical: 0 · High: 0 — recorded on 2026-10-30 and enforced by
`uv run pytest tests/security -q`. The only open Medium is F-13 (Pillow advisories
blocked by the 14-day dependency freeze); every other finding is verified, fixed, or
explicitly accepted with a trigger.

## Tooling results

| Check | Command | Result |
|---|---|---|
| Python advisories | `uv run --with pip-audit pip-audit` | 65 advisories across 4 packages (all dev/tooling or blocked by the 14-day freeze — see F-13/F-14) |
| Web advisories | `npm --prefix web audit --audit-level=high` | 0 vulnerabilities after `npm audit fix` (was 1 high + 1 moderate — F-15) |
| Secret scan | `gitleaks detect --no-banner --redact` | no leaks (37+ commits) |
| Upload/traversal/fuzz suite | `uv run pytest tests/security -q` | pass, incl. 75 audit tests, no xfails |

`pre-commit run gitleaks --all-files` cannot bootstrap its hook cache in the locked-down
sandbox; CI runs the same gitleaks binary (`8.30.1`) on every push, and the direct scan
above was executed locally.

## Checklist (ASVS 4.0 categories, trimmed)

| # | Control | Status | Evidence |
|---|---|---|---|
| V1 | Authentication: access code constant-time, fail-closed when unset | Pass | `tests/security/test_access.py`, `audit/test_authorization.py` |
| V2 | Session: no server session, code kept in `sessionStorage` only | Pass | `web/src/api/client.ts`, T-5.6 |
| V3 | Session timeout / logout | n/a | stateless code per request |
| V4 | Authorization: every non-public route guarded | Pass | `audit/test_authorization.py` (6 routes × missing/wrong code) |
| V5 | Input validation: magic bytes, allowlist, caps, sanitised names | Pass | `audit/test_upload_fuzz.py` (26 cases) |
| V6 | Cryptography: no custom crypto, TLS by the host | Pass | no crypto code in `src/` |
| V7 | Error handling: typed envelope, no traces/paths | Pass | `audit/test_serving.py`, `api/errors.py` |
| V8 | Data protection: 24 h retention, redaction, no personal data | Pass | `audit/test_headers_privacy.py`, `security/retention.py`, `security/redact.py` |
| V9 | Communications: security headers | Pass (fixed) | F-10, `SecurityHeadersMiddleware` |
| V10 | Malicious code: no eval/exec, model output treated as data | Pass | JSON-only parsing; no `eval`, no shell strings |
| V11 | Business logic: spend cap, rate limit on creation | Pass (partial) | `audit/test_authorization.py` (429 + `Retry-After`); read routes unthrottled — F-11 |
| V12 | Files/resources: traversal-safe serving, allowlist dirs | Pass | `audit/test_serving.py` (13 traversal probes) |
| V13 | API/service: fixed `Content-Type`, Range safe, JSON only | Pass | `audit/test_serving.py` |
| V14 | Configuration: secrets via env only, no defaults baked in | Pass | `security/access.py`, `gitleaks` |

## Findings

| Id | Sev | Control | Finding | Status |
|---|---|---|---|---|
| F-01 | — | V1/V4 | Access code on every non-public route | Pass (verified) |
| F-02 | — | V12 | `..`, `%2f`, `%5c`, absolute, drive and `%00` path probes refused with E-13 | Pass (verified) |
| F-03 | — | V12 | `input/` and `stages/` are never served | Pass (verified) |
| F-04 | — | V5 | Archives rejected on container magic, never decompressed | Pass (verified) |
| F-05 | — | V5 | Container/extension mismatch rejected | Pass (verified) |
| F-06 | — | V5 | Traversal, drive, NUL, bidi and 400-char names sanitised or refused | Pass (verified) |
| F-07 | — | V5 | Resolution judged on displayed size (rotation-aware); 181 s refused | Pass (verified) |
| F-08 | — | V5 | Non-UTF-8 SOP text and PDFs without `%PDF-` refused | Pass (verified) |
| F-09 | Medium | V12 | A rejected upload left its part-written copy in `runs/.uploads/<id>/`. Fix: the scratch dir is removed when validation raises (video *and* SOP paths). | **Fixed** — `routes_runs.create_run`, tests in `audit/test_upload_fuzz.py` |
| F-10 | Medium | V9 | TRD §8 headers were missing. Fix: a pure-ASGI `SecurityHeadersMiddleware` (nosniff, `Referrer-Policy: no-referrer`, CSP) applied to every response including the SSE stream, which a buffering `BaseHTTPMiddleware` would have broken. | **Fixed** — `api/main.py`, tests in `audit/test_headers_privacy.py` |
| F-11 | Low | V11 | Only `POST /runs` is throttled; `GET`/SSE routes are not. An authenticated client can hold many SSE connections. | **Accepted** (single-tenant demo, code required); revisit at T-7.2 deploy |
| F-12 | — | V11 | Creation limiter returns 429 + `Retry-After` with the E-05 envelope | Pass (verified) |
| F-13 | Medium | V14 | `pillow 12.3.0` carries 39 published advisories (fix `13.0.0`, released 2026-10-16). Blocked by `exclude-newer = 2026-10-13` in `pyproject.toml`. Reachability: Pillow only ever receives `Image.fromarray` pixel buffers produced by ffmpeg — no untrusted image file is parsed — so no advisory maps to an executed path today. | **Open (tracked)** — bump to `pillow>=13.0.0` once the freeze window allows; needs the `exclude-newer` policy refreshed (human decision) |
| F-14 | Low | V14 | `certifi 2026.7.22`, `filelock 4.1.1`, `virtualenv 21.14.7` advisories: dev/tooling packages, not shipped in the runtime image (image list is fixed by T-7.2). | **Accepted** |
| F-15 | High (was) | V14 | `undici 8.11.2` (dev-only via `jsdom`) and `postcss-selector-parser 6.1.4` advisories in the web lockfile. | **Fixed** — `npm audit fix` (undici 8.12.2+, selector-parser 6.1.5+); `npm audit --audit-level=high` → 0 |
| F-16 | — | V8 | Redaction removes `META_API_KEY`, `Authorization`, `X-Access-Code`, `pw_access_code` from log lines and structured payloads | Pass (verified) |
| F-17 | — | V8 | Retention purge removes run media older than 24 h and keeps exempt demo cases | Pass (verified) |
| F-18 | Low | V10 | No `eval`/`exec`/`subprocess` with shell strings; ffmpeg/ffprobe are invoked with argument lists; model output is parsed as JSON only | Pass (verified by review) |

## Privacy statement (NFR-05)

Process Watcher analyses physical procedures, not people. Videos are used only to
verify the procedure against the written SOP; the system does not identify, name, track
or score individuals, and no face recognition is performed. Evidence images show hands
and tools by design (prompts never request faces). Operator names appear only in bench
metadata never rendered into reports. Uploads and derived media are deleted after 24 h
(frozen demo cases exempt). The only credential in the system is a shared access code,
compared in constant time; it is never logged or sent to the browser bundle.

## Follow-ups (owner, trigger)

1. **F-13** Pillow upgrade to `13.0.0` — O3/O4 with the dependency-freeze decision; re-run `pip-audit` afterwards.
2. **F-11** throttle read/SSE routes if the demo stays public past the submission.
