# SelfFork — Design System v3 (P+Prompt Engineer, power-aware sade)

> **Source of truth:** `docs/decisions/ADR-006_v2_Pivot.md` §5.
> Bu doküman ADR-006'nın **executable design spec**'idir. Stitch'e feed edilir, `apps/web/` implementasyonunda referans alınır.
> Önceki sürümler (v1 cockpit / v2 non-engineer minimalist) **superseded**.

---

## 0. Persona ve Tasarım Kompası

### 0.1 Hedef Kullanıcı: P + Prompt Engineer

- **Profil:** Senior level operator (10+ yıl) **veya** bilgisayar-okuryazar non-engineer.
- **Yapar:** Proje yönetir (Jira/kanban), prompt yazar, CLI'leri yönlendirir, çıktıyı test eder, sonraki prompt'u yazar.
- **Yapmaz:** Kod yazmaz. Doğrudan editörde çalışmaz. Terminal'de uzun saatler geçirmez.
- **Çoklu proje paralel sürer.** Mobile-aware (Telegram bridge).

### 0.2 Stil Tek Cümle

> **Linear v1 sade hiyerarşi + Replit Agent canlılığı + Vercel dashboard temizliği**, "light enterprise" tonda. Cursor/Lovable "magic-tek-input" değil; PRD §8.5 mühendis cockpit'i de değil. **Power user görünürlüğü açık, gürültü kapalı.**

### 0.3 Tasarım İlkeleri (kompass)

| İlke | Anlam |
|---|---|
| **Calm hierarchy** | Bir ekranda bir anchor element. Diğer elementler küçük, kenarda, ikincil. |
| **Power, not pomp** | Slider/threshold/audit gibi mühendis süslemeleri yok; subscription quota / live status / Jr notları gibi **gerçek power surface** açık. |
| **Single-operator vibe** | Multi-user UI affordance yok (avatar grid, user picker, team toggle yok). Kişisel atölye hissi. |
| **Server-app aesthetic** | "Local app" hissi (full-window, sidebar fixed). Mobil ikincil (Telegram halleder). |
| **Audit hidden by default** | Audit/log/event timeline Advanced toggle arkasında. Default ekran sade. |
| **Backed by truth** | Mock yok. Boş state için "henüz veri yok" göster. |
| **Tabular discipline** | Sayısal değerler `tabular-nums`. Layout shift yok. |
| **Latin pacing** | Türkçe etiketler tercih edilir; İngilizce sadece kanonik terim. |

### 0.4 Kabul Kriteri (Stitch'e brief)

5 ekran üretilecek. Her ekran:
- 1280px desktop genişlikte default. Mobile responsive ikincil.
- Light mode varsayılan. Dark mode opsiyonel (Settings'ten).
- Sidebar 240px fixed sol; collapse 64px (`[` shortcut).
- Topbar 56px üst (workspace switcher + Jr status + bildirim).
- Asıl içerik scroll.
- Card-based; tonlama incelmiş (gri-100 / 50 / white tabanlı).
- Border-radius `rounded-lg` (12px) varsayılan; `rounded-xl` hero kartlar için.
- Shadow disiplinli: `shadow-sm` cards, `shadow-md` modals.
- Tipografi Inter; sayısal yerler tabular-nums.

---

## 1. Design Tokens

### 1.1 Renk Paleti

**Light mode (default):**

| Token | Hex | Anlam |
|---|---|---|
| `--bg-base` | `#FAFAFA` | Sayfa arka plan |
| `--bg-surface` | `#FFFFFF` | Card / panel zemin |
| `--bg-subtle` | `#F4F4F5` | Group block / sidebar |
| `--bg-muted` | `#E4E4E7` | Disabled, divider |
| `--text-primary` | `#18181B` | Başlık, gövde |
| `--text-secondary` | `#52525B` | Açıklama, ikincil |
| `--text-tertiary` | `#A1A1AA` | Placeholder, ikon disabled |
| `--text-inverse` | `#FFFFFF` | Primary buton üstü |
| `--border-default` | `#E4E4E7` | Card border |
| `--border-strong` | `#D4D4D8` | Input border, divider |
| `--primary-500` | `#004AC6` | Tek primary (Stitch'ten gelen `221 100% 39%`) |
| `--primary-600` | `#003BA5` | Hover state |
| `--primary-50` | `#E6EEFA` | Pill bg, light accent |
| `--success-500` | `#16A34A` | "Active", "Connected", "Online" |
| `--success-50` | `#DCFCE7` | Success pill bg |
| `--warning-500` | `#EAB308` | "Quota düşük", "Pending" |
| `--warning-50` | `#FEFCE8` | Warning pill bg |
| `--danger-500` | `#DC2626` | "Disconnected", "Error", "Destructive pending" |
| `--danger-50` | `#FEE2E2` | Danger pill bg |
| `--live-pulse` | `#DC2626` | Live indicator dot (red, pulse animation) |

**Dark mode opsiyonel** — Settings'te kullanıcı seçer. Aynı semantic token mapping; bg-base → `#09090B`, surface → `#18181B`, text-primary → `#FAFAFA` vs. (Default ship'te dark mode v3 first-cut'ta deferred.)

### 1.2 Tipografi

| Token | Family | Size | Weight | Line | Letter |
|---|---|---|---|---|---|
| `display-lg` | Inter | 30px | 700 | 1.2 | -0.02em |
| `display-md` | Inter | 24px | 700 | 1.25 | -0.02em |
| `heading-lg` | Inter | 20px | 600 | 1.3 | -0.01em |
| `heading-md` | Inter | 16px | 600 | 1.4 | 0 |
| `body-md` | Inter | 14px | 400 | 1.5 | 0 |
| `body-sm` | Inter | 13px | 400 | 1.45 | 0 |
| `label-md` | Inter | 12px | 500 | 1.4 | 0.02em |
| `label-sm` | Inter | 11px | 500 | 1.4 | 0.05em |
| `mono-md` | JetBrains Mono | 13px | 400 | 1.5 | 0 |
| `numeric-md` | Inter (tabular-nums) | 14px | 600 | 1.4 | 0 |

Display fontu eklenmez. Tüm hiyerarşi Inter, weight & size varyasyonu.

### 1.3 Spacing Scale

`xs=4` `sm=8` `md=12` `lg=16` `xl=24` `2xl=32` `3xl=48` `4xl=64`

(Mevcut `tailwind.config.ts` Material-3 spacing tokenları korunur, semantic map ekstradır.)

### 1.4 Radius

`sm=6` `md=8` `lg=12` (varsayılan) `xl=16` `full=9999`

### 1.5 Shadow

| Token | Değer | Kullanım |
|---|---|---|
| `shadow-xs` | `0 1px 2px rgba(0,0,0,0.04)` | Subtle card |
| `shadow-sm` | `0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)` | Default card |
| `shadow-md` | `0 4px 6px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.06)` | Hover, popover |
| `shadow-lg` | `0 10px 15px rgba(0,0,0,0.05), 0 4px 6px rgba(0,0,0,0.04)` | Modal, dialog |

### 1.6 İkon Sistemi

- **Lucide Icons** (zaten kurulu).
- Size: `16` küçük (inline), `18` default, `20` button, `24` hero.
- Stroke width 1.75.
- Material Symbols **opsiyonu reddedildi** (build size).

### 1.7 Animasyon

- Cubic-bezier `(0.16, 1, 0.3, 1)` ease-out-quint
- Süreler: `fast=120ms` (hover, focus), `default=180ms` (slide, fade), `slow=300ms` (modal enter)
- `prefers-reduced-motion` saygı

---

## 2. Bilgi Mimarisi (IA) + Navigasyon

### 2.1 Sidebar

```
┌────────────────────────────┐
│ ⊕ SelfFork            ◀ [  │  ← Logo + collapse btn
├────────────────────────────┤
│                            │
│  ▢ Dashboard           ⌘1  │  ← active state: bg-primary-50
│                            │
│  ▢ Workspaces              │  
│    ▸ ProjectX  ●           │  ← live indicator
│    ▸ ProjectY              │  
│    ▸ ProjectZ              │  
│    + New project           │  ← dashed border outline button
│                            │
│  ▢ Talk                ⌘2  │
│                            │
│  ▢ Connections         ⌘3  │
│                            │
│  ▢ Settings            ⌘4  │
│                            │
├────────────────────────────┤
│                            │
│  Self Jr                 │  ← Footer
│  ● Online · gemma-4 @ mac  │  ← model + endpoint kısa
│                            │
└────────────────────────────┘
```

- Genişlik: 240px açık, 64px collapsed (ikon only).
- Toggle: `[` keyboard shortcut + topbar'da hamburger button.
- Active state: text primary + bg primary-50 + sol kenarda 3px primary-500 bar.
- "Workspaces" sub-list: max 5 görünür + "Show all (N)" link >5'te.
- Footer mini status: Self Jr online + model slug + endpoint host.

### 2.2 Topbar

```
┌────────────────────────────────────────────────────────────────┐
│ ☰  [Workspace ▼]   Search...    🔔 3   ● Live  ⚙  ?  ⊙ Y │
└────────────────────────────────────────────────────────────────┘
```

- Yükseklik: 56px.
- Sol: hamburger (mobile/collapse trigger), workspace switcher dropdown.
- Orta: Cmd+K search (modal trigger).
- Sağ:
  - Bildirim çanı (badge = pending destructive count + telegram unread)
  - Live indicator: pulsing red dot + "Live" label (Jr active CLI varsa)
  - Settings ikon kısayolu
  - Help (?) → kısayollar overlay
  - User affordance: single-letter avatar "Y" — multi-user UI değil, sadece "siz" işareti

### 2.3 Cmd+K Komut Paleti

Slash commands ve hızlı geçişler:
- `/workspace ProjectY` — workspace switch
- `/cli claude` — sticky CLI override (active workspace)
- `/pause` — Self Jr'ı durdur (tüm active CLI subprocess SIGTERM)
- `/resume` — devam
- `/talk` — Talk ekranına git
- `/note <text>` — aktif workspace'e not ekle
- `/finetune` — Settings > Fine-tune'a git
- `>` ile araştırma (örn. `> supabase auth`) — RAG sorgu

---

## 3. Component Library

### 3.1 Mevcut shadcn primitives (korunur)

`Button` · `Input` · `Label` · `Switch` · `Separator` · `Tooltip` · `Dialog` · `Select` · `Alert` (custom)

### 3.2 Yeni component'ler (v3)

| Component | Amaç | Ekran |
|---|---|---|
| `<QuotaGaugeCard />` | Provider subscription quota ring + remaining + reset window | Dashboard, Connections |
| `<LiveLoopStatus />` | Hero card: "Jr şu an X workspace'te Y CLI ile Z yapıyor" | Dashboard |
| `<ActivityFeedItem />` | Compact event row (icon + label + time + project) | Dashboard |
| `<ProjectCard />` | Kanban özet + last activity + status pill | Dashboard |
| `<WorkspaceHeader />` | Workspace title + status + actions dropdown | Workspace |
| `<KanbanBoard />` | 4-column drag-drop (Backlog / In progress / Review / Done) | Workspace |
| `<KanbanCard />` | Single task card (title + tags + assignee + estimate) | Workspace |
| `<LiveRunTheater />` | 3-pane composite (CLI output / screenshot timeline / Jr thought) | Workspace |
| `<CLIOutputPane />` | Terminal stream + ansi colors + auto-scroll lock | Workspace (theater) |
| `<ScreenshotTimeline />` | Horizontal strip + hover popover preview | Workspace (theater) |
| `<JrThoughtBubble />` | Compacted Speaker thought summary + "raw" toggle | Workspace (theater) |
| `<ProjectNotes />` | Markdown editor (Tiptap or similar) + auto-save | Workspace |
| `<ChatMessage />` | operator / Self Jr bubble + timestamp + workspace pill | Talk |
| `<ChatComposer />` | Multiline input + slash chips + attach | Talk |
| `<ProviderCard />` | Single CLI: status dot + sub-info + actions | Connections |
| `<TelegramCard />` | Bot config + webhook + log preview | Connections |
| `<FineTuneSection />` | Dataset + hyperparams + start | Settings |
| `<ModelEndpointForm />` | URL + protocol + auth + health | Settings |
| `<AdvancedToggle />` | Collapse panel — hidden power user controls | Settings |
| `<PendingConfirmationBanner />` | Destructive eylem 4h soft confirm timer | All workspaces, Dashboard |

### 3.3 State patterns

**Loading:**
- Skeleton blocks, not spinners. Card shape preserved.
- `<Skeleton variant="card" />` · `<Skeleton variant="text" lines={3} />`

**Empty:**
- Centered illustration (line-art, Lucide-style ikon büyütülmüş)
- Başlık (örn. "Henüz workspace yok")
- 1 cümle açıklama
- Primary CTA buton

**Error:**
- Inline danger Alert + retry CTA
- Toast destructive (5sn auto-dismiss + manual close)

**Live update:**
- Pulse dot (red 500ms cycle) + "Live" badge
- Last update timestamp ("2 sn önce", "12 dk önce") — server time, client format

---

## 4. Ekran 1 — Dashboard

### 4.1 Amaç

operator giriş yapar yapmaz **"Jr şu an ne yapıyor, kaynaklar ne durumda, hangi projeye girmeliyim"** üç sorusuna cevap alır.

### 4.2 Layout (1280px desktop, dikey scroll)

```
┌──────────────────────────────────────────────────────────────────┐
│  Topbar (sticky)                                                 │
├──────┬───────────────────────────────────────────────────────────┤
│ Side │  Page content (max-w-7xl mx-auto px-6 py-8)               │
│ bar  │                                                            │
│      │  ┌─ Header ────────────────────────────────────────┐     │
│      │  │ Dashboard                                        │     │
│      │  │ Sabah, operator. Self Jr 3 projeyi takip ediyor.  │     │
│      │  └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │  ┌─ Sec 1: CLI Quota Strip ────────────────────────┐     │
│      │  │  (5 QuotaGaugeCard horizontal flex, gap-4)       │     │
│      │  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │     │
│      │  │  │claude│ │codex │ │gemini│ │minmax│ │ glm  │  │     │
│      │  │  │  ◐   │ │  ⬤  │ │  ◓   │ │ off  │ │ off  │  │     │
│      │  │  │ 67%  │ │ 92%  │ │ 23%  │ │ –    │ │ –    │  │     │
│      │  │  │4h12m │ │5h   │ │1d 8h │ │      │ │      │  │     │
│      │  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘  │     │
│      │  └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │  ┌─ Sec 2: Live Loop Status (hero) ─────────────────┐     │
│      │  │ 🔴 LIVE                                          │     │
│      │  │ ProjectX  ·  Claude CLI  ·  turn 47/∞  ·  12m   │     │
│      │  │                                                  │     │
│      │  │ "Login flow testliyor — Supabase auth ekranını   │     │
│      │  │  inceliyor, password placeholder doğrulanıyor."  │     │
│      │  │                                                  │     │
│      │  │                            [Open Workspace →]    │     │
│      │  └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │  ┌─ Sec 3: Recent activity (compact 5 row) ────────┐     │
│      │  │ Recent activity                                  │     │
│      │  │ ────────────────────────────────────────────    │     │
│      │  │ ✓  5 dk      ProjectX  TASK-12 tamamlandı       │     │
│      │  │ 🔔 12 dk     ProjectY  Supabase auth gerekli    │     │
│      │  │ 🤖 47 dk     ProjectX  Claude → Codex (quota)   │     │
│      │  │ ⚠ 1 saat    ProjectX  Destructive pending (3h27m│     │
│      │  │ 📝 2 saat    ProjectZ  Yeni not eklendi          │     │
│      │  │                              [Show all →]        │     │
│      │  └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │  ┌─ Sec 4: Projects grid (3-col responsive) ───────┐     │
│      │  │ Workspaces                                       │     │
│      │  │ ────────────────────────────────────────────    │     │
│      │  │ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │     │
│      │  │ │ProjectX│ │ProjectY│ │ProjectZ│ │ + New  │    │     │
│      │  │ │● SHIP  │ │💤 SLEEP│ │⏳ PEND │ │workspace│    │     │
│      │  │ │12/24   │ │ 0/8    │ │auth    │ │        │    │     │
│      │  │ │last 2m │ │last 3d │ │waits   │ │        │    │     │
│      │  │ └────────┘ └────────┘ └────────┘ └────────┘    │     │
│      │  └──────────────────────────────────────────────────┘     │
└──────┴───────────────────────────────────────────────────────────┘
```

### 4.3 Components in detail

**`<QuotaGaugeCard provider="claude" />`** (`160×120px`):

- Background: white surface; border `border-default`
- Top row: provider logo (16px) + provider name (label-md)
- Mid: ring chart (Recharts veya custom SVG), 60×60px, fill = primary-500 (>50%) / warning-500 (20-50%) / danger-500 (<20%)
- Center number (display-md, tabular-nums): "67%"
- Bottom: subtitle (body-sm, text-secondary): "4h 12m left" / "resets at 14:30"
- Click → Connections sayfasında ilgili provider'a anchor scroll
- Disabled state (sign-in yok): grey out + "Sign in" link

**`<LiveLoopStatus />`** (full width hero):

- Background: white, `border-l-4 border-primary-500` (active) veya `border-muted` (idle)
- Live indicator: 8px pulsing red dot + "LIVE" label (warning-500) eğer aktif loop varsa
- Idle state: "Jr şu an dinleniyor" + "Yeni iş başlat →" CTA
- Mid: meta row (workspace · cli · turn · duration) — body-sm
- Quote block: italic, body-md, text-primary — Speaker'ın anlık "thought summary"
- Right action: "Open Workspace →" primary outline button

**`<ActivityFeedItem />`** (compact row):

- Icon left (16px, semantic color)
- Time (label-sm, text-tertiary, fixed width 80px tabular-nums)
- Workspace name (heading-md, text-primary)
- Description (body-sm, text-secondary)
- Click → ilgili workspace + scroll to event detail

**`<ProjectCard />`** (240×160px):

- Header: name (heading-md) + status pill (success / warning / danger)
- Mid: kanban progress bar (12/24 done) + ratio text
- Footer: "Last: 2m ago" (label-sm, text-tertiary)
- Hover: shadow-md elevation + "Open →" overlay
- "+ New" card: dashed border, plus icon, primary text

### 4.4 Backend bindings

- `<QuotaGaugeCard />` → `GET /api/providers` (subscription_quota field)
- `<LiveLoopStatus />` → `GET /api/loop/active` + WebSocket `/ws/loop`
- `<ActivityFeedItem />` → `GET /api/activity?limit=5` (audit log derivation)
- `<ProjectCard />` → `GET /api/projects` (status + last_activity + task ratio)

### 4.5 Empty states

- 0 provider signed in: Quota strip yerine CTA card: "5 CLI provider'a bağlanın → Connections'a git"
- 0 project: Projects grid yerine: hero CTA "İlk projenizi başlatın", büyük "+ New project" buton
- 0 activity: Recent activity yerine "Jr henüz hiçbir şey yapmadı" + idle hint

---

## 5. Ekran 2 — Workspace

### 5.1 Amaç

Bir projeye girince operator **kanban + canlı film + Jr notları** üçlüsünü tek scroll'da görür.

### 5.2 Layout (flat scroll, sekme YOK)

```
┌──────────────────────────────────────────────────────────────────┐
│  Topbar [Workspace: ProjectX ▼] ...                             │
├──────┬───────────────────────────────────────────────────────────┤
│ Side │  WorkspaceHeader (sticky offset top-14)                  │
│ bar  │  ┌──────────────────────────────────────────────────┐   │
│      │  │ ProjectX                                          │   │
│      │  │ ● SHIPPING · 12/24 tasks · son aktivite 2 dk      │   │
│      │  │ [Switch] [Edit] [Pause Jr] [Archive]              │   │
│      │  └──────────────────────────────────────────────────┘   │
│      │                                                          │
│      │  Section: Kanban                                        │
│      │  ┌──────────────────────────────────────────────────┐   │
│      │  │ ┌──Backlog─┐┌──InProg.─┐┌──Review─┐┌──Done────┐│   │
│      │  │ │ TASK-13  ││ TASK-12  ││ TASK-11 ││ TASK-10  ││   │
│      │  │ │ TASK-14  ││          ││         ││ TASK-9   ││   │
│      │  │ │ + Add    ││          ││         ││ TASK-8   ││   │
│      │  │ │          ││          ││         ││ + 4 more ││   │
│      │  │ └──────────┘└──────────┘└─────────┘└──────────┘│   │
│      │  └──────────────────────────────────────────────────┘   │
│      │                                                          │
│      │  Section: Live Run Theater (3-pane)                     │
│      │  ┌──────────────────────────────────────────────────┐   │
│      │  │ Header: ● LIVE · claude · turn 47/∞ · 12m       │   │
│      │  │         [Pause] [Switch CLI ▼] [Open transcript]│   │
│      │  ├────────────────┬────────────────┬───────────────┤   │
│      │  │ CLI output     │ Screenshots    │ Jr thought    │   │
│      │  │ (terminal)     │ (timeline)     │ (compacted)   │   │
│      │  │                │                │               │   │
│      │  │ $ npm run dev  │  ┌──┐┌──┐┌──┐ │ ▸ "Supabase   │   │
│      │  │ > started      │  │  ││  ││ ● │ │   auth ekranı│   │
│      │  │ ✓ ready 3000   │  └──┘└──┘└──┘ │   açık. Email │   │
│      │  │                │ 10:23 10:24..│ │   kutusu görü-│   │
│      │  │ Self Jr →     │                │   yor."        │   │
│      │  │ "lütfen logini│ ┌────────────┐│               │   │
│      │  │  test et"      │ │  Active    ││ ▸ Next prompt:│   │
│      │  │ Claude →       │ │  preview   ││   "şimdi geçer│   │
│      │  │ I'll check ... │ │            ││   siz şifre   │   │
│      │  │                │ └────────────┘│   gir"        │   │
│      │  │ [auto-scroll]  │                │               │   │
│      │  │   ─pause─      │ Vision tier:   │ [show raw ▾] │   │
│      │  │                │ tier-1 (mlx)   │               │   │
│      │  └────────────────┴────────────────┴───────────────┘   │
│      │  Width split: 40% / 30% / 30%                           │
│      │  Min height: 480px; resizable handle between panes      │
│      │                                                          │
│      │  Section: Jr Notes (markdown)                           │
│      │  ┌──────────────────────────────────────────────────┐   │
│      │  │ 📝 ProjectX notlarım                              │   │
│      │  │ ────────────────────────────────────────────    │   │
│      │  │ # Auth                                            │   │
│      │  │ - Supabase magic-link tercih edildi               │   │
│      │  │ - Email confirmation REQUIRED                     │   │
│      │  │                                                   │   │
│      │  │ # Backend                                         │   │
│      │  │ - operator → API route, server actions DEĞİL    │   │
│      │  │                                                   │   │
│      │  │ # Tests                                           │   │
│      │  │ - Playwright e2e, CI headless                     │   │
│      │  │                                                   │   │
│      │  │ Last update: 8 dk önce  [Edit] [+ Add section]   │   │
│      │  └──────────────────────────────────────────────────┘   │
│      │                                                          │
│      │  Section: Pending confirmations (visible only if any)   │
│      │  ⚠ 1 destructive eylem onay bekliyor (3h 27m kaldı)   │
│      │  [git push origin main]      [Onay] [İptal] [Detay]    │
│      │                                                          │
└──────┴───────────────────────────────────────────────────────────┘
```

### 5.3 Live Run Theater detay

#### 5.3.1 Veri Modeli

```typescript
interface LiveRunTheaterState {
  activeCLI: 'claude' | 'codex' | 'gemini' | 'minimax' | 'glm';
  cliSession: {
    sessionId: string;
    turn: number;
    startedAt: ISO8601;
    tokensUsed: number;
    status: 'running' | 'idle' | 'paused' | 'errored';
  };
  cliOutput: {
    stream: ANSIChunk[];     // append-only, WebSocket push
    autoScroll: boolean;
  };
  screenshots: Array<{
    id: string;
    at: ISO8601;
    blob: string;            // pre-signed URL or base64
    source: 'browser' | 'mobile-emu' | 'desktop';
    visionTier: 1 | 2 | 3;
    active: boolean;         // bu an gösterilen preview
  }>;
  jrThoughts: Array<{
    id: string;
    at: ISO8601;
    summary: string;         // <=400 char compacted
    raw?: string;            // <think>...</think> full, lazy load
  }>;
  nextPrompt?: string;
  alerts: Array<{
    kind: 'destructive_pending' | 'error' | 'quota_low';
    detail: string;
    actionable?: { label: string; action: string };
  }>;
}
```

#### 5.3.2 WebSocket protokol

`ws://server/ws/workspace/{slug}/theater`

Event tipleri:

```typescript
type TheaterEvent =
  | { type: 'cli.output.append'; chunk: ANSIChunk }
  | { type: 'cli.turn.complete'; turn: number; tokens: number }
  | { type: 'screenshot.new'; screenshot: Screenshot }
  | { type: 'thought.new'; thought: ThoughtSummary }
  | { type: 'next-prompt.preview'; text: string }
  | { type: 'cli.switch'; from: CLIName; to: CLIName; reason: string }
  | { type: 'alert.new'; alert: Alert }
  | { type: 'session.end'; reason: string };
```

#### 5.3.3 Pane davranışları

**CLI output pane:**
- Monospace (JetBrains Mono 13px)
- ANSI 16-color + truecolor support (`@xterm/headless` veya server-side ansi-to-html)
- Auto-scroll lock: pause button (kullanıcı yukarı scroll edince otomatik pause)
- Search: Ctrl+F in-pane regex
- Copy: select + Ctrl+C standart
- Max buffer: 10k satır, FIFO ring

**Screenshot timeline:**
- Yatay strip, 80×60px thumbnails, gap 4px
- Hover: 320×240px popover preview + timestamp
- Click: aktif preview pane'i (alt yarı) güncelle
- Pinned screenshot (kullanıcı pin atabilir) sol kenar yıldız ikonu
- Auto-advance: yeni screenshot geldikçe sağa akar, active otomatik son
- Vision tier label altta (label-sm): "tier-1 (mlx)" / "tier-2 (ollama)" / "tier-3 (api)"

**Jr thought bubble:**
- 3-4 son düşünce summary, eski olanlar yukarı kayar
- Her summary item:
  - ▸ ikon (chevron) + summary text (italic, body-sm)
  - Show "raw" toggle → `<think>` ham içeriği expand
- Next prompt preview (italic, text-primary, alt kısımda)
- "[Pause Jr]" buton sağ üst (workspace bazlı pause)

### 5.4 Kanban detay

- 4 column varsayılan: Backlog / In progress / Review / Done
- Configurable: Settings'ten projeye özel column adları (gelişmiş)
- Drag-drop (react-dnd veya @dnd-kit/sortable)
- Card click → side drawer (Sheet) ile task detay
- "+ Add" inline form (klavye ile add)
- Filter chips: assignee (sadece operator vs Self Jr), tag, priority
- Jira import button (kart kovasında küçük link, "Jira'dan import →")

### 5.5 ProjectNotes detay

- Markdown editor (Tiptap or Lexical or basit textarea + remark render)
- Auto-save (debounce 1sn), backend `PUT /api/workspaces/{slug}/notes`
- Section navigation (table of contents) sol kenar
- RAG ingest: notes değiştiğinde Mind pillar `notes_collection`'a yazılır
- "Jr'ın eklediği notlar" badge: AI-generated note'lar (italic, alt çizgi border)
- operator tarafından eklenenler "human" badge ile

### 5.6 PendingConfirmationBanner

- Sticky top, page-internal (page header altında)
- Background: `bg-warning-50` border `border-warning-500`
- Icon: ⚠ warning + bell
- Metin: "1 destructive eylem onay bekliyor — git push origin main"
- Sağda countdown timer (3h 27m kaldı)
- Butonlar: [Onay] (primary) [İptal] (ghost) [Detay →] (link)
- Detay click → modal: tam komut + nedeni + telegram preview

### 5.7 Backend bindings

- `<KanbanBoard />` → `GET /api/workspaces/{slug}/tasks`
- `<LiveRunTheater />` → WebSocket `/ws/workspace/{slug}/theater`
- `<ProjectNotes />` → `GET/PUT /api/workspaces/{slug}/notes`
- `<PendingConfirmationBanner />` → `GET /api/workspaces/{slug}/pending-actions`

---

## 6. Ekran 3 — Talk

### 6.1 Amaç

operator ↔ Speaker (Self Jr) direkt sohbet. Project-context-aware. ChatGPT/Claude.ai tarzı.

### 6.2 Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ Topbar                                                            │
├──────┬───────────────────────────────────────────────────────────┤
│ Side │ ┌─ Header ───────────────────────────────────────┐       │
│      │ │ Talk                                            │       │
│      │ │ Speaker: Self Jr · Context: [Auto-detect (X)▼] │       │
│      │ │ [New chat] [History]                            │       │
│      │ └─────────────────────────────────────────────────┘       │
│      │                                                            │
│      │ ┌─ Conversation feed (scroll up to load more) ───┐       │
│      │ │                                                  │       │
│      │ │  [operator]                          09:14    │       │
│      │ │  login flow nasıl ilerliyor?                    │       │
│      │ │                                                  │       │
│      │ │  [Self Jr] 09:15 · ProjectX · claude         │       │
│      │ │  Magic-link auth ile ProjectX'te ilerliyorum.  │       │
│      │ │  Supabase email confirmation zorunlu, 2 dk     │       │
│      │ │  önce test mail attım, doğrulama bekliyor.     │       │
│      │ │  Gemini'yi kapatıp Claude'a geçtim çünkü       │       │
│      │ │  Supabase JS API tipleri daha karmaşıktı.      │       │
│      │ │  [Open workspace →] [View live →]              │       │
│      │ │                                                  │       │
│      │ │  [operator]                          09:18    │       │
│      │ │  Codex'i kullan, daha hızlı                    │       │
│      │ │                                                  │       │
│      │ │  [Self Jr] 09:18 · ProjectX · system         │       │
│      │ │  Anlaşıldı. Bu workspace için sticky override  │       │
│      │ │  uygulanıyor: ProjectX → Codex.                │       │
│      │ │  Claude session'ı temiz kapatılıyor...          │       │
│      │ │                                                  │       │
│      │ └──────────────────────────────────────────────────┘       │
│      │                                                            │
│      │ ┌─ Composer (sticky bottom) ──────────────────────┐       │
│      │ │ ┌──────────────────────────────────────────────┐│       │
│      │ │ │ Mesaj yaz... (Enter = gönder, Shift+Enter NL) ││       │
│      │ │ │                                              ││       │
│      │ │ └──────────────────────────────────────────────┘│       │
│      │ │ [📎] [/cli] [/workspace] [/pause] [/note]  →   │       │
│      │ └──────────────────────────────────────────────────┘       │
└──────┴───────────────────────────────────────────────────────────┘
```

### 6.3 Components

**`<ChatMessage role="user"|"jr" />`:**
- Avatar dot (left): primary-500 (user) veya success-500 (jr)
- Role label (label-md, semibold)
- Timestamp (label-sm, text-tertiary, sağ üst)
- For Jr: ek meta — workspace pill + active CLI pill (color coded per provider)
- Body: markdown render (links, code blocks, inline mention chips)
- Footer (Jr only): related actions ("Open workspace →", "View live →")
- Max width 720px; sol/sağ pad asymmetric (chat dengesi)

**`<ChatComposer />`:**
- Textarea (auto-grow, max 8 lines)
- Slash chips clickable: `/cli` `/workspace` `/pause` `/note` `/finetune`
- 📎 file attach (image, code snippet)
- Send button (primary, disabled if empty)
- Shift+Enter newline, Enter send
- Composing typing indicator (Jr "yazıyor..." pulse) sağ üstte

### 6.4 Context auto-detect

Header'da dropdown: `[Auto-detect (ProjectX) ▼]`

Auto mode:
- Talk'taki son mesajda workspace mention varsa → o workspace
- Yoksa son aktif loop'un workspace'i → o workspace
- Yoksa son talk session'ın workspace'i → o workspace
- Hiçbiri yoksa → "All projects" (global)

Manuel override: dropdown'dan workspace seç → sonraki mesajlar o workspace context'inde Speaker'a gider.

### 6.5 History panel

"History" button → side drawer (Sheet) ile geçmiş conversation'lar listesi.
Her item:
- Title (Jr otomatik özet üretir: "Supabase login flow debug")
- Last message preview
- Timestamp + workspace badge
- Search input top

### 6.6 Backend bindings

- `GET /api/talk/conversations` — list
- `GET /api/talk/conversations/{id}` — full message thread
- `POST /api/talk/send` — { workspace?, text, attachments }
- `WebSocket /ws/talk/{conversation_id}` — typing + new message stream

### 6.7 Empty state

İlk kez Talk açıldıysa:
- Hero illüstrasyon (Lucide MessageCircle 64px)
- "Self Jr ile konuş"
- 1 cümle açıklama: "Proje bağlamında her şeyi sorabilirsin"
- 3 örnek prompt chip:
  - "ProjectX'in dünkü ilerlemesi nasıldı?"
  - "Yarın hangi task'ları yapmalıyım?"
  - "Stripe entegrasyonunu nasıl planlıyoruz?"

---

## 7. Ekran 4 — Connections

### 7.1 Amaç

5 CLI provider auth + subscription quota + Telegram bridge tek yerde. Multi-user UI affordance yok.

### 7.2 Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ Topbar                                                            │
├──────┬───────────────────────────────────────────────────────────┤
│ Side │ Header: Connections                                       │
│      │ "CLI providers + Telegram bridge + browser auth state"   │
│      │                                                            │
│      │ ── Section: CLI Providers ────────────────────────────   │
│      │                                                            │
│      │ ┌─ ProviderCard claude (signed in) ───────────────┐     │
│      │ │ ● Claude Code (Anthropic Pro)                   │     │
│      │ │   Subscription: Pro · 67% quota left            │     │
│      │ │   Resets: 14:30 (4h 12m kaldı)                  │     │
│      │ │   Active sessions: 1 · workspace ProjectX       │     │
│      │ │   [Sign out] [Test connection] [Browser preview]│     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ┌─ ProviderCard codex (signed in) ────────────────┐     │
│      │ │ ● Codex (ChatGPT Plus)                          │     │
│      │ │   Subscription: Plus · 92% · resets in 5h       │     │
│      │ │   [Sign out] [Test connection]                  │     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ┌─ ProviderCard gemini (signed in, warning) ──────┐     │
│      │ │ ⬤ Gemini CLI (Google AI Studio)                │     │
│      │ │   Subscription: Free Tier · 23% · 1d 8h reset   │     │
│      │ │   ⚠ Quota düşük                                 │     │
│      │ │   [Sign out] [Test connection]                  │     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ┌─ ProviderCard minimax (not signed in) ──────────┐     │
│      │ │ ○ Minimax                                       │     │
│      │ │   Not signed in.                                │     │
│      │ │   [Sign in →]                                   │     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ┌─ ProviderCard glm (not signed in) ──────────────┐     │
│      │ │ ○ GLM (Zhipu)                                   │     │
│      │ │   [Sign in →]                                   │     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ── Section: Telegram Bridge ──────────────────────────   │
│      │                                                            │
│      │ ┌─ TelegramCard ──────────────────────────────────┐     │
│      │ │ ● Telegram Bridge — Connected as @yamac         │     │
│      │ │   Bot: @YamacJrBot                              │     │
│      │ │   Webhook: https://selffork.example.com/tg      │     │
│      │ │   Soft confirmation: 4 hours (default)          │     │
│      │ │   Last activity: 5 dk önce (TASK-12 onayı)      │     │
│      │ │                                                  │     │
│      │ │   Recent messages:                              │     │
│      │ │   • Jr → Sr  09:14  PROD push onayı             │     │
│      │ │   • Sr → Jr  09:08  "ProjectY için frontend..." │     │
│      │ │                                                  │     │
│      │ │   [Send test] [View log] [Bot settings]         │     │
│      │ └──────────────────────────────────────────────────┘     │
└──────┴───────────────────────────────────────────────────────────┘
```

### 7.3 ProviderCard

**Status dots:**
- 🟢 success-500: signed in, quota ok
- 🟡 warning-500: signed in, quota <20%
- 🔴 danger-500: signed in, errored / 0 quota
- ⚪ tertiary: not signed in

**Sign-in flow trigger:**
- "Sign in →" click → modal açılır
- Modal içeriği: server-side headless browser canvas (live screenshot) + "Sign in your browser" affordance
- Body M5 driver'ı OAuth flow'u yönetir (Playwright)
- Cookies sunucuda persisted → modal kapanır, status 🟢

**Browser preview action:**
- "Browser preview" → drawer (Sheet) ile canlı headless browser screenshot stream
- Power user: manuel adımları orada atabilir (örn. MFA code girer)

### 7.4 TelegramCard

**Initial state (not connected):**
- "Connect to Telegram" hero CTA
- Wizard 3-step:
  1. BotFather instructions (link + copy)
  2. Bot token input
  3. Webhook URL (otomatik üretilir, kopyala)
- "Test webhook" button → bot'tan test mesajı gelir

**Connected state:**
- Status dot + bot name + webhook URL
- Soft confirmation window default config (Settings'e shortcut)
- Recent messages preview (son 3-5)
- Actions: send test, view log (drawer), bot settings (modal)

### 7.5 Backend bindings

- `GET /api/providers` — provider list + status + quota
- `POST /api/providers/{name}/signin/start` — Body driver başlat
- `POST /api/providers/{name}/signout`
- `GET /api/telegram/status`
- `POST /api/telegram/setup` — { bot_token }
- `WebSocket /ws/providers/{name}/auth-stream` — sign-in canvas

---

## 8. Ekran 5 — Settings

### 8.1 Amaç

Model endpoint + fine-tune UI + Telegram config + theme + advanced power user surface.

### 8.2 Layout (collapsible sections, default expanded ilk 3)

```
┌──────────────────────────────────────────────────────────────────┐
│ Topbar                                                            │
├──────┬───────────────────────────────────────────────────────────┤
│ Side │ Header: Settings                                          │
│      │                                                            │
│      │ ▼ Model Endpoint                                           │
│      │ ┌──────────────────────────────────────────────────┐     │
│      │ │ Endpoint URL: [http://192.168.1.10:8080       ] │     │
│      │ │ Protocol:     ⊙ OpenAI-compatible               │     │
│      │ │                ○ MLX-server (raw)               │     │
│      │ │                ○ Ollama                         │     │
│      │ │ Model name:   [gemma-4-26b-a4b-it-4bit       ] │     │
│      │ │ Auth:          ○ None                           │     │
│      │ │                ⊙ API key  [••••••••]            │     │
│      │ │                ○ Bearer token                   │     │
│      │ │ Health:        ● Online · 187ms · just now      │     │
│      │ │ [Test connection] [Save & restart]              │     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ▼ Fine-tune                                                │
│      │ ┌──────────────────────────────────────────────────┐     │
│      │ │ Training dataset                                  │     │
│      │ │  Source: ⊙ Auto (session history → CoT pipeline)  │     │
│      │ │          ○ Manual path: [/path/to/dataset.jsonl]  │     │
│      │ │  Examples: 8,432 (after CoT scoring)              │     │
│      │ │  Est. time: 5h 18m (remote GPU)                   │     │
│      │ │                                                   │     │
│      │ │ Hyperparams                                       │     │
│      │ │   Method:        [QLoRA          ▼]               │     │
│      │ │   LoRA rank:     [32       ]                      │     │
│      │ │   LoRA alpha:    [16       ]                      │     │
│      │ │   Learning rate: [2e-4     ]                      │     │
│      │ │   Epochs:        [3        ]                      │     │
│      │ │   Target:        [attention only ▼]               │     │
│      │ │                                                   │     │
│      │ │ Training endpoint                                 │     │
│      │ │  ○ Same as model endpoint                         │     │
│      │ │  ⊙ Separate: [https://train.gpu.example.com]     │     │
│      │ │                                                   │     │
│      │ │ Current adapter: v1.2 (47 days old)               │     │
│      │ │ [▶ Start training]                                │     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ▼ Telegram bridge                                          │
│      │ ┌──────────────────────────────────────────────────┐     │
│      │ │ Soft confirmation window: [4 hours ▼]            │     │
│      │ │  (Destructive eylem onay süresi.                  │     │
│      │ │   Sessizlik = iptal.)                             │     │
│      │ │                                                   │     │
│      │ │ Destructive whitelist: [Open editor →]            │     │
│      │ │  Current: 7 categories enabled                    │     │
│      │ │   prod_deploy · db_destructive · force_push ·    │     │
│      │ │   file_destructive · account · financial · social │     │
│      │ │                                                   │     │
│      │ │ Per-category override:                            │     │
│      │ │  prod_deploy:   [4 hours ▼]                      │     │
│      │ │  social_outbound:[1 hour  ▼]                     │     │
│      │ │                                                   │     │
│      │ │ [Open destructive_actions.yaml]                   │     │
│      │ └──────────────────────────────────────────────────┘     │
│      │                                                            │
│      │ ▸ Theme                                                    │
│      │ ▸ Workspace defaults                                       │
│      │ ▸ Advanced (power user)                                    │
└──────┴───────────────────────────────────────────────────────────┘
```

### 8.3 Advanced section (collapsed, power user)

Açıldığında:

```
▼ Advanced (power user)
  ─ Show Jr raw thinking      [ ]
  ─ Show audit event timeline [ ]
  ─ Show vision tier details  [ ]
  ─ Show full session log     [ ]
  ─ Workspace data dir:        /opt/selffork/data
  ─ RAG store path:            /opt/selffork/rag.db
  ─ Reset RAG embeddings →     [Reset (irreversible)]
  ─ Open API key fallback:     [Configure...]
  ─ Telemetry & analytics:     [ ] Anonymous usage stats
  ─ Export config:             [Download config.yaml]
  ─ Import config:             [Upload]
```

### 8.4 Backend bindings

- `GET/PUT /api/settings/model-endpoint`
- `GET/PUT /api/settings/fine-tune`
- `POST /api/reflex/train` — fine-tune trigger
- `GET /api/reflex/training-status` — progress polling
- `GET/PUT /api/settings/telegram`
- `GET /api/settings/destructive-whitelist`
- `PUT /api/settings/destructive-whitelist/{id}/window`
- `GET/PUT /api/settings/theme`
- `GET/PUT /api/settings/advanced`

---

## 9. Pattern Library

### 9.1 Modal / Dialog

- Center modal: `shadow-lg`, `bg-surface`, `rounded-lg`, `max-w-md` (small) / `max-w-2xl` (large)
- Backdrop: `bg-black/40 backdrop-blur-sm`
- Esc to close, click-outside to close (data-loss varsa confirm)
- Header: title (heading-lg) + close X
- Body: `space-y-4`
- Footer: align-right, primary + ghost buttons

### 9.2 Drawer / Sheet

- Slide from right: `w-[480px]`, full height
- Used for: workspace switcher, history panel, browser preview stream, task detail
- Header sticky, body scrolls

### 9.3 Notification / Toast

- Position: bottom-right (desktop), bottom-center (mobile)
- Variants: success / warning / danger / info
- Auto-dismiss: success 3s, info 4s, warning 6s, danger sticky
- Stack max 3, queue rest

### 9.4 Empty states

Pattern:
1. Centered Lucide ikon 64px (text-tertiary)
2. heading-lg title
3. body-md description (max 480px width)
4. Primary CTA button

### 9.5 Loading / Skeleton

- Card variant: `<Skeleton variant="card" height={160} />`
- Text variant: `<Skeleton variant="text" lines={3} />`
- Avatar variant: rounded-full
- Animate-pulse with prefers-reduced-motion saygı

### 9.6 Live indicator

- 8px round dot, color = success-500 (idle online) veya danger-500 (live working)
- Pulse animation (CSS keyframes, opacity 1 → 0.4 → 1, duration 1.5s)
- Tooltip on hover: "Live · 2m 47s · ProjectX"

### 9.7 Status pills

`<StatusPill variant="success|warning|danger|info">label</StatusPill>`
- Padding: `px-2 py-0.5`
- Radius: `rounded-md`
- Font: `label-md` semibold
- Color: text on variant-500, bg variant-50

### 9.8 Provider color coding

CLI providers UI'da renkli pill ile gösterilir (tutarlı):
- claude: `#D4A056` (Anthropic amber)
- codex: `#10A37F` (OpenAI green)
- gemini: `#4285F4` (Google blue)
- minimax: `#7C3AED` (purple)
- glm: `#EF4444` (Zhipu red)

Bu sadece **pill chip arka planı** için; ana primary palette etkilenmez.

---

## 10. Accessibility

- Tüm interactive elemanlar `aria-label`
- Keyboard navigation: Tab order doğru, focus ring `outline-2 outline-primary-500 outline-offset-2`
- Color contrast: text-primary AAA, text-secondary AA, danger pill üstündeki text AA
- `prefers-reduced-motion` → animation kapalı
- Screen reader: live region (`aria-live=polite`) — toast notifications için
- Modal: focus trap + restore on close
- Cmd+K palette: tüm slash command screen reader announced

---

## 11. Implementation Notes

### 11.1 Foundation korunur

- Inter font import (`next/font/google`) korunur
- Material-3 token paleti `tailwind.config.ts` korunur (semantic mapping ekstradır)
- Sidebar component (`components/layout/sidebar.tsx`) korunur — sub-list workspace dinamik enjekte edilir
- Topbar component (`components/layout/topbar.tsx`) korunur — sağ aksesuarlar revize
- AppShell layout korunur — `md:ml-sidebar-width` offset
- shadcn primitives (button/input/label/switch/separator/tooltip/dialog/select/alert) korunur

### 11.2 Yeni dosyalar

```
apps/web/
├── app/
│   ├── page.tsx                          # Dashboard (mevcut "/" rewrite)
│   ├── workspaces/
│   │   └── [slug]/page.tsx               # YENİ — Workspace (3-pane theater)
│   ├── talk/page.tsx                      # mevcut rewrite (chat composer)
│   ├── connections/page.tsx               # mevcut rewrite (provider + telegram)
│   └── settings/page.tsx                  # mevcut rewrite (sections)
├── components/
│   ├── dashboard/
│   │   ├── QuotaGaugeCard.tsx            # YENİ
│   │   ├── LiveLoopStatus.tsx            # YENİ
│   │   ├── ActivityFeedItem.tsx          # YENİ
│   │   └── ProjectCard.tsx               # YENİ
│   ├── workspace/
│   │   ├── WorkspaceHeader.tsx           # YENİ
│   │   ├── KanbanBoard.tsx               # YENİ
│   │   ├── KanbanCard.tsx                # YENİ
│   │   ├── LiveRunTheater.tsx            # YENİ
│   │   ├── CLIOutputPane.tsx             # YENİ
│   │   ├── ScreenshotTimeline.tsx        # YENİ
│   │   ├── JrThoughtBubble.tsx           # YENİ
│   │   ├── ProjectNotes.tsx              # YENİ
│   │   └── PendingConfirmationBanner.tsx # YENİ
│   ├── talk/
│   │   ├── ChatMessage.tsx               # YENİ
│   │   └── ChatComposer.tsx              # YENİ
│   ├── connections/
│   │   ├── ProviderCard.tsx              # YENİ
│   │   └── TelegramCard.tsx              # YENİ
│   └── settings/
│       ├── FineTuneSection.tsx           # YENİ
│       ├── ModelEndpointForm.tsx         # YENİ
│       └── AdvancedToggle.tsx            # YENİ
└── lib/
    ├── api/
    │   ├── projects.ts                   # rewrite (workspace endpoint)
    │   ├── providers.ts                  # extend (signin start/stream)
    │   ├── telegram.ts                   # YENİ
    │   ├── theater.ts                    # YENİ (WebSocket helpers)
    │   └── settings.ts                   # YENİ
    └── store/
        └── theater-slice.ts              # YENİ (Zustand)
```

### 11.3 Removed (v2 Stitch artifacts)

`app/workspaces/page.tsx` (flat list) → `app/workspaces/[slug]/page.tsx`'in alt route'u (parent index list opsiyonel, Dashboard'da grid var, ayrı sayfa gerekmez)

### 11.4 No-mock rule

Tüm endpoint'ler **gerçek backend** ile konuşur. Backend ready değilse:
- HTTP 503 ile karşılan → UI inline error + retry CTA
- WebSocket connection fail → "Self Jr offline. [Reconnect]"
- Asla fake data, asla `Math.random()` placeholder

---

## 12. Stitch Brief (Generation Instructions)

Stitch'e bu dokümanı upload edip 5 ekran üreteceğim. Her ekran prompt'unda şu kelimeleri **vurgulayacağım**:

- **light enterprise theme** (not "minimal modern")
- **calm hierarchy** (not "single-input magic")
- **power user surface visible** (not "advanced hidden")
- **operator atelier vibe** (not "team dashboard")
- **server-app full-window** (not "mobile-first")
- **NO multi-user avatars / team grids**
- **NO audit log streams default**
- **NO slider widgets**
- **NO "magic" wand or AI-glow effects**

**Reject patterns Stitch'e:**

> "We do NOT want: marketing-style hero with gradient, mobile-first thumb-zone layout, social-media share buttons, profile circles for teams, dashboard with KPI cards in cockpit aesthetic, 'AI is thinking ✨' glowing animations."

**Yes patterns:**

> "We DO want: Linear v1 sidebar pattern, Vercel dashboard project grid, Replit Agent live event feed, Cursor IDE sidebar tone, light enterprise color palette (off-white surface, blue primary), Inter typography, tabular-nums for metrics, real terminal stream in CLI pane, screenshot timeline horizontal thumbnails."

---

**DESIGN.md v3 son — Stitch upload'a hazır.**
