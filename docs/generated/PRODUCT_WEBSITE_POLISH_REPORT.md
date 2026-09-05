# Product Website Polish Report

**Date:** 2026-08-27
**Route:** `/product/`
**Status:** Complete

## Files Changed

| File | Changes |
|------|---------|
| `services/evidence_api/product/index.html` | Removed inline onclick attrs, added evidence lists to 2 cards, expanded all 3 cards, CTA dark button classes, new multi-column footer, updated link targets |
| `services/evidence_api/product/styles.css` | Navbar polish, hero shimmer + connectors, timeline enhancements, CTA text readability fix, footer grid, card states (approve/reject/edit), grain texture, stronger hovers |
| `services/evidence_api/product/app.js` | Fixed expand/collapse bug, Approve/Edit/Reject button handlers, stat count-up animation, inline edit panel |
| `docs/generated/PRODUCT_WEBSITE_POLISH_REPORT.md` | New (this file) |

## Files NOT Changed

- `services/evidence_api/static/*` — `/ui/` dashboard untouched
- `services/evidence_api/app.py` — routes unchanged
- `sdk-python/*` — SDK untouched

## Bug Fixes

### 1. Card expand/collapse (was broken)
- **Root cause:** JS handler called `e.stopPropagation()` which blocked the inline `onclick` from toggling `.expanded`. Cards 2 and 3 could never expand.
- **Fix:** Removed inline `onclick` attrs from HTML. Replaced JS handler with proper `header.closest(".capability-card").classList.toggle("expanded")`.

### 2. CTA section text readability (was invisible)
- **Root cause:** Background gradient goes from `#FAFAF7` to `#111827` but text stayed dark body color.
- **Fix:** Added CSS overrides for `.cta-section h2`, `.section-subtitle`, `.section-label`, and `.accent-text` to use light-on-dark colors. Changed CTA buttons from `btn-secondary` to `btn-secondary-dark`.

## New Interactions

### Approve/Edit/Reject Buttons
- **Approve:** Adds green "Approved" badge to header, `.card-approved` class (green border, green header bg), status text "Added to ACAP draft".
- **Reject:** Adds red "Rejected" badge, `.card-rejected` class (dimmed to 55% opacity, grayscale body), status text "Excluded from ACAP".
- **Edit:** Opens inline edit panel with 3 fields (Action Type select, Approval Required select, Data Classification text input). Save updates card meta values. Cancel closes panel. Re-clicking Edit toggles panel off.
- All state is frontend-only mock. No backend calls.

### Stat Count-up Animation
- IntersectionObserver triggers when `.scanner-stats` scrolls into view (30% threshold).
- Each `.stat-value` animates from 0 to target over 1.5s with ease-out cubic.
- Handles comma-formatted numbers (strips for parsing, re-adds via `toLocaleString()`).
- Skipped when `prefers-reduced-motion` is set.

## Visual Polish

| Area | Change |
|------|--------|
| Navbar logo | 1.15rem -> 1.3rem, tighter letter-spacing (-0.03em) |
| Nav link gap | 28px -> 36px |
| Nav padding | 28px -> 36px |
| Hero code lines | Static gray replaced with shimmer gradient animation (2.5s loop) |
| Hero card connectors | Vertical line from code to cards + horizontal ticks per card |
| Timeline progress | 0.15s linear -> 0.4s cubic-bezier for smoother fill |
| Timeline circles | Box-shadow 4px/0.12 -> 6px/0.15, added scale(1.1) on active |
| Timeline step spacing | Padding-bottom 64px -> 72px |
| Timeline step desc | Line-height 1.65 -> 1.75 |
| Timeline sticky (tablet) | Margin-bottom 20px -> 32px |
| Card hover | shadow-md -> shadow-lg, translateY -2px -> -3px, green border |
| Stat card | Added hover effect (shadow-md, translateY -2px) |
| Confidence card hover | Added green border on hover |
| Background texture | SVG noise grain at 2.5% opacity via `body::after` |
| Footer | Single line replaced with 4-column grid (brand, Product, Platform, Resources) + bottom tagline |

## Content Completions

| Card | Before | After |
|------|--------|-------|
| `refund_execute` | Fully populated, expanded | Unchanged |
| `send_invoice_email` | Collapsed, no evidence list | Expanded, 5 evidence items added |
| `delete_customer` | Collapsed, no evidence list | Expanded, 5 evidence items added |

## CTA Link Targets

| Button | Href | Status |
|--------|------|--------|
| Live Dashboard (nav) | `/ui/` | Working |
| View Live Demo | `/ui/` | Working |
| Open Demo Dashboard | `/ui/` | Working |
| View in Dashboard | `/ui/` | Working |
| Dashboard (footer) | `/ui/` | Working |
| Explore Scanner | `#scanner` | Working |
| Review SDK | `#adapters` | Working (updated from `#scanner`) |
| Approve Next Milestone | `#scanner` | Working (updated from `#assessment`) |
| Generate Instrumentation Plan | `#scanner` | Working |

## Validation Results

| Check | Result |
|-------|--------|
| Missing anchor targets | 0 |
| `/ui/` links | 5 (all working) |
| Inline onclick attrs | 0 (all removed) |
| Emoji characters | 0 |
| Expanded cards with evidence | 3 of 3 |
| Footer grid | Present |
| CTA dark buttons | 4 (1 primary-dark, 3 secondary-dark) |
| New CSS classes | All present |
| New JS features | All present |
| prefers-reduced-motion | Respected (shimmer, grain, count-up all disabled) |

## Remaining Polish Opportunities

- Capability card expand/collapse could use a height transition animation for smoother open/close
- The edit panel could include visual feedback (brief highlight) after Save
- Stats could show a brief highlight/pulse after count-up completes
- The hero scanner visual could add a subtle particle effect or more code-like patterns
- Consider adding a favicon if one does not exist
