# 03_UI_Spec.md: Process Watcher · Design System and Style Guide
> Layer 02 · v1.0 · 2026-10-25 · Locks colours, typography, components and layout so every screen looks the same. Flows are in `02_AppFlow.md`. Contrast ratios below were computed against the listed backgrounds; T-6.7 re-verifies them with axe.

## 1. Principles
1. **Evidence first.** The real frame is the hero; models' prose is secondary. Evidence and illustrations must never look alike.
2. **Calm, professional tool.** Dark, dense but legible, no decoration that does not carry meaning.
3. **Projector-ready.** 18 px base text, high contrast, large hit targets; nothing important below 14 px.
4. **Honest uncertainty.** Low confidence looks different (dashed, muted) instead of being hidden or shouted.
5. **Keyboard-first review.** Every review action has a key; focus is always visible.

## 2. Colour tokens (dark theme, default)
| Token | Hex | Use | Contrast (on `surface` #121923) |
|---|---|---|---|
| `--bg` | `#0B0F14` | page background | n/a |
| `--surface` | `#121923` | cards, panels | n/a |
| `--surface-2` | `#1A2430` | raised elements, hover | n/a |
| `--border` | `#2A3A4D` | decorative dividers | decorative |
| `--border-strong` | `#5B7189` | inputs, buttons, focusable edges | ≥ 3:1 |
| `--text` | `#E6EDF3` | primary text | 14.9:1 |
| `--text-muted` | `#9FB0C3` | secondary text | 8.0:1 |
| `--accent` | `#6EA8FF` | primary actions, links, selection | 7.3:1 |
| `--accent-ink` | `#0B0F14` | text on accent fill | 8.0:1 |
| `--ok` | `#4ADE80` | success, compliant | 10.1:1 |
| `--error` | `#F87171` | errors | 6.4:1 |
| `--focus` | `#6EA8FF` | 2 px focus ring, 2 px offset | n/a |

### Deviation and status colours
| Token | Hex | Meaning | Contrast on `surface` |
|---|---|---|---|
| `--dev-missed` | `#F5A524` | missed step | 8.7:1 |
| `--dev-order` | `#A78BFA` | out-of-order step | 6.5:1 |
| `--dev-tool` | `#FB7185` | wrong tool | 6.6:1 |
| `--needs-review` | `#94A3B8` | `needs_review` (always **dashed** outline) | 6.9:1 |
| `--illustration` | `#38BDF8` | AI illustration (always **dashed** frame + badge) | 8.2:1 |

Colour is never the only signal: each deviation type also has an icon and a text label (missed = skip-forward, out-of-order = swap-arrows, wrong tool = wrench-cross).

### Overlay palette (SAM masks, by track-ID hash)
`#22D3EE #F472B6 #FACC15 #34D399 #FB923C #60A5FA #C084FC #F87171 #2DD4BF #A3E635` — fill alpha **0.35**, outline **2 px** at alpha 0.95, label chip with `--bg` at 0.8 alpha.

### Report (print/HTML export) theme: light
`--r-bg #FFFFFF · --r-text #0F172A (17.9:1) · --r-muted #475569 (7.6:1) · --r-border #CBD5E1`; deviation colours reuse the tokens above on white badges with dark text.

## 3. Typography
| Role | Font stack | Size / line | Weight |
|---|---|---|---|
| UI text | `Inter, "Segoe UI", system-ui, sans-serif` | 18 / 28 (base), 14 / 20 (small), 16 / 24 (control) | 400 / 500 / 600 |
| Headings | same | h1 32 / 40 · h2 24 / 32 · h3 20 / 28 | 600 |
| Mono (IDs, timecodes, hashes) | `"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace` | 14 / 20 | 500 |

Timecodes use `font-variant-numeric: tabular-nums` and the format `mm:ss.s` (e.g. `01:12.4`). Fonts are bundled locally (no external font requests in the exported report). Min text size is 14 px.

## 4. Spacing, radius, elevation, motion
- **Spacing scale (4 px base):** 4 · 8 · 12 · 16 · 24 · 32 · 48.
- **Radius:** cards **12 px** · buttons and inputs **8 px** · chips **999 px** · video and evidence frames **8 px** · modals **16 px**.
- **Elevation:** flat; separation by `--surface` / `--surface-2` and 1 px `--border`. One shadow only (modals/menus): `0 8px 24px rgba(0,0,0,.45)`.
- **Motion:** 120 ms ease-out for hover/focus, 160 ms for panels; no autoplay animation; `prefers-reduced-motion` disables all transitions except the progress bar.
- **Icons:** `lucide-react` (stroke 1.75, 20 px default).

## 5. Layout
| Breakpoint | Review layout |
|---|---|
| ≥ 1600 px (1080p projector, target) | 12-col grid; video + timeline = 8 cols, deviation panel = 4 cols; panel scrolls independently |
| 1280–1599 px | 7 / 5 columns |
| 1024–1279 px | 6 / 6 columns; evidence carousel collapses to one frame |
| < 1024 px | Stacked: video → timeline → panel (best effort; not a target) |

Page max width 1920 px; outer padding 24 px; header 56 px high; timeline height 148 px (two lanes of 48 px + ruler 28 px + gaps).

## 6. Components
| Component | Spec |
|---|---|
| **Button** | Primary: `--accent` fill, `--accent-ink` text, 44 px high min, 8 px radius. Secondary: transparent, 1 px `--border-strong`. Danger: `--error` outline. Disabled: 50% opacity + `aria-disabled`. |
| **Chip** | 28 px high, 999 px radius, 14 px text. Type chips fill with the type colour at 16% alpha, 1 px border in the full colour, icon + label. |
| **Card** | `--surface`, 12 px radius, 1 px `--border`, 16 px padding. Selected: 2 px `--accent` border. |
| **StageStepper** | 12 horizontal steps (wrap to 2 rows ≥ 1280 px). States: pending (muted), running (accent, animated bar), done (ok check), failed (error, expandable reason), skipped (muted, strike). |
| **CostMeter** | `$0.00 / $3.00` in mono; bar turns amber at 80% and red at 100%. |
| **Timeline** | Two lanes, 48 px each: **Expected** (SOP steps as blocks, labeled `stp_01 …`) and **Observed** (aligned intervals + hatched idle). Ruler with ticks every 5 s. Marker = 12 px diamond in type colour (dashed outline when `needs_review`). Playhead 2 px `--accent` with time label. Role `slider`, arrow keys move by 1 frame, shift+arrow by 1 s. |
| **DeviationCard** | Header: type chip · severity (High has a filled dot) · timecode (mono, clickable) · confidence bar. Body: explanation (≤ 2 sentences). Footer: Accept · Dismiss · Add note. |
| **EvidenceFrame** | **Solid** 2 px `--text` border, tag top-left `EVIDENCE · real frame · mm:ss.s`, SAM masks and `#id concept` labels visible, caption bar with step id. Click opens a lightbox with zoom and a "Show without overlay" toggle. |
| **IllustrationFrame** | **Dashed** 2 px `--illustration` border, diagonal corner ribbon, permanent badge `AI ILLUSTRATION · NOT EVIDENCE` (also burned into the pixels), caption "What correct looks like". Never placed inside the evidence carousel. |
| **Banner** | Info (accent), Warning (amber), Error (red). Icon + text + optional action. Role `status` (info) or `alert` (error). |
| **Toast** | Bottom-left, 4 s, polite live region; errors persist until dismissed. |
| **EmptyState** | Icon, one-line title, one-line help, one primary action. |
| **Modal** | 16 px radius, focus trapped, `Esc` closes, returns focus to the trigger. |
| **Dropzone** | Dashed `--border-strong`, 160 px min height, drag-over fills `--surface-2`; shows file name, size, duration after drop. |
| **StepEditorRow** | Drag handle, step number, text input, tool/part chips, Critical toggle (shield icon), ordering select; error state shows inline message under the row. |

## 7. Overlay rendering (video canvas and evidence frames)
- Draw order: masks → outlines → labels → timestamp burn-in (evidence only).
- Label: `#trk_007 screwdriver` in mono 12 px, chip padding 4 × 2, placed at the mask's top-left, auto-shifted to avoid collisions (max 2 shifts, then stacked).
- Evidence burn-in: bottom bar 36 px, `--bg` at 0.8 alpha: `step stp_05 · 01:12.4 · dev_002`.
- Performance: p95 canvas draw ≤ 8 ms with 12 tracks at 720p; polygons simplified with tolerance 1.5 px at 720p.

## 8. Accessibility
- WCAG 2.2 AA contrast for all text and UI boundaries; focus ring visible on every interactive element (2 px `--focus`, 2 px offset).
- All review actions available by keyboard (`02_AppFlow.md` §2.4); a `?` dialog lists shortcuts.
- Timeline exposes `aria-valuetext` such as "01:12.4, step 5 of 11, wrong tool flagged".
- Images have meaningful `alt` (evidence: "Evidence frame at 01:12.4, step 5, hand holding Phillips screwdriver"); illustrations: "AI illustration, not evidence: …".
- Live regions announce stage changes (polite) and failures (assertive).
- Respect `prefers-reduced-motion` and `prefers-color-scheme` is not honoured for the app (dark only) but IS honoured for the exported report (light default, dark not needed).

## 9. Copy and tone
| Situation | Wording |
|---|---|
| Deviation titles | "Step *3* skipped", "Step *5* done before step *4*", "Wrong tool at step *6*: Phillips screwdriver expected, flat-head used" |
| Low confidence | "Needs review: the evidence is not conclusive." |
| Not recognized | "This video does not match the SOP closely enough to check it." |
| Illustration caption | "What correct looks like (AI illustration, not evidence)" |
| Empty deviation list | "No deviations found. Every step was observed in order." (only when status is `done` and the run is not `partial`) |
| Partial | "Some analysis was unavailable: *Illustrations*. Everything else is complete." |

Voice: plain, specific, no model hype, no blame of individuals (never "the operator failed").

## 10. Design tokens delivery
`web/src/ui/tokens.css` declares the variables above on `:root`; Tailwind `theme.extend.colors` maps to them (`bg-surface`, `text-muted`, `border-strong`, …). Components never use raw hex. The report template (`src/pw/report/templates/*`) imports the light-theme subset inline (no external CSS).
