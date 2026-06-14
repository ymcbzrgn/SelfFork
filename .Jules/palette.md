## 2026-06-14 - Tooltips for Icon-Only Buttons
**Learning:** `aria-label` alone is insufficient for icon-only buttons. While `aria-label` makes them accessible to screen readers, sighted users navigating visually also rely on hover context, which is easily provided via the standard HTML `title` attribute.
**Action:** When creating or modifying icon-only buttons, always include a standard HTML `title` attribute matching the `aria-label` to ensure hover context is available for sighted users.
