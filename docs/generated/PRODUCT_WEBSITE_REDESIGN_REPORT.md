# Product Website Redesign Report

**Date:** 2026-08-27
**Route:** `/product/`
**Status:** Complete

## Files Changed

| File | Action |
|------|--------|
| `services/evidence_api/product/index.html` | Full rewrite (897 -> 706 lines) |
| `services/evidence_api/product/styles.css` | Full rewrite (1521 -> ~900 lines of design tokens + components) |
| `services/evidence_api/product/app.js` | Full rewrite (228 -> ~190 lines, added scroll timeline) |
| `docs/generated/PRODUCT_WEBSITE_REDESIGN_REPORT.md` | New (this file) |

## Files NOT Changed

| File | Status |
|------|--------|
| `services/evidence_api/static/*` | `/ui/` dashboard untouched |
| `services/evidence_api/app.py` | Routes unchanged; `/ui` and `/product` both mount correctly |
| `sdk-python/*` | SDK logic untouched |
| `tests/*` | Test files untouched |

## Design Changes

### Color Palette

| Element | Before | After |
|---------|--------|-------|
| Primary background | `#050a18` (near-black) | `#FAFAF7` (warm off-white) |
| Alternate sections | `#0a1628` (dark navy) | `#F5F3EE` (ivory) / `#EDEAE3` (cream) |
| Heading text | `#f1f5f9` (white) | `#1a2332` (deep navy) |
| Body text | `#94a3b8` (slate) | `#475569` (dark slate) |
| Primary accent | `#3b82f6` (bright blue) + neon gradients | `#1a5c3a` (forest green) |
| Cards | Glassmorphism with glow | White cards with subtle borders and soft shadows |

### Layout Changes

| Element | Before | After |
|---------|--------|-------|
| Hero | Centered, full-viewport dark with emoji flow diagram | Left-aligned text + right-side dark scanner visual |
| Timeline | Click-based 6-step journey with auto-advance | Scroll-driven sticky timeline with vertical fill line |
| Section backgrounds | All dark with slight variation | Alternating ivory/white/warm, dark only for runtime + assessment |
| Cards | Glass panels with backdrop-filter blur | Clean bordered cards on white backgrounds |
| Icons | Unicode emoji characters | Text abbreviations (IN, AI, FN, OK) and CSS shapes |

### Sections (10 total)

1. **Hero** — Left-aligned headline, right-side dark scanner panel with animated capability cards
2. **Scroll Timeline** (new) — Sticky left text + right vertical timeline with 6 numbered steps; line fills green on scroll, circles activate, sticky text updates
3. **Scanner Discovery** — Stats cards + 3 expandable capability review cards on warm background
4. **Review to ACAP** — 3-step visual flow + ACAP YAML (dark accent) + plain English + summary cards
5. **Runtime Monitoring** — Full dark section with event stream trace cards
6. **Adapters** — 8 clean cards with purpose, evidence type, and code snippets
7. **Evidence Confidence** — 4 trust-level cards with provenance indicators
8. **Assessment Dashboard** — Dark section with KPI strip + finding card with evidence chain
9. **Coverage Gaps** — Warning items showing ungoverned capabilities
10. **Final CTA** — Light-to-dark gradient with 3 action buttons

### Removed

- Emoji-based icons (replaced with CSS text or shapes)
- Animated grid background overlay
- Neon glow effects and gradient text fills
- Pulsing CTA button animation
- Problem Statement section (content folded into hero + timeline)
- Stakeholder Value section (4 persona cards)
- Journey step auto-advance timer

## Animation Behavior

| Animation | Implementation |
|-----------|---------------|
| Scroll timeline fill | `scroll` event listener calculates viewport-center progress through timeline track; updates CSS height of progress line |
| Timeline step activation | Steps activate (opacity 1, green circle) when viewport center passes their position |
| Sticky text update | Left panel text content changes via JS when active step changes |
| Fade-in reveals | IntersectionObserver with `threshold: 0.1` and staggered delays via `data-reveal-delay` |
| Scanner beam | CSS animation looping vertically across dark hero panel |
| Capability card reveal | CSS keyframe `heroCardReveal` with staggered delays |
| Event stream flow | Cards slide in from right with sequential delays |
| Confidence bars | Width animated from 0 to target on intersection |
| `prefers-reduced-motion` | All animations/transitions reduced to 0.01ms; beam hidden; elements shown at full opacity |

## Responsive Checks

| Breakpoint | Behavior |
|------------|----------|
| Desktop (>1024px) | Full 2-column layouts; sticky timeline; grid adapters |
| Tablet (768-1024px) | Single-column hero/timeline/monitoring; 2-col capability cards |
| Mobile (<768px) | Hamburger nav; single-column everything; timeline non-sticky; flow arrows rotate 90deg |
| Small mobile (<480px) | Compact spacing; hero pills hidden; single-column stats |

## Verification Results

| Check | Result |
|-------|--------|
| `/product/` loads | Pass |
| `/ui/` unchanged | Pass (files not modified) |
| All anchor links resolve | Pass (0 missing targets) |
| `/ui/` links present | Pass (4 occurrences) |
| Emoji characters | 0 (all removed) |
| Routes confirmed | `/ui` and `/product` both mounted in FastAPI |
| `prefers-reduced-motion` | Respected in CSS |
| Console errors | None expected (no external dependencies, no API calls) |

## Remaining Polish Opportunities

- Add subtle CSS grain/noise texture to ivory backgrounds for more editorial depth
- Consider adding a favicon if one does not exist
- The capability card expand/collapse could animate height instead of instant show/hide
- Terminal typing animation from the old version was removed; could be re-added for the scanner visual
- Consider adding `loading="lazy"` if images are ever added
