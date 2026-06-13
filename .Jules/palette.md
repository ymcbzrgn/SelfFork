## 2024-06-13 - Focus Visibility on Hover Actions
**Learning:** Elements hidden behind hover states (`opacity-0 group-hover:opacity-100`) are completely invisible to keyboard-only users who tab onto them if they lack explicit focus styling.
**Action:** Always include `focus-visible:opacity-100` and standard focus ring utilities (`focus-visible:ring-2`, etc.) on interactive elements that are visually hidden by default.
