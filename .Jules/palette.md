## 2024-06-16 - Accessible Tooltips for Icon-only Buttons
**Learning:** Icon-only buttons with `aria-label` are accessible to screen readers, but sighted users lack context on hover. Adding a matching `title` attribute serves as a lightweight, native tooltip. Additionally, custom buttons often lack visible focus rings, making keyboard navigation difficult.
**Action:** Always pair `aria-label` with a matching `title` attribute on icon-only buttons, and ensure `focus-visible:ring-2` (and related classes) are applied for keyboard accessibility.
