# Vercel Product Site Extraction Report

**Date:** 2026-09-15
**Milestone:** Separate Vercel-ready public product site
**Status:** Complete
**Route target:** Vercel static site with project root `vercel-site/`

## Summary

Extracted the product website out of the FastAPI service into a standalone, frontend-only
site that deploys to Vercel with no backend, and added a purpose-built interactive demo
dashboard alongside it.

This milestone is **purely additive**. No existing file was modified. The FastAPI app, both
of its mounted frontends, the Evidence API, SDK, scanner, ACAP generation and runtime rules
are all untouched.

---

## Files created

All new. Nothing else in the repository changed.

| File | Bytes | Lines | Origin |
|---|---|---|---|
| `vercel-site/index.html` | 34,901 | 770 | Copied from `services/evidence_api/product/index.html`, then 3 edits |
| `vercel-site/dashboard.html` | 25,095 | 603 | **New** — static demo console shell |
| `vercel-site/assets/styles.css` | 42,212 | 1,862 | **Verbatim copy** of `product/styles.css` |
| `vercel-site/assets/app.js` | 15,198 | 404 | **Verbatim copy** of `product/app.js` |
| `vercel-site/assets/dashboard.css` | 27,838 | 501 | **Verbatim copy** of `static/styles.css` |
| `vercel-site/assets/dashboard.js` | 50,299 | 1,334 | **New** — demo console controller |
| `vercel-site/assets/demo-data.js` | 38,933 | 948 | **New** — the entire demo dataset |
| `vercel-site/assets/favicon.svg` | 553 | 9 | **New** — shield + check mark |
| `vercel-site/vercel.json` | 591 | 22 | **New** |
| `vercel-site/README.md` | 7,119 | 167 | **New** |
| `docs/generated/VERCEL_PRODUCT_SITE_EXTRACTION_REPORT.md` | — | — | **New** (this file) |

The three verbatim copies were verified byte-identical with `cmp`, so the public site
renders pixel-for-pixel like the current `/product/` and `/ui/`.

---

## What was copied vs. extracted vs. written

### Copied verbatim (3 files)

`product/styles.css`, `product/app.js`, `static/styles.css`. Chosen deliberately over
merging the two stylesheets: they declare the same palette under *different* variable names
(`--bg-warm` vs `--bg`, `--green-deep` vs `--green`, `--rose` vs `--danger`) and both define
`.card`, `.badge` and `.btn-primary`. Hand-merging 70 KB of CSS would have risked selector
collisions and visual drift for no benefit.

### Extracted with minimal edits (1 file)

`index.html` — copied, then exactly three changes:

1. **Five dashboard CTAs repointed** from the absolute `/ui/` (which 404s on any static
   host) to the relative `./dashboard.html`: nav "Live Dashboard", hero "View Live Demo",
   assessment "View in Dashboard", final CTA "Open Demo Dashboard", footer "Demo Dashboard".
   Asset paths moved to `./assets/`. Relative paths were chosen so the page works under
   `file://`, `python -m http.server` and Vercel identically.
2. **Product story completed to four clauses.** The site shipped only the three-clause
   version in `.philosophy-quote` and the footer. The canonical principle in
   `docs/team/01_PRODUCT_AND_WORKFLOW.md:26` is
   *"Scanner suggests. Human approves. Runtime proves. **Rescan shows drift.**"* —
   the fourth clause was added in both places.
3. **Public-site metadata added** that the page lacked entirely: favicon, `og:*`,
   `twitter:*`, canonical link, `theme-color`.

No other copy, layout, section or interaction was changed. All 7 required sections are
intact and untouched: codebase scanner (`#scanner`), capability review (cards inside it),
ACAP generation (`#acap`), runtime monitoring (`#monitoring`), findings and assessment
(`#assessment`), stakeholder value (`#confidence`, `#coverage`, `#cta`).

### Written new (4 files)

`dashboard.html`, `dashboard.js`, `demo-data.js`, `favicon.svg`.

The demo console was written from scratch rather than copying the real `static/app.js`
(1,438 lines driving 14 GET + 8 POST endpoints) and stubbing its network layer. A fetch
shim would have dragged in upload, demo-reset and export-report controls that cannot work
publicly, and any unstubbed route would surface as a console error. The rewrite reuses the
real console's markup, class names and helper semantics, so it looks and behaves like the
product while being genuinely static.

The 7th "Settings" tab of the real console was dropped: all three of its buttons (Reset
Demo, Run Assessment, Export Report) are backend-only.

---

## What is static / demo-only

Everything. There is no backend, and the demo makes no call to one.

| Capability | Status in the public site |
|---|---|
| Data source | `assets/demo-data.js` (`window.AGENTGOV_DEMO`), a plain `<script>` include |
| Review decisions | In-memory; reset on refresh or on re-selecting a system |
| ACAP version generation | Appends a version to page state |
| `governance.yaml` | Built in-browser, downloaded via `Blob` + `URL.createObjectURL` |
| Run ACAP Rules | Two rules reimplemented in JS over the fixture's events |
| Findings | Recomputed locally from review state + events |
| Assessment | Frozen fixture snapshot (as in the real product), flagged stale when finding counts diverge |
| Discovery upload, demo reset, export report | Not present |
| Network | Only Google Fonts (identical to the existing product page) |

### Demo data

Two switchable systems:

- **`gaming-agent-demo`** (primary) — 4 capabilities matching `demo-gaming-backend/app.py`:
  `purchase_in_game_skin` (write / financial / approval required / **approved**),
  `ban_toxic_player` (write / account / approval required / **denied**),
  `update_leaderboard_score` (write / approved),
  `send_match_invite` (communicate / approved).
  Model surface: one OpenAI call, `generate_npc_dialogue -> openai.chat.completions.create`.
  9 runtime events on one connected trace; 2 high-severity findings.
- **`support-api`** (secondary) — 3 capabilities, one in `needs_reapproval`, one `pending`,
  1 finding, audit status `needs_reapproval`. Gives the system selector a meaningful
  second state.

Shapes mirror the real API responses, including the unflattering parts: the coverage matrix
is the real fixed 17-field list from `coverage.py` with its `missing` and
`annotation_required` rows preserved, and `evidence_confidence` stays `low` because a
required field is missing. Missing fields are reported as missing, never fabricated.

The two findings are the ones that carry the product story:

| Rule | Capability | Why it fires |
|---|---|---|
| `R_ACAP_denied_observed` | `ban_toxic_player` | A human explicitly denied it; runtime invoked it anyway |
| `R_ACAP_approval_required_missing` | `purchase_in_game_skin` | Event claims `approval.granted: true` with **no** verification flag |

The second is the subtle one and is faithful to `rules.py:190-202`: `approval.granted` is
self-reported and is **not** trusted evidence. Only `approval.verified`, `approval.trusted`
or `approval.token_verified` count. The demo event claims approval without proving it.

**Privacy.** Synthetic data only. No raw prompts, raw responses, API keys, tokens, emails,
customer data or secrets. `sha256:…` session and actor values are illustrative strings, not
hashes of anything real. Nothing was copied from `.env`, `evidence.db`, notebooks or
`artifacts/governance/`. Tool arguments appear in the API's `public_event` projection shape
(`arguments_exposed: false`), so the demo shows honestly that argument values are not stored.

---

## How to run locally

```bash
cd vercel-site
python -m http.server 3000
```

| URL | Page |
|---|---|
| http://127.0.0.1:3000 | Product landing page |
| http://127.0.0.1:3000/dashboard.html | Demo dashboard |

Both pages also work when opened directly from disk — all paths are relative and the demo
data is a `<script>` include rather than a `fetch`, so nothing is blocked by `file://`
CORS. (`/dashboard` without the extension is a Vercel rewrite and only resolves once deployed.)

## How to deploy to Vercel

1. Push the repository.
2. Vercel → **New Project** → import the repo.
3. **Root Directory:** `vercel-site`
4. **Framework Preset:** Other. Leave Build Command and Output Directory empty — there is
   no `package.json` and no build step.
5. Deploy.

`vercel.json` provides:

| Route | Serves |
|---|---|
| `/` | `index.html` (Vercel static default) |
| `/dashboard` | `dashboard.html` (rewrite, no redirect) |
| `/dashboard.html` | `dashboard.html` (direct) |
| `/assets/*` | assets, `Cache-Control: public, max-age=3600` |

`cleanUrls` was deliberately **not** used: it would 308-redirect `/dashboard.html` to
`/dashboard`, whereas the requirement is that both resolve directly. Baseline security
headers (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`) are also set.

---

## What remains in the FastAPI app

Unchanged and still the source of truth:

| Component | Location |
|---|---|
| Operational dashboard | `services/evidence_api/static/` → `/ui/` |
| Product page (original) | `services/evidence_api/product/` → `/product/` |
| Evidence API | `services/evidence_api/app.py` (all routes) |
| Evidence store | `services/evidence_api/db.py` |
| ACAP generation / draft | `services/evidence_api/draft.py`, `app.py` |
| Runtime rules | `services/evidence_api/rules.py` |
| Coverage / risk / report | `coverage.py`, `risk.py`, `report.py` |
| Control library | `control_library.py`, `control-library/canonical-controls.yaml` |
| Scanner + SDK | `sdk-python/` |

`git status --porcelain services/ sdk-python/ tests/` is empty. The mounts at
`services/evidence_api/app.py:60-61` are untouched, which matters because
`tests/test_evidence_ui.py:43-71` asserts on the literal contents of `/ui/app.js` and
`/ui/index.html`.

---

## Verification result

| Check | Result |
|---|---|
| All 8 files serve over `python -m http.server 3000` | **PASS** — all HTTP 200 |
| `vercel.json` valid JSON | **PASS** |
| `node --check` on all 3 JS files | **PASS** |
| Landing page loads | **PASS** |
| Dashboard loads | **PASS** |
| **Console errors / warnings (whole session)** | **PASS — 0 errors, 0 warnings** |
| Initial render populated | **PASS** — 4 capability cards, 17 coverage rows, 9 events, 2 findings, 4 framework cards, 9 timeline items, 5 framework-status rows, 5 applicability rows |
| All 6 tabs switch | **PASS** |
| All 6 risk filters | **PASS** — all:4, high:2, medium:2, low:0 (empty state), pending:0, reviewed:4 |
| Approve / Reject / Not-a-Capability | **PASS** — badges, ACAP counts and audit status all update |
| Edit modal (save + cancel) | **PASS** — action type, risk, data classes, approval, side effect all write back; card re-classifies to `risk-high` |
| Generate ACAP Version | **PASS** — appended v3, v4; counts recomputed |
| `governance.yaml` preview | **PASS** — correctly excludes the denied capability, emits `approval_required` / `data_classes` / `external_side_effect` only when set, exactly like `_build_manifest_from_acap` |
| `governance.yaml` download (both buttons) | **PASS** — real `blob:` download named `governance.yaml` |
| Run ACAP Rules | **PASS** — "2 findings from 3 tool events (ACAP v3)"; findings, workflow dots and audit status all update |
| Rules genuinely computed | **PASS** — approving `ban_toxic_player` reclassified its finding from `R_ACAP_denied_observed` to `R_ACAP_approval_required_missing` rather than replaying a canned result |
| System selector | **PASS** — switches to `support-api` (3 caps, 1 finding, `needs_reapproval`); switching back restores pristine gaming state |
| Responsive 1440px / 390px | **PASS** — no horizontal page overflow (383px content in 390px viewport); wide tables scroll inside their own `overflow-x: auto` containers |
| Mobile sidebar drawer | **PASS** — added (see below); opens to `left: 0`, scrim works, closes on tab pick and Escape |
| No broken links | **PASS** — 26 links, 0 pointing at `/ui/`, 0 dead in-page anchors, 0 placeholder `#`, 0 external |
| No backend references in deployable files | **PASS** — no `fetch(`, `XMLHttpRequest`, `WebSocket`, `127.0.0.1`, `localhost`, `:8000` or `/ui/` outside comments and README |
| Network traffic | **PASS** — only Google Fonts, identical to the existing product page |
| Verbatim copies byte-identical | **PASS** — `cmp` clean on all 3 |
| `services/`, `sdk-python/`, `tests/` untouched | **PASS** — `git status --porcelain` empty |

### One fix made beyond a straight copy

`dashboard.css` parks `.sidebar` at `left: -260px` under `@media (max-width: 960px)` and
reveals it with `.sidebar.open`, but the real console ships **no toggle** for that class —
so on a phone the sidebar is unreachable. Since the stylesheet had to stay a verbatim copy,
a toggle button, scrim and Escape handler were added in `dashboard.html`'s demo-only
`<style>` block and `dashboard.js`. This is a latent bug in the operational console at
`/ui/` too, and is worth a separate ticket.

### Python test suite

`python -m unittest discover -s tests -t .` → **`Ran 239 tests`, `FAILED (failures=25, errors=4)`.**

**These failures are pre-existing and unrelated to this milestone.** Verified by moving
`vercel-site/` out of the repository entirely and re-running: byte-identical result
(25 failures, 4 errors). Root cause is environmental — `artifacts/governance/` does not
exist in this working tree (it is gitignored by design per `CLAUDE.md`), so the tests that
read `artifacts/governance/events.jsonl` raise `FileNotFoundError`. They need a prior
scenario run to generate the evidence JSONL. No Python file was touched by this milestone.

---

## Limitations

1. **State is in-memory.** Every demo action resets on refresh. Re-selecting a system in
   the selector is the intended way to restart a walkthrough.
2. **Findings carry frontend fixture enrichment.** The demo findings include
   `failed_control`, `failed_control_title` and `framework_mappings` so the Findings detail
   panel can render its Failed Control and Framework Mappings sections. **The live backend
   does not emit these for ACAP findings** — `run_all_acap_rules` never calls
   `control_library.enrich_finding`, and `control-library/canonical-controls.yaml` only maps
   `R1_confirm_without_proposal` and `R2_confirmation_without_customer_turn`. That is a real
   gap in the backend, recorded here rather than papered over, and it means the live
   dashboard's failed-control chip and ACAP framework status will not light up for ACAP
   findings until the enrichment call is added.
3. **The fixture is hand-authored**, not generated from a real scan. If the scanner,
   ACAP or event schema changes, `demo-data.js` must be updated by hand. The committed
   `gaming-discovery.json` only captured route wrappers plus two of the four functions, so
   all four capabilities were authored directly against the real candidate schema.
4. **No real drift/rescan demo.** The fourth clause of the product story
   ("Rescan shows drift") is told in copy on the landing page but not simulated in the
   dashboard; there is no second scan to diff. A `changeset` view would need a second
   fixture upload.
5. **The demo's `finding_id` is not a real sha256.** WebCrypto is async, so `dashboard.js`
   uses a synchronous FNV-1a stand-in producing the same `F-` + 12-hex shape. Ids are
   deterministic for the same inputs but will not match backend ids.
6. **No token costs, no OTLP export, no live model calls.**
7. **Palette duplicated across two stylesheets** under different token names. Extracting a
   single shared token file for `/product/`, `/ui/` and the Vercel site is a reasonable
   follow-up.
8. **No OG image.** `og:*` tags are present but there is no preview image asset, so link
   previews will render text-only.
