# Product Website Build Report

## Route

**URL**: `/product/` (e.g., `http://localhost:8000/product/`)

## Files Changed

### Modified
- `services/evidence_api/app.py` — Added 2 lines:
  - `PRODUCT_DIR` constant (line 27)
  - `app.mount("/product", ...)` static files mount (line 59)

### Created
- `services/evidence_api/product/index.html` — Landing page with 13 sections
- `services/evidence_api/product/styles.css` — Design system (dark glassmorphism, responsive)
- `services/evidence_api/product/app.js` — Scroll reveals, nav, journey interactivity, terminal animation

## Sections

1. Hero — headline, CTAs, animated flow visual
2. Problem — trace visualization, governance quote
3. Codebase Scanner — stats, interactive capability cards, terminal mock
4. Review Suggestions — 3-step flow (suggest → review → generate)
5. ACAP Generator — YAML preview + plain English translation
6. Runtime Monitoring — animated event stream, privacy badge
7. Adapter Layer — 7 adapter cards (FastAPI, OpenAI, Anthropic, LangChain, etc.)
8. Evidence Confidence — 4-tier confidence model, philosophy quote
9. Assessment Dashboard — KPI strip, finding card with evidence chain
10. Coverage Gaps — ungoverned capability examples
11. Interactive Product Journey — 6-step clickable flow with auto-advance
12. Stakeholder Value — 4-column audience cards
13. Final CTA — platform summary, dashboard link

## How to Run

```bash
cd services/evidence_api
uvicorn app:app --reload --port 8000
```

- Dashboard: http://localhost:8000/ui/
- Product page: http://localhost:8000/product/

## Tech Stack

- Vanilla HTML/CSS/JS (no build tools, no frameworks)
- Google Fonts (Inter) loaded via CDN
- CSS custom properties, glassmorphism, CSS Grid
- IntersectionObserver for scroll-triggered animations
- All UI data is mocked/static — no backend API calls from the product page

## Existing Dashboard

The `/ui/` route is completely unchanged. No files in `services/evidence_api/static/` were modified.
