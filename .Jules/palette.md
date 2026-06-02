## 2024-06-02 - Ensure focus-visible on custom elements
**Learning:** Custom `<button>` and `<Link>` elements must manually include `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background` to support keyboard navigation accessibly, because the app relies on shadcn-style focus rings for accessible navigation.
**Action:** Always add these focus-visible tailwind utilities to custom interactive elements, and verify via keyboard navigation tests.
