# KnowSayin Design System

Source of truth for the public KnowSayin website visual language.

## UI/UX Audit

- Layout: the previous page stacked every section vertically, so the tool felt longer than the actual task. The editor and result should sit side by side on desktop because the product value is comparison.
- Typography: headings were heavy and slightly inflated for a compact utility. Body copy and labels need clearer hierarchy, calmer weights, and more readable line lengths.
- Spacing: top sections competed with the editor. The tool surface should be visible in the first viewport and keep labels close to their controls.
- Color: the dark gradient, grid, glass panels, and rainbow action button made the page read like a generic AI SaaS template. The new palette should be neutral, editorial, and product-like with restrained accent colors.
- Buttons: pill links and a full-width gradient button looked promotional. Buttons should use stable dimensions, plain states, and strong affordance without animation.
- Cards: the old UI used several soft glass card shapes. Use one purposeful workbench surface and avoid nested card styling.
- Navigation: top actions should feel like a product utility header, not floating badges. Quota must stay visible but quiet.
- Mobile: the old mobile version was functional, but the header consumed valuable height and the action stack felt heavy. The mobile layout should put the input first and keep actions easy to thumb.
- States: loading, error, success, empty, disabled, and quota/refill states need visible but calm treatment.

## Product Direction

KnowSayin is a prompt-cleaning utility, not a magical AI showcase. The interface should feel like a sharp writing instrument:

- direct
- compact
- trustworthy
- privacy-conscious
- bilingual-friendly
- good for repeated daily use

The first screen should be the tool, not a marketing hero.

## Color

Use a quiet neutral base with multiple restrained accents. Avoid large purple/blue gradients, glassmorphism, decorative orbs, and heavy background effects.

### Light Theme

```text
canvas          #f5f7f4
surface         #ffffff
surface-muted   #eef2ed
field           #fbfcf8
ink             #161817
ink-soft        #343a37
muted           #68726d
muted-strong    #4c5651
line            #d9e1da
line-strong     #b7c3ba
accent          #2d6cdf
accent-strong   #1f55b7
success         #267360
warning         #a86821
danger          #c9493d
focus           #7da6f4
```

### Dark Theme

```text
canvas          #101211
surface         #171a18
surface-muted   #202520
field           #121513
ink             #f2f5ef
ink-soft        #dce4dc
muted           #9aa79f
muted-strong    #bdc8c0
line            #303831
line-strong     #465047
accent          #8ab4ff
accent-strong   #a9c8ff
success         #7cc9aa
warning         #e1a95f
danger          #ff8b7f
focus           #9ec0ff
```

## Typography

- Font stack: `ui-sans-serif`, `system-ui`, `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `sans-serif`.
- Monospace stack for machine codes and counters: `ui-monospace`, `SFMono-Regular`, `Menlo`, `Consolas`, `monospace`.
- Letter spacing is always `0`.
- Page title: 42px desktop, 30px mobile, line-height 1.04, weight 760.
- Section label: 12px, uppercase, weight 760, muted.
- Body: 15-16px, line-height 1.55, weight 450-520.
- Textarea: 15px desktop, 16px mobile to avoid iOS zoom, line-height 1.58.
- Buttons: 14px, weight 700.

## Spacing

Use a 4px base scale:

```text
2  = 8px
3  = 12px
4  = 16px
5  = 20px
6  = 24px
8  = 32px
10 = 40px
12 = 48px
```

Rules:

- Page shell: 24px mobile horizontal padding, 32px desktop horizontal padding.
- Header to workbench: 24px desktop, 16px mobile.
- Workbench inner padding: 16px mobile, 18px desktop.
- Control gaps: 10-14px.
- Labels sit 8px above their controls.

## Radius

- Buttons: 8px.
- Inputs/textareas: 8px.
- Tool surfaces/cards: 8px.
- Small pills/status items: 999px only when they are truly compact metadata.

## Shadows

Shadows must be structural, not decorative:

```text
shadow-soft: 0 1px 2px rgba(16, 24, 20, 0.06), 0 16px 40px rgba(16, 24, 20, 0.08)
shadow-raised: 0 12px 28px rgba(16, 24, 20, 0.12)
dark-shadow-soft: 0 18px 44px rgba(0, 0, 0, 0.28)
```

Avoid glowing shadows except focus rings.

## Buttons

Primary:

- Solid accent background.
- White text in light theme, dark ink in dark theme only if contrast is better.
- 46-48px height for main actions.
- No animated shine or gradient sweep.

Secondary:

- Transparent or muted surface.
- 1px border.
- Clear hover/active/disabled states.

Metadata links:

- Compact pill style is allowed for `Download`, `GitHub`, and quota.
- Keep quota readable but not dominant.

## Forms

- Textareas are the core product surface.
- The input and result fields should have equal visual importance, with result receiving a subtle success-side border only after content exists if needed.
- Placeholder text should be readable but clearly secondary.
- Focus ring: 2px outer ring in focus color with no layout shift.
- Disabled controls keep shape and reduce opacity only slightly.

## Workbench

Desktop:

- Two-column comparison layout.
- Left column: original.
- Right column: result.
- Actions align below their related columns.
- Status spans the workbench width.

Mobile:

- Single column.
- Input, primary action, result, secondary actions, status.
- Hide long desktop explainer copy below 620px.
- Keep touch targets at least 44px high.

## Responsive Rules

```text
<= 620px: compact mobile; no subtitle/desktop strip; one column; textarea min height 184px.
621-899px: tablet; one column but wider spacing.
>= 900px: desktop workbench uses two columns.
>= 1180px: max content width 1120px; do not stretch textareas beyond comfortable reading width without two columns.
```

## States

- Empty: quiet placeholder, disabled copy button.
- Loading: disable primary action and show status text; no flashing animation.
- Success: status uses success color and result text is immediately scannable.
- Error: status uses danger color, no modal.
- Quota empty: extra panel appears as a functional refill section, not a promotional banner.
- Linked machine: show machine code in monospace metadata.

## Accessibility

- Preserve IDs and labels for existing JavaScript behavior.
- Maintain visible labels for both textareas.
- Focus states must be keyboard-visible.
- Respect `prefers-reduced-motion`.
- Respect `prefers-color-scheme`.
- Hidden QA override is allowed with `?theme=light` or `?theme=dark`; default behavior must still follow the user's system preference.
- Keep Chinese and English strings from overflowing on mobile.

## Implementation Guardrails

- Do not change routes, API paths, form IDs, event handlers, quota logic, or backend code.
- Do not add tracking, analytics, third-party fonts, or external UI libraries.
- Do not store prompt contents, transcripts, or service logs in repo files.
- Visual changes should live in `site/index.html` and `site/static/site.css` unless a state truly requires JavaScript.
