## 2024-11-21 - Focus Visible Styles for Keyboard Navigation
**Learning:** Custom interactive elements like custom `<button>` and `<Link>` components often miss default browser focus outlines when using Tailwind CSS resets, hindering keyboard navigation.
**Action:** Always manually apply the standard Tailwind focus ring pattern (`focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background`) to all custom interactive elements, or prefer using the provided shadcn/ui generic `Button` component when possible.
