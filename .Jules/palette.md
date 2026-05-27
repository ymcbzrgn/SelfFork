
## 2026-05-27 - Keyboard Navigation Focus States
**Learning:** Custom UI buttons in headers and tools often lack focus states. This significantly hinders keyboard accessibility, as standard Tailwind forms reset styles (`outline-none`) typically strip native focus rings.
**Action:** Always ensure `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring` is applied to `<button>` elements that don't inherit from a core UI component (`<Button>`) to maintain keyboard navigation visibility.
