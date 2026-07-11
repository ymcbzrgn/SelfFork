## 2024-06-18 - Icon-Only Button Accessibility Pattern

**Learning:** When using custom icon-only HTML `<button>` elements (rather than Shadcn UI components), it's critical to include both an `aria-label` for screen readers and a matching `title` attribute for sighted users (tooltips). Furthermore, custom buttons often lack default focus states, making keyboard navigation difficult.

**Action:** Whenever creating or reviewing custom icon-only buttons, ensure they have:
1. `aria-label` describing the action.
2. `title` attribute matching the `aria-label`.
3. `focus-visible` classes (e.g., `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background`) applied for keyboard users.
