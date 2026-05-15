# SelfFork — Design System v2 (Minimalist, User-First)

## 1. Who is this for?

**A person — not necessarily an engineer — who wants to ship a project.**

They open SelfFork, say what they want, and SelfFork builds it. They never see audit logs, model slugs, daemon heartbeats, tier metrics, or token counts. Those exist; SelfFork handles them behind the scenes. The UI is a calm, confident surface that responds to intent.

Reference vocabulary: **Lovable.dev**, **Cursor IDE**, **Replit Agent**, **ChatGPT canvas**, **Linear v1**, **Notion's first screen**. Reject: dashboards, cockpits, KPI rows, engineering audit panels, tier breakdowns, anything with the word "JSONL" in it.

## 2. Five Screens, Nothing More

The entire product is five screens. Anything else is hidden behind "Advanced".

1. **Home** — one big input: *"What are you building?"* + a strip of recent projects.
2. **Workspaces** — card grid of the user's projects (one card per project, image + name + one-line status).
3. **Connections** — list of the AI assistants the user can plug in (Claude, ChatGPT, Gemini, etc). Each row: name, simple Connect/Disconnect, a soft "Active" check when ready.
4. **Settings** — single page of high-level toggles (light mode, notifications, save-to-cloud, privacy). Engineering options live behind a small "Advanced" link at the bottom.
5. **Talk** — chat with the agent for the active workspace. Conversation on the left, the thing being built (preview / file / canvas) on the right.

There is **no Dashboard**, no Fleet view, no Body tab, no audit timeline, no token usage chart in the default flow. Those things still exist as power-user surfaces, but a normal user must never see them.

## 3. Color & Surface

**Light mode only.** Cream-on-white, slate text. No dark mode.

| Token | HSL | Use |
|---|---|---|
| `background` | 0 0% 99% | Page (very soft off-white) |
| `surface` | 0 0% 100% | Cards (a hair brighter than background) |
| `surface-muted` | 240 4% 96% | Sidebar, hover, soft fills |
| `foreground` | 240 10% 14% | Primary text |
| `foreground-muted` | 240 4% 50% | Secondary text |
| `border` | 240 6% 92% | Hairline (rare) |
| `accent` | 217 91% 55% | One CTA color — used sparingly |
| `success` | 142 71% 42% | A check or "Active" tick |

**Rules:**
- Tonal layers over borders. `background → surface-muted → surface`. The eye finds the active surface, not because of an outline but because of softness contrast.
- One CTA color per screen. If everything is blue, nothing is. Reserve `accent` for the single primary action.
- No "destructive" red on default screens. Destructive only appears inside a confirmation modal.

## 4. Typography

- **Inter**, 4 sizes max:
  - `display` 32 / 600 / -0.02 (page-level intent line: "What are you building?")
  - `heading` 20 / 600 / -0.01 (card titles, settings groups)
  - `body` 16 / 400 / 0 (default reading text, slightly larger than engineering UI so it feels approachable)
  - `caption` 13 / 500 / 0 (timestamps, tiny metadata — never uppercase, no `tnum`)
- **No monospace anywhere on the default flow.** A user does not want to see paths or model IDs. If a monospace string truly must appear (e.g., a copied snippet inside Talk), then it gets a subtle background and a copy button — never as decoration.

## 5. Spacing

- 8 px base unit. Everything snaps to it.
- Page gutter 40 px on desktop (more breathing room than engineering cockpit).
- Card padding 24 px.
- Vertical rhythm between cards: 24 px.
- Topbar 64 px. Sidebar 240 px (collapses to icons at < 1280 px).

## 6. Components

### The big input (Home only)

A single, generous text field. Placeholder reads *"What are you building?"* in `display` typography, `foreground-muted`. The field is borderless until focus; on focus, a soft 1 px `accent` ring appears and a paper-plane send icon fades in on the right. Submitting routes to a new workspace and opens **Talk**.

### Card (workspaces, settings groups)

Soft, no border. Background `surface`. Shadow: `0 2px 8px rgba(15, 23, 42, 0.04)`. Radius 16 px (a bit more generous than the engineering version — feels friendlier). Hover: lifts 2 px, shadow ramps slightly. No tooltips on hover; if a card needs an explanation, the explanation is part of its body, not a hover overlay.

### Button

- **Primary**: solid `accent`, white text, radius 12 px, 12 / 20 padding. One per screen.
- **Secondary**: text-only on `foreground-muted`, no background, no border. Hover gets `surface-muted` background.
- **No outlined buttons.** They add visual weight without status. We have primary (intent) and secondary (link-like).
- **Disabled** is `foreground-muted` at 50 %. Never grey-on-grey.

### Status indicator

A single small green dot + the word "Active" (lowercase). That's the entire vocabulary of "this is working." For "not yet connected", show a `foreground-muted` "Not connected" link styled like a CTA — it invites action, doesn't announce a problem.

There is no "expired", "expiring soon", "rate limited", "stale heartbeat" jargon on the default flow. Those map to the same "Not connected" + a one-sentence explanation when the user actually opens the row.

### Connection row (Connections page)

One row per AI provider. Each row contains:

- Provider name in `heading` typography (e.g., "Claude").
- A subtle one-line description (e.g., "Anthropic's flagship coding assistant").
- A right-aligned action: either a primary `Connect` button, or a green dot + "Active" + a tiny "Manage" text link.

That's it. No model selector, no token counter, no quota bar. If the user clicks "Manage", they get a modal with two sentences and a "Disconnect" link.

### Settings rows

Each row is a single toggle or a single link, vertically stacked. Use real prose for the label (e.g., "Send me a notification when a project finishes" — not "Notifications: on/off"). Group rows with `heading` titles and 24 px vertical gaps. **No tabs**, no nested settings panes.

At the bottom of Settings there is one small text link: *"Advanced settings →"* in `foreground-muted`. That's where engineering toggles (vision model swap, audit verbosity, daemon mesh) live — out of sight by default.

### Modal

Centered, max 480 px wide, 32 px padding. Soft shadow. Backdrop is `rgba(15, 23, 42, 0.32)` — visible but not dramatic. Two-button footer: primary right, secondary text-link left.

### Empty state

Always a single sentence in `foreground-muted` and a primary CTA below. Example for an empty Workspaces: "*Nothing here yet. Start something.*" + a primary button "**New project**". No illustrations, no marketing copy.

## 7. Sidebar

Five items, in this order:

1. Home (house icon)
2. Workspaces (folder icon)
3. Talk (chat bubble icon)
4. Connections (link icon)
5. Settings (gear icon)

That's all five top-level icons. No project list expansion under the sidebar — a user clicks "Workspaces" to see their projects. The active item gets `accent` text + an 8 % `accent` background block. The brand at the top is just the word "SelfFork" in `heading` typography — no logo mark experiments.

## 8. Topbar

The topbar is intentionally almost empty.

- Left: the current workspace name in `body` typography (clickable, opens a switcher). Nothing else.
- Right: a small avatar circle (the user's initials) — clicking it opens a tiny menu with "Settings" and "Sign out".

That's it. No search, no audit dir pills, no online indicator. The product is in a working state at all times; SelfFork handles offline / reconnect internally and only surfaces a banner if action is required from the user.

## 9. Motion

Soft and slow. Anything snappy here would feel engineering.

- Page enter: 220 ms ease-out, 12 px up.
- Card hover lift: 160 ms ease-out.
- Button press: 90 ms scale 0.97 then return.
- Status check tick: 320 ms with a tiny bounce when transitioning from grey to green.
- Talk pane streaming text: 1.2 ch / frame typewriter; no flashing cursor.

## 10. Iconography

Lucide only. 20 px in nav. 18 px inline. Outline (never filled). Stroke 1.75. Color inherits.

## 11. The hard rules

**Do**

- Treat the user like a curator of their projects, not an operator of a server fleet.
- Hide every engineering metric by default. The system is responsible for the metric; the user is responsible for the outcome.
- Use a single sentence wherever a settings page would normally use a noun ("Notifications").
- Make every screen pass the *Lovable test*: could a non-developer use this in their first minute, with no instruction?

**Don't**

- Don't show audit timelines, JSONL paths, tier numbers, model slugs, token counts, machine IDs, or HMAC anything on a default screen.
- Don't include the words "configure", "manage", "monitor", "fleet", "daemon", "audit", "session" on the default flow.
- Don't add tabs inside pages. If a page has tabs, it's two pages.
- Don't show more than one primary action on a screen.
- Don't ever, ever ship a Dashboard. SelfFork shows you the thing you're building, not the system that builds it.
