
## 2024-06-10 - Custom Button Accessibility in Topbar
**Learning:** Many custom `<button>` elements and icon-only interactive elements in the codebase lack proper keyboard focus indicators, making them difficult for keyboard users to navigate. Additionally, icon-only buttons often lack `title` tooltips, which are critical for sighted mouse users to understand the button's action if they don't use screen readers (which rely on `aria-label`).
**Action:** Always manually apply focus states (`focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background`) to custom `<button>` elements. Ensure every icon-only button has a `title` attribute that matches its `aria-label` to provide visual tooltips.
