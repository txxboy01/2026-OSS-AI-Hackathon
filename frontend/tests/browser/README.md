# Browser integration regressions

Runs the actual Next UI in installed Chrome against actual FastAPI HTTP routes.
Only the Gemini extractor is replaced, using `app_env="test"`. No Gemini key or
live model call is needed. API validation, CORS, evidence validation and guidance
remain real. The fixture raises only analysis rate limits for repeated scenarios.

Prerequisites: frontend dependencies, the backend virtual environment, Node 22+
and Playwright (or playwright-core) with installed Google Chrome. No browser is
downloaded by this harness. When Playwright is installed outside this project,
set `QA_PLAYWRIGHT_MODULE` to its absolute `index.mjs` path.

From `frontend`:

```sh
node --test --test-concurrency=1 tests/browser/regressions.test.mjs
```

Optional environment variables:

- `QA_PLAYWRIGHT_MODULE`: absolute path to the installed Playwright module.
- `QA_PYTHON`: backend Python executable (defaults to `rpm-backend/.venv`).
- `QA_HEADED=1`: visible Chrome; otherwise runs headless.
- `QA_OUTPUT`: evidence directory; defaults to a unique OS temporary directory.

Do not run two copies against the same checkout simultaneously: Next dev owns
that checkout's `.next/dev` lock. Server ports and default evidence directories
are unique per run. Startup waits for server readiness events. Race cases hold
real HTTP responses, subscribe to the terminal DOM transition, then release the
responses; there are no sleeps or polling delays. Every scenario gets a new
browser context and a bounded timeout.

Coverage: obsolete analysis success/error responses after sample/text changes,
duplicate submission, consent-independent guidance before analysis and after
HTTP/network failure, all six guidance actions, responsive navigation at
320/375/720/768px, and both dialogs' focus, Tab/Shift+Tab, Escape, close button and
backdrop behavior. The desktop result-to-guidance flow is a control case.

Each run retains PNGs, Playwright traces, request bodies, commands, server logs
and cleanup receipts outside the repository. Modal screenshots are full-page:
the backdrop correctly covers the viewport, not offscreen document content.
The harness closes its browser and terminates only its own server processes.
