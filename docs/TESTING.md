# Testing

What the suites are, how to run them, and what the coverage numbers actually
mean — including the parts that are worse than they look.

## Running

| | Command |
|---|---|
| Backend | `pytest` |
| Backend + coverage | `pytest --cov --cov-report=term-missing` |
| Frontend unit | `npm test` *(from `src/presentation/react`)* |
| Frontend + coverage | `npm run test:coverage` |
| E2E | `npm run test:e2e` |
| Everything | `npm run test:all` |

There is deliberately **no `fail-under` gate yet** on either side. A threshold
set before anyone looks at the number either locks in an arbitrary figure or
gets lowered to make a build green. Pick one from the baselines below, record it,
and ratchet it upward — never downward.

## Baselines — measured 2026-10-14

### Backend: 81%

`2253` statements, `408` missed, branch coverage on. 412 tests, ~36s.

Strong where it matters: `rag_engine.py` 92%, `gemini_provider.py` 93%,
`guardrails/checks.py` 91%, `semantic_chunker.py` 90%, `sqlite_conversation_repository.py` 86%.

**Three modules at 0%**, which the headline number hides:

| Module | Why it matters |
|---|---|
| `presentation/api/app.py` (0%) | The composition root. Nothing tests that the app wires its dependencies correctly — a wrong `Registry.set()` only surfaces at runtime. |
| `infrastructure/embeddings/huggingface_embeddings.py` (0%) | The default embedding provider. 153 lines, never executed by a test. |
| `presentation/api/routes/health.py` (0%) | The liveness probe. The one endpoint an orchestrator depends on. |

### Frontend: 13.6%

34 tests across three files, against roughly 3,000 lines of JSX.

**Twelve modules at 0%**, including every component in the navigation shell:

```
App.jsx  theme.js  navItems.js  PageScroll.jsx  ErrorBoundary.jsx  EmptyState.jsx
TopNav.jsx  Dock.jsx  MobileNav.jsx  CommandPalette.jsx
DocumentList.jsx  HistoryView.jsx  SettingsPanel.jsx  ChatWidget.jsx (4.9%)
```

What the 34 tests *do* cover is narrow and deliberate: `api.js` (the fetch
layer), `Markdown.jsx` (the riskiest renderer), and three tiny presentational
components. That is a reasonable foundation. It is not a net over the app.

## Coverage is not value — the clearest example in this repo

`infrastructure/llm/structured_output.py` is a **dead feature**: no production
caller ever passes `use_structured_output=True`. It sits at **93% coverage**,
because it has two dedicated test files (284 lines) exercising a code path
nothing else calls.

Meanwhile the embedding provider and the app composition root sit at 0%.

Coverage measures *what executed*. It cannot tell dead code from load-bearing
code, and a high number is exactly as achievable by testing something useless as
by testing something important. Treat a coverage figure as a floor, not a score.

## Known gaps

- `tests/integration/` and `tests/e2e/` exist but are **empty** (only
  `__init__.py`). The layout implies a layer of testing that does not exist.
- The E2E suite mocks the API, so it verifies frontend behaviour against a
  contract, not against the real backend. Nothing exercises the two together
  automatically.

## There is no authentication — deliberately

The app has no auth layer, no rate limiter, and no Postgres store. That was a
**decision, not an oversight**: commit `7a199d8` ("refactor: delete the
infrastructure add-ons nothing enables") removed ~1050 lines of JWT auth, rate
limiting, the Postgres repository and OpenTelemetry tracing, on the grounds that
they were all gated behind flags nothing enabled and — for auth in particular —
that guarding requests from the machine's own user "is not a boundary, it is a
second way to get the app wrong".

Two things follow from that, and they are worth keeping separate:

1. **`.env.example` was not updated with the deletion.** It went on documenting
   `ENABLE_AUTH`, `SECRET_KEY`, `AUTH_API_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
   `ENABLE_RATE_LIMITING`, `RATE_LIMIT_*` and `DATABASE_URL` — none of which any
   code read. Someone deploying this would set `ENABLE_AUTH=true`, get no error,
   and believe they were authenticated. **Fixed** — those blocks are removed and
   every remaining variable is verified against `settings.py`.

2. **The "loopback only" premise is now load-bearing.** It is the *entire*
   access-control story, and it is not enforced by the application — it is a
   consequence of the `--host 127.0.0.1` in the Dockerfile and the
   `127.0.0.1:8000:8000` publish in `docker-compose.yml`. Start the server with
   `--host 0.0.0.0`, put it behind a proxy that forwards from elsewhere, or
   tunnel it, and there is no authentication in front of the corpus, the
   conversation history, or the Settings API-key endpoints. If this ever leaves
   the developer's machine, auth has to be rebuilt first.

Stale `__pycache__` entries for the deleted modules (`jwt_auth`, `limiter`,
`postgres_conversation_repository`, `query_rewriter`, `parent_child_splitter`
and others) survived the deletions and were misleading — a stale `.pyc` for a
module that no longer exists reads, to anything scanning the tree, like an
existing implementation. They have been removed.