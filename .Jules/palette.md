## 2024-05-12 - Ensure hover-revealed actions are keyboard accessible
**Learning:** Icon-only buttons that are only revealed on hover (using `opacity-0 group-hover:opacity-100`) are invisible to keyboard users when they navigate via tab. Adding `focus:opacity-100` alongside `focus-visible:ring-2` is critical to make these actions accessible without a mouse.
**Action:** Always verify hover-revealed elements have corresponding `focus` or `focus-visible` styles so they appear when a keyboard user tabs to them.
