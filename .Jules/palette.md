## 2024-05-30 - Accessible Hover-Only Icon Buttons
**Learning:** Hover-only icon buttons (`opacity-0` to `opacity-100`) in Kanban cards and similar components become completely inaccessible to keyboard users because they remain invisible during tab focus. This hides interactive functionality from a11y tools and keyboard navigators.
**Action:** Always pair `group-hover:opacity-100` with `focus-visible:opacity-100` and standard focus rings (`focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`). Add `aria-label` to icon-only buttons.
