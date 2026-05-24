# ADR-006 — SelfFork v2 Pivot: Server Deployment, Speaker-Only, Full Autonomy, UI Revise

## Status

- **Status:** Accepted (vision-locked, 2026-05-17)
- **Date:** 2026-05-17
- **Author:** operator + Claude (interlocutor)
- **Type:** **DOMINANT ADR** — bu, SelfFork projesinin tarihindeki en kapsamlı karar dokümanıdır. ADR-001 (MVP v0), ADR-004 (M4 Cockpit) ve ADR-005 (M5 Body) gibi öncel kararları belirli maddelerde **patch'ler**; ARGE PDF'inin bazı bölümlerini **revoke** eder; PRD ve ROADMAP'in tekrar tabaklanmasını **mandate** eder.
- **Supersedes (clauses):**
  - `docs/archive/Yamac_Jr_ARGE.pdf` §7 (Watcher), §8 (Tailscale mesh / multi-machine fleet), §9 (Slider 0-10 + threshold tablosu PROD = ∞ kuralı), §2.1 (Mac mini = ev beyin)
  - `docs/PRD.md` §8.5 (Cockpit Vite/React stack referansı), §5.1'in single-operator persona stricture'ı (genişler), §15 threshold table
  - `docs/ROADMAP.md` M4 Cockpit IA tarifi (Mission/Run/Chat/Ctxt 4-tab), M5 cockpit ek route'ları
  - `docs/decisions/ADR-001_MVP_v0.md` §UI surface, §853 hibrit dil reddi (revizyon)
  - `docs/decisions/ADR-004_M4_Cockpit.md` IA tarifi (kanonik 4-tab workspace)
  - `apps/web/DESIGN.md` v2 minimalist (rewrite gerekli → v3)
- **Related (uyumlu, etkilenmez):**
  - ADR-002 Mind Architecture — değişmez
  - ADR-003 M3 CLI Surfing — router girdileri **revize** (quota + operator override + RAG; rotasyon mantığı iptal)
  - ADR-005 M5 Body — Body daemon + vision + provider auth korunur, multi-machine bölümü revize

---

## 0. Yönetici Özeti (Executive Summary)

SelfFork üç çekirdek pivot ile bugün (2026-05-17) yeniden tanımlanmıştır:

1. **Deployment pivot:** Mac mini-merkezli mimari → **Linux sunucu self-host**. SelfFork tek bir sunucuda yaşar; CLI'ler aynı sunucuda yan yana koşar; model **external endpoint** (kullanıcı UI'dan seçer: lokal, başka sunucu, GPU sunucu). Açık kaynak — isteyen kendi sunucusuna kurar.
2. **Mimari pivot:** Çift model (Speaker + Watcher) → **Speaker-only**. Watcher iptal. Slider 0-10 özerklik kadranı iptal. Tam otonom Self Jr — sadece destructive eylemler için 3-4 saat fail-safe soft confirmation (Telegram).
3. **UI pivot:** Operator-cockpit (PRD §8.5 light-enterprise) ↔ Stitch v2 non-engineer flat-minimalist gerilimi → **P+Prompt Engineer power-aware sade UI**. 5 ekran: Dashboard / Workspace (3-pane Live Run Theater) / Talk / Connections / Settings. Stitch v2 yeniden tasarlanacak (DESIGN.md v3 spec'iyle).

Bu üç pivot, ARGE'nin temel ruhunu ("uyumayan ikinci ben") koruyor; mimari ayrıntıları (Watcher, mesh, slider) bütçe ve operator iş akışı gerçekliğiyle güncelliyor; UI'ı ne Cursor/Lovable çocuk-modu, ne mühendis-cockpit — ikisinin arasında, **P+Prompt Engineer için power-aware sade** yere koyuyor.

---

## 1. Bağlam ve Tetikleyici

### 1.1 Tetikleyici Olaylar

**2026-05-16 gece:** Operator önceki cockpit'e "rezalet" dedi. Aynı gece Stitch MCP ile yeni v2 UI doğdu (Home / Workspaces / Talk / Connections / Settings — 5 ekran flat, "non-engineer minimalist", Lovable.dev / Cursor / Replit referansı). Backend + vision modeli down olduğu için doğrulanmadı, commit edilmedi. Memory'ye `[[ui-minimalist-user-first]]` ve `[[v2-ui-rebuild-inprogress]]` düştü.

**2026-05-17:** Operator yeni session açtı, ARGE PDF'i (`docs/archive/Yamac_Jr_ARGE.pdf`) referans olarak gösterdi:

> *"benim asıl vizyonum bu dökümanda... bunu okuyup tekrar karar ver! sonra da bana anladıklarını kısaca söyle! ona göre ben seni düzelticem!"*

PDF okundu; doc-vizyon ↔ Stitch v2 sapma raporu çıkarıldı (uyum 3/10). Operator karşılığında üç ana yeniden tanımlamayı verdi:

> *"1- non-engineer kitle kalabilir! ancak bu şekilde değil kesinlikle! 2- watcher model iptal sadece speaker model olacak! 3- olay şu! ... aslında P + Prompt engineer'ım."*

Devamında deployment vizyonu:

> *"ya benim bu projeyi açık kaynak yapma sebebim isteyen herkes bir linux GPU sunucuya selffork kurup diledikleri projeyi yaptırabilsinler isterim! ... şahsen GPU sunucuya param da yok şuanda o yüzden ben Selffork projesini CPU sunucuda ayağa kaldırırım bütün CLI ler tabiki selffork neredeyse orada kalkar! ama settingsden benim localimdeki modeli kaldırırım..."*

Bu üç beyan + ardışık AskUserQuestion turları (slider iptal, hibrit endpoint, 3-pane theater, CLI router task-aware+quota-aware, full autonomy + 3-4 saat soft confirmation) → 12 maddelik karar bloğu kilitlendi → bu ADR.

### 1.2 Bağlamsal Çelişkiler (Karar Sebebi)

| Çelişki | Nereden | Yeni Karar |
|---|---|---|
| ARGE "Mac mini ev beyin" vs operator bütçe gerçekliği | ARGE §2.1 vs 2026-05-17 beyanı | Model = external endpoint (hibrit), SelfFork = Linux sunucu |
| ARGE Speaker+Watcher iki-ajanlı vs operator basitlik tercihi | ARGE §7 vs 2026-05-17 beyanı "watcher iptal" | Sadece Speaker; full-duplex sorunu autonomy + Telegram bridge ile çözülür |
| ARGE Slider 0-10 + threshold tablosu vs operator "tam güven" tercihi | ARGE §9 vs 2026-05-17 beyanı "JR'a full otonom güven" | Slider iptal; destructive eylem listesi için fail-safe-NO 3-4 saat soft confirmation |
| PRD §8.5 operator-cockpit (light-enterprise) vs Stitch v2 non-engineer minimalist | PRD §8.5 (`PRD.md:935`) vs `[[ui-minimalist-user-first]]` | P+Prompt Engineer power-aware sade middle ground |
| ARGE 3-makine × 4-agent mesh vs operator self-host vizyonu | ARGE §8 vs açık kaynak deployment | Tek sunucu (Linux), multi-machine mesh ileride opsiyonel |
| ADR-003 CLI Surfing "rotasyon" mantığı vs operator "task-aware seçim" beyanı | ADR-003 vs "claude codex gemini rotasyon değil, task'a göre seçim" | Router girdileri: quota + operator override + RAG geçmiş performans |

---

## 2. 12-Madde Karar Bloğu (The Locks)

Bu maddelerin her biri ayrı tartışılmıştır; her birinin ardındaki gerekçe §3+ bölümlerinde detaylandırılmıştır.

| # | Karar | Etkilenen pillar / surface |
|---|---|---|
| 1 | **Persona = P+Prompt Engineer.** Operator gibi: prompt yazar, kod yazmaz, CLI'leri yönlendirir, çıktıyı test eder. Non-engineer kullanıcıya açık AMA Stitch v2 sade-çocuk-UI **değil** — power user-aware sadelik. | UI |
| 2 | **Watcher iptal.** ARGE §7 (Speaker+Watcher interleaved full-duplex) revoke. Sadece Speaker. Watcher dataset / classifier eğitimi yapılmaz. | Reflex |
| 3 | **Slider 0-10 iptal.** ARGE §9 özerklik kadranı revoke. "Self Jr'a full otonom güven." | Body, UI (slider widget yok) |
| 4 | **Destructive eylem koruması = soft confirmation, fail-safe NO, 3-4 saat pencere.** Destructive whitelist için Telegram'dan onay; operator 3-4 saat içinde **explicit** onay vermezse eylem **yapılmaz** (sessizlik = iptal). | Body, Telegram bridge |
| 5 | **Live Run Theater = 3-pane.** Sol: CLI output stream. Orta: screenshot timeline (Body M5 vision çıktısı). Sağ: Jr düşünce balonu (Speaker iç-monolog). Maks immersion. | UI Workspace |
| 6 | **CLI router sinyalleri = quota + operator override + RAG geçmiş performans.** "Rotasyon" mantığı iptal. Task-aware seçim RAG'den öğrenilir. ADR-003 §router-strategy revize. | Orchestrator (CLI Surfing) |
| 7 | **Deployment = Linux sunucu self-host (GPU ideal, CPU kabul).** SelfFork tek bir sunucuda; açık kaynak; isteyen kendi sunucusuna kurar. ARGE Mac-mini-ev-beyin revoke. | Infra |
| 8 | **CLI'ler SelfFork ile aynı sunucuda.** Browser-driven auth state sunucuda persisted. Multi-machine daemon mesh (ARGE §8) iptal; ileride opsiyonel feature olarak gelebilir. | Body, Orchestrator |
| 9 | **Model = external endpoint.** UI Settings'te "Model Endpoint" config (URL). Operator hibrit kullanım: CPU sunucuda SelfFork + lokaldeki Mac model; sonra GPU sunucu alınınca GPU model işaretlenir. | Reflex (deploy), UI Settings |
| 10 | **Auth = subscription sign-in, API key DEĞİL.** Her CLI provider için browser-driven OAuth/login flow (Body M5'in iskeleti zaten hazır). | Body, Connections UI |
| 11 | **Subscription quota tracking UI'da gauges.** Provider başına kalan token/dakika + reset window. Body provider auth state'in üstünden derive edilir; provider-side API yok. | UI Dashboard |
| 12 | **Telegram bridge iki yönlü.** Jr → Sr proaktif (destructive onay + ihtiyaç bildirim). Sr → Jr ad-hoc prompt (mobilden). Mevcut PTB altyapısı (`b57a765`) korunur, UI surface eklenir. | Telegram, UI Connections |

---

## 3. ARGE'den Revoke Edilenler vs Korunanlar

### 3.1 Revoke (silinen ARGE bölümleri)

| ARGE bölümü | Sebep |
|---|---|
| §7 Watcher (Full-Duplex Simülasyonu) | Karmaşa azaltma, Speaker tek model dataset; full-duplex pratik gerek değil (P+Prompt eng iş akışında inject genelde human-driven) |
| §8 Tailscale mesh / multi-machine fleet | Sunucu self-host vizyonuyla uyumsuz; CLI'ler sunucuda yan yana, lokal makine sadece UI client |
| §9.1-§9.3 Slider 0-10 + lokasyon farkındalığı | Operator "tam güven" beyanı; ek manuel ayar minimalist'e aykırı |
| §9.4 Threshold tablosu (PROD = ∞) | Statik tablo yerine dinamik destructive whitelist + soft confirmation pencereli |
| §9.5 PROD koruması statik kural | Yerine **soft confirmation 3-4 saat fail-safe NO** dinamik kural |
| §2.1 "Mac mini = ev beyin" sıkı koşulu | Bütçe gerçekliği; Mac mini opsiyonel model endpoint, ana yer sunucu |
| §2.3 48GB bellek bütçesi (Mac mini)  | Sunucu için ayrı (CPU başlangıç → GPU hedef) |

### 3.2 Korunan (değişmeyen ARGE bölümleri)

| ARGE bölümü | Status |
|---|---|
| §1 Gemma 4 26B A4B-it Speaker | KORUNUR — base model |
| §3 Dört katman zaman çizgisi (Mevcut → Uzak → Proaktif → Otonom) | KORUNUR (sadece §3 Katman 2 ARGE §8 multi-machine yerine "remote endpoint" anlamında okunacak) |
| §4 Fine-tune felsefe ("Kimlik = weights, bilgi = RAG") | KORUNUR |
| §4.2-§4.7 Fine-tune metodolojisi, dataset, CoT, QLoRA | KORUNUR (sadece Watcher kaldırıldığı için Watcher classifier eğitimi maddesi düşer) |
| §5 RAG (3 koleksiyon, hibrit arama, reranker) | KORUNUR |
| §6 Embedding/Reranker (Jina API + BGE fallback) | KORUNUR |
| §9.6 Undo/checkpoint/replay | KORUNUR — yine zorunlu, destructive otonomi compansation |
| §12 Önemli alıntılar (proje ruhu) | KORUNUR |
| §13 Yol haritası özeti (üç katman) | KORUNUR (sunucu deployment'ı yorumlanır) |

### 3.3 ARGE ruh ifadesi (immutable)

Bu cümleler proje DNA'sıdır, asla revoke edilemez:

> *"o sadece benim gibi yönlendirme yapıcak! o ben olucak! literally"* — PDF s.800
> *"bana bir tane daha benden lazım vaktim yetmiyor aklımdaki herşeye!!!"* — PDF s.798
> *"256K dan kısma seçeneğim yok! paradan ödün vericez... kolaya ya da hızlıya kaçmam kaliteye kaçarım!"* — PDF s.792-793
> *"yamaç jr. olacak!"* — PDF s.815

---

## 4. Yeni Mimari Topoloji

### 4.1 Genel Diyagram

```
                    İSTEMCİ (operator)
                          │
                          │  HTTPS / mobil app / Telegram
                          ▼
        ┌──────────────────────────────────────────┐
        │     SUNUCU (Linux, GPU veya CPU)         │
        │                                          │
        │  ┌──────────────────────────────────┐    │
        │  │  SelfFork core                   │    │
        │  │  ─ FastAPI orchestrator          │    │
        │  │  ─ Next.js cockpit (apps/web)    │    │
        │  │  ─ SQLite + sqlite-vec + FTS5    │    │
        │  │  ─ Mind (RAG) pillar             │    │
        │  │  ─ Body (vision + driver) pillar │    │
        │  │  ─ Telegram bridge (PTB)         │    │
        │  └─────────────┬────────────────────┘    │
        │                │                         │
        │                │ subprocess              │
        │                ▼                         │
        │  ┌──────────────────────────────────┐    │
        │  │  CLI sürüsü (yan yana)           │    │
        │  │  ─ claude-code                   │    │
        │  │  ─ codex                         │    │
        │  │  ─ gemini-cli                    │    │
        │  │  ─ minimax CLI                   │    │
        │  │  ─ glm CLI                       │    │
        │  │  + opencode (legacy, isteğe bağlı)│    │
        │  │                                  │    │
        │  │  Auth state (cookies) persisted  │    │
        │  │  /home/selffork/.config/cli/*    │    │
        │  └──────────────────────────────────┘    │
        │                                          │
        │  ┌──────────────────────────────────┐    │
        │  │  Headless browser (Playwright)   │    │
        │  │  Body M5 vision driver           │    │
        │  └──────────────────────────────────┘    │
        └──────────────┬───────────────────────────┘
                       │
                       │ HTTPS (model API protokolü, OpenAI-compat
                       │        veya MLX-server veya Ollama)
                       ▼
        ┌──────────────────────────────────────────┐
        │     MODEL ENDPOINT (kullanıcı seçer)     │
        │                                          │
        │  Senaryo A — lokal Mac mini              │
        │  Senaryo B — başka GPU sunucu            │
        │  Senaryo C — aynı sunucuda lokal model   │
        │  Senaryo D — Anthropic/Google/OpenAI API │
        │              (acil fallback, eğitilmemiş)│
        └──────────────────────────────────────────┘
```

### 4.2 Sunucu Bileşenleri

#### 4.2.1 SelfFork core (sunucuda yaşar)

- **Orchestrator** — `packages/orchestrator/` altında FastAPI. CLI session lifecycle, Body daemon, Telegram bridge, vision tier seçimi, persistence (SQLite).
- **Cockpit** — `apps/web/` altında Next.js (production-ready static export veya Node SSR). Operator UI; sunucudan static asset serve edilir, runtime WebSocket bağlantısı orchestrator FastAPI'sine.
- **Mind pillar** — `packages/mind/` altında RAG (3 koleksiyon: session geçmişi + GitHub kod AST + meslektaş referans), embedding/reranker (Jina API + BGE fallback), context compaction.
- **Body pillar** — `packages/body/` altında vision driver (Playwright headless browser, mobile-use opsiyonel), permission warden, action audit. ADR-005 implementasyonu korunur.
- **Telegram bridge** — `packages/telegram/` altında PTB (python-telegram-bot). İki kanal: proaktif bot (Jr → Sr) + ad-hoc receive (Sr → Jr).

#### 4.2.2 CLI sürüsü (sunucuda yan yana)

CLI'ler **subprocess** olarak SelfFork tarafından spawn edilir, tmux session'da koşar (legacy uyumluluk). Browser-driven auth flow için **headless browser** sunucuda açılır (Playwright + xvfb veya headless mode). Auth cookies sunucuda persisted (`~/.config/selffork/auth/<provider>/`).

| CLI | Provider | Auth path | Quota source |
|---|---|---|---|
| claude-code | Anthropic | `~/.config/Claude/auth.json` | derived from `agent.invoke` audit |
| codex | OpenAI (ChatGPT) | `~/.codex/auth.json` (cookies + token) | derived |
| gemini-cli | Google | `~/.config/gemini/auth.json` | derived |
| minimax CLI | Minimax | `~/.minimax/auth.json` | derived |
| glm CLI | Zhipu (智谱) | `~/.config/glm/auth.json` | derived |
| opencode | Multi-provider | `~/.opencode/config.json` | per-provider derived |

#### 4.2.3 Headless browser

Body M5'in vision driver'ı. Auth flow için kullanıcı UI'dan "Sign in to Claude" tıklar; sunucuda headless browser açılır; sayfa screenshot UI'da gösterilir (live VNC tarzı veya periodic screenshot). Kullanıcı sayfa elementlerini UI'dan tıklayabilir veya Self Jr otomatik flow ile (Body driver).

### 4.3 Model Endpoint — Hibrit Konfigürasyon

UI Settings → "Model Endpoint" sayfası:

```
┌────────────────────────────────────────────┐
│  Model Endpoint                            │
│                                            │
│  Endpoint URL: [http://192.168.1.10:8080 ]│
│  Protocol:     [● OpenAI-compatible       ]│
│                [○ MLX-server (raw)        ]│
│                [○ Ollama                  ]│
│  Model name:   [gemma-4-26b-a4b-it-4bit  ]│
│                                            │
│  Auth:         [○ None (lokal)            ]│
│                [● API key                 ]│
│                [○ Bearer token            ]│
│                                            │
│  Health:       ● Online · 187ms · 2026... │
│                                            │
│  [Test connection] [Save & restart]       │
└────────────────────────────────────────────┘
```

Operator senaryoları:
- **Bütçesiz başlangıç:** Sunucu CPU + endpoint = `http://<lokal-mac-ip>:8080` (MLX-server). Sunucu network'ünden lokal Mac'e Tailscale veya VPN üzerinden erişir.
- **GPU sunucu sonra:** Endpoint = `http://gpu.example.com:8080`. Eski lokal endpoint history'de saklanır, geri dönülebilir.
- **Aynı sunucu lokal model:** Endpoint = `http://localhost:8080` (sunucuda da mlx-vlm veya vllm + Gemma 4).
- **Acil fallback:** Endpoint = `https://api.anthropic.com` + Anthropic API key (eğitilmemiş model; refleks kayıp, sadece "çalışmaya devam et" güvencesi).

### 4.4 Speaker Mimarisi (Watcher İptali)

ARGE §7'de tarif edilen Watcher iptal edildi. Pratik etkiler:

- **Tek model context:** Speaker (Gemma 4 26B A4B-it, fine-tuned). 256K context. Tek thread'de generation.
- **Inject mekanizması:** "Self Jr'ın sokrun ortasından kesilmesi" yeteneği artık Speaker'ın **kendi rotation breakpoint**'inde gerçekleşir. Speaker doğal cümle sonu / tool call / yeni turn boundary'sinde queue'yu yoklar; Sr'dan gelen mesaj varsa context'e ekler.
- **Interrupt mekanizması:** operator UI'dan "stop" / Telegram'dan "dur" yazarsa, orchestrator subprocess'i signal ile durdurur (`SIGTERM` graceful, sonra `SIGKILL`).
- **Classifier ihtiyacı:** Eskiden Watcher'ın yaptığı continue/inject/interrupt classification artık yapılmaz. Speaker'ın kendi prompt eng'i + operator'ın iradesi yeterli.
- **Eğitim datasetinden Watcher etiketleri çıkar:** ARGE §4.4'teki "Watcher dataset (timestamp pattern analizi)" artık ekstrakte edilmez. Reflex pipeline sadece Speaker target turn'ler için.

### 4.5 Otonomi Modeli

Slider 0-10 iptal. ARGE §9.4 threshold tablosu da iptal. Yerine **iki katmanlı sade model**:

```
                EYLEM
                  │
                  ▼
        ┌─────────────────────┐
        │  Destructive mi?    │
        │  (whitelist match)  │
        └─────┬───────────────┘
              │
        ┌─────┴─────┐
       NO          YES
        │           │
        ▼           ▼
    [DEVAM ET]   [SOFT CONFIRM]
                     │
                     ▼
          ┌──────────────────────┐
          │ Telegram'a istek yolla│
          │ "X yapacağım, onay?"  │
          └──────────┬───────────┘
                     │
            ┌────────┴──────────┐
        explicit "yes"      sessizlik / "no"
            │                   │
            ▼                   ▼
        [DEVAM ET]         [İPTAL — kayıt]
                            (3-4 saat sonra)
```

**Destructive whitelist (config'te, başlangıç):**

```yaml
# packages/body/src/selffork_body/sandbox/data/destructive_actions.yaml
destructive_actions:
  - id: prod_deploy
    description: "PROD ortamına deploy / push"
    match_any:
      - tool: git
        args_contains: ["push", "origin", "main"]
      - tool: gh
        args_contains: ["release", "create"]
      - tool: vercel
        args_contains: ["--prod"]
      - env_var_set: ["PROD=1", "NODE_ENV=production"]
    confirm_window_hours: 4

  - id: db_destructive
    description: "Veritabanı yıkıcı eylem"
    match_any:
      - sql_keyword: ["DROP TABLE", "TRUNCATE", "DELETE FROM"]
      - tool: prisma
        args_contains: ["migrate", "reset"]
    confirm_window_hours: 4

  - id: force_push
    description: "Force push"
    match_any:
      - tool: git
        args_contains: ["push", "--force"]
      - tool: git
        args_contains: ["push", "-f"]
    confirm_window_hours: 4

  - id: file_destructive
    description: "rm -rf benzeri silme"
    match_any:
      - tool: rm
        args_contains: ["-rf", "-fr"]
      - tool: find
        args_contains: ["-delete"]
    confirm_window_hours: 4

  - id: account_destructive
    description: "Üçüncü taraf hesap silme / kritik ayar değişimi"
    match_any:
      - url_contains: ["/settings/delete", "/account/close"]
      - http_method: DELETE
        url_contains: ["/api/users/"]
    confirm_window_hours: 4

  - id: financial
    description: "Ödeme / fon transferi / crypto işlem"
    match_any:
      - url_contains: ["stripe.com/payments", "checkout"]
      - tool: cast
        args_contains: ["send"]
    confirm_window_hours: 4

  - id: social_outbound
    description: "Public sosyal mesaj (geri alınamaz)"
    match_any:
      - url_contains: ["twitter.com/intent/tweet", "x.com/intent"]
      - tool: telegram
        args_contains: ["@channel", "@everyone"]
    confirm_window_hours: 4
```

**Soft confirmation timer:** Default 4 saat. Operator UI'da config'ten 30dk / 1h / 2h / 4h / 8h seçer.

**UI surface:** Talk ekranında inline "Pending confirmation: X eylem, kalan süre 3h 27m" badge; Connections > Telegram'da pending list; Dashboard'da count gauges.

**Telegram mesaj formatı:**

```
🤖 Self Jr

Workspace: [ProjectX]
Eylem: PROD'a deploy
Komut: `git push origin main`
Sebep: kanban'da TASK-247 ✓ tamamlandı, CI yeşil, staging onaylı

Onay penceresi: 4 saat (2026-05-17 14:30 GMT+3'e kadar)

[✅ Onay]  [❌ İptal]  [⏰ Bekle 2h]  [💬 Bana sor]
```

Sessizlik (operator cevap vermez) → 4 saat sonra eylem **iptal**, audit log'a "destructive_action_timeout" kaydı.

### 4.6 CLI Router — Yeni Mantık

ADR-003'teki "rotasyon" mantığı revoke. Yeni router girdileri (öncelik sırasıyla):

1. **operator anlık override** (en güçlü). UI Talk'tan veya Telegram'dan: "şimdi sen Gemini'ye geç" / "/cli claude". Router itaat eder, sticky (sessions boyu) veya tek-turn (geçici).
2. **Quota kalan** (subscription pencere). Provider başına derive edilen kalan token/dakika. Eşik altına düştüğünde (varsayılan: <%10) router otomatik diğer adaya geçer.
3. **RAG geçmiş performans** (project-CLI affinity). Geçmiş session'lardan derive edilen başarı skoru: bu workspace × bu task tipinde hangi CLI ne kadar başarılı (turn-to-task-complete metric). RAG store'da `(project_slug, task_type, cli) → success_rate` kaydı.

Router girdisi olmayan (ADR-006 ile düşürülen):
- **Statik task-tipi → CLI mapping.** ("UI = Gemini" gibi sabit kural yok; bu öğrenilir, statik yazılmaz.)
- **Rotasyon takvimi.** ("Pazartesi Claude, Salı Codex" gibi takvim yok.)
- **Pricing/cost optimization.** (Henüz değil; ileride faz 2 router girdisi olabilir.)

**Algoritma (yüksek seviyede):**

```python
def select_cli(workspace, task, candidates) -> CLI:
    if explicit_override := get_active_override(workspace):
        return explicit_override

    eligible = [c for c in candidates if quota_remaining(c) > THRESHOLD]
    if not eligible:
        return raise QuotaExhaustedAcrossFleet()

    scores = {c: rag_performance_score(workspace, task, c) for c in eligible}
    return max(scores, key=scores.get)
```

**ADR-003 patch:** §router-strategy bölümü güncellenir; "rotasyon" kelimesi metinden çıkarılır; üç-girdili score function dokümante edilir.

**S6 implementasyon notu (2026-05-24, [[s6-complete-2026-05-24]]):** affinity'ye **model boyutu** eklendi — `select_cli` artık `(cli, model)` döner; gate sırası operatör override → per-model quota gate (gemini per-model; ToS-safe reactive, direct-API `retrieveUserQuota` BAN) → affinity argmax. Self Jr bunu 8 router tool ile (4 write + 4 read), operatör 3 yüzeyle (Theater "Switch CLI" dialog · Talk `/cli` · Telegram `/cli`) yönetir. minimax-cli router adayı DEĞİL (opencode→M2.7). Cost/rotasyon hâlâ YOK.

### 4.7 Telegram Bridge — İki Yönlü

PTB altyapısı (`b57a765` commit) korunur. Bridge'in iki kanal'ı:

#### 4.7.1 Jr → Sr (proaktif)

Kullanım senaryoları:
- **Destructive onay** (yukarıda §4.5).
- **İhtiyaç bildirim:** "Supabase auth gerekiyor", "Stripe webhook secret nereye gireceğimi bilmiyorum", "App Store screenshot upload elle gerekli."
- **Major karar bildirim:** "X kütüphanesini ekledim, package.json güncellendi" (audit hash + diff özet).
- **Hata report:** "Build kırıldı: TypeError at app/page.tsx:47". Stack trace + suggested fix.
- **Daily/weekly özet:** "Bu hafta: 12 task complete, 3 PR merged, 47 saat aktif."

#### 4.7.2 Sr → Jr (ad-hoc)

Kullanım senaryoları:
- **İş ekleme:** "[ProjectX] frontend testlerini de ekle"
- **Hızlı soru:** "[ProjectX] şu an hangi task'tasın?"
- **Anlık inject:** "DUR, login flow değil önce signup ekle"
- **CLI override:** "/cli claude" (router'a sticky override)
- **Workspace switch:** "/workspace ProjectY"

#### 4.7.3 Bridge protokolü

Telegram → orchestrator HTTPS webhook. orchestrator → router → Speaker. Sr cevapları Speaker'ın aktif Talk session'ına inject olur (active workspace context'te). Eğer aktif workspace yoksa, Sr mesajı "drafts" queue'ya düşer; operator UI Talk'a girince "Telegram'dan 3 mesajın var" notifier görür.

#### 4.7.4 UI surface

Connections sayfasında Telegram kartı:
- Bot token alanı + setup wizard (BotFather instructions)
- "Test mesaj gönder" butonu
- Webhook URL (sunucu domain'i)
- Onay penceresi default süresi config
- Mesaj log (son 50)

---

## 5. UI Surface — 5 Ekran

### 5.1 Persona ve Stil

**Persona:** P+Prompt Engineer.

Profil:
- Senior level (10+ yıl operator gibi VEYA bilgisayar-okur-yazar non-engineer).
- Kod yazmaz, prompt yazar.
- CLI/agent ekosistemini bilir (Claude Code, Codex, Lovable, v0, Cursor).
- Birden çok proje paralel sürer.
- Mobile-first değil ama mobile-aware (Telegram bridge için).

**Stil — middle ground:**
- Cursor/Lovable "tek input + magic" değil. Power user kontrolleri açık.
- PRD §8.5 "light-enterprise dashboard" değil. Audit/log/metric gürültüsü yok.
- **"Linear v1 + Replit Agent + Vercel dashboard sade-power"** karışımı.
- **Calm, hierarchical, focused** — bir ekranda bir iş, anchor element büyük, kalan element küçük.

**Tipografi:** Inter (sans), tabular-nums (gauges için). Display fontu yok.

**Renk sistemi:** Light enterprise. Tek primary (mavi tonu, PRD'nin önerdiği `221 100% 39%` korunur). Surface tonları: white / 50 / 100 / 200. Borders 200. Text 700 / 500.

**Iconography:** Lucide. Material Symbols opsiyonu reddedildi (build size).

### 5.1.1 Operatör Günlük Akışı (Operator Journey)

UI'ı doğru kavramak için önce operatörün **bir günü** — bu, 5 ekranın
neden bu sırada ve bu biçimde olduğunu açıklar:

1. **Sabah, Dashboard.** Operatör girer girmez 5 CLI'nin kota durumunu
   (claude/codex/gemini/minimax/glm — kalan pencere + reset) ve Self
   Jr'ın o an hangi workspace'te ne yaptığını (Live Loop hero) görür.
2. **Workspace seçer.** Kanban'da o sprint'in task'ları zaten hazırdır —
   operatör onları Jira-stili önceden planlamıştır.
3. **Self Jr çalışır.** Bir task'ı alır; task tipine + kalan kotaya +
   geçmiş performansa göre bir CLI seçer (rotasyon değil — §4.6 router),
   ona prompt yazar. Operatör **Live Run** tab'ında CLI'nin kod
   üretişini "film izler gibi" izler (3-pane theater).
4. **Self Jr test eder.** Ürettiği şeyi ayağa kaldırır (web/mobil),
   vision ile kontrol eder, sonraki prompt'u yazar. **Operatör tek
   satır kod yazmaz.**
5. **Operatör araya girer — iki yol.** Masadaysa **Talk** ekranından
   doğrudan Self Jr ile konuşur (yön düzelt, CLI değiştir). Dışarıdaysa
   **Telegram**'dan aynı şeyi yapar.
6. **Self Jr ihtiyaç bildirir.** Bir dış bağımlılığa takılırsa (örn.
   "Supabase auth bağlaman gerek") Telegram'dan operatöre yazar.
7. **Destructive eylem = onay.** PROD push / DB drop gibi bir eylem
   gerektiğinde Self Jr Telegram'dan onay ister; operatör 4 saat içinde
   onaylamazsa eylem iptal (§4.5 fail-safe NO).

Operatörün rolü: **task tanımlamak, prompt akışını yönlendirmek, çıktıyı
denetlemek** — yani P+Prompt Engineer. SelfFork bu döngüyü operatör
uyurken / işteyken / dışarıdayken de yürütür ("uyumayan ikinci ben").

### 5.2 Bilgi Mimarisi (IA)

```
┌─────────────────────────────────────────────┐
│  Sidebar (collapsible, [ tuşu)              │
│  ─ Dashboard                                │
│  ─ Workspaces (lista, aktif vurgu)          │
│    ├─ ProjectX                              │
│    ├─ ProjectY                              │
│    └─ + New                                 │
│  ─ Talk                                     │
│  ─ Connections                              │
│  ─ Settings                                 │
│                                             │
│  ─────────── (bottom)                       │
│  ─ Jr status: ● Online                     │
│  ─ Model: gemma-4-26b @ lokal              │
└─────────────────────────────────────────────┘
```

Ana navigasyon **sidebar** — Stitch v2'deki sidebar korunur, içerik revize.

### 5.3 Ekran 1 — Dashboard

**Amaç:** Operator giriş yapar yapmaz "Jr şu an ne yapıyor, kaynaklar ne durumda, hangi projeye girmeliyim" cevabını alır.

**Layout (yukarıdan aşağı):**

```
┌──────────────────────────────────────────────────────────────┐
│  Top — CLI Quota Gauges                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ claude     │  │ codex      │  │ gemini     │   ...      │
│  │ ████░░ 67% │  │ ██████ 92% │  │ ██░░░░ 23% │            │
│  │ 4h 12m    │  │ resets 5h  │  │ 1d 8h     │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│                                                              │
│  Mid — Live loop status                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🔴 LIVE · ProjectX · Claude CLI · 12 dk 47 sn       │  │
│  │ "Login flow testliyor — Supabase auth screen"        │  │
│  │ [Open Workspace →]                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Mid-2 — Recent activity feed (kompakt)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 5 dk önce · ProjectX · ✓ TASK-12 tamamlandı         │  │
│  │ 12 dk önce · ProjectY · 🔔 Supabase auth gerekli   │  │
│  │ 47 dk önce · ProjectX · 🤖 Claude → Codex (quota)  │  │
│  │ 1 saat önce · ProjectX · ⚠️ Destructive pending     │  │
│  │ [Show all →]                                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Bottom — Projects grid                                     │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────┐  │
│  │ ProjectX   │ │ ProjectY   │ │ ProjectZ   │ │ + New  │  │
│  │ 🔴 SHIPPING│ │ 💤 SLEEPING│ │ ⏳ PENDING │ │        │  │
│  │ 12/24 task│ │ 0/8 task  │ │ Auth waits│ │        │  │
│  └────────────┘ └────────────┘ └────────────┘ └────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Components:**
- `<QuotaGaugeCard provider="claude" />` — ring chart + remaining time + reset window
- `<LiveLoopStatus />` — single hero card, animated ● indicator, anchor link
- `<RecentActivityFeed limit={5} />` — Body audit event derivation, compact
- `<ProjectCard status="shipping" />` — kanban özet + last activity

**Etkileşim:**
- Project card click → Workspace
- Live loop card click → ilgili Workspace + Live Run Theater
- Quota gauge click → Connections > provider detail

**Yok olan (PRD §8.5'ten silinen):**
- Fleet Command Center karmaşası — projeler grid + loop status yeterli
- Provider quota bar chart (ayrı surface yerine top strip)
- Audit event timeline (Recent activity 5'lik kompakta indi)

### 5.4 Ekran 2 — Workspace

**Amaç:** Bir projeye girince operator kanban + canlı işlem + Jr notları üçlüsünü görür. **Live Run Theater** çekirdek.

**Layout (3-bölge, sekme yok — flat scroll):**

```
┌──────────────────────────────────────────────────────────────┐
│  Header: ProjectX · 🔴 SHIPPING · Last: 2 dk önce            │
│  [Switch workspace ▼] [Edit] [Archive]                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ─── Kanban ──────────────────────────────────────────────  │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Backlog  │  │ In prog. │  │ Review   │  │ Done     │    │
│  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │    │
│  │ │TASK-13│ │  │ │TASK-12│ │  │ │TASK-11│ │  │ │TASK-10│ │    │
│  │ └──────┘ │  │ └──────┘ │  │ └──────┘ │  │ └──────┘ │    │
│  │ ┌──────┐ │  │          │  │          │  │ ┌──────┐ │    │
│  │ │TASK-14│ │  │          │  │          │  │ │TASK-9 │ │    │
│  │ └──────┘ │  │          │  │          │  │ └──────┘ │    │
│  │ + Add    │  │          │  │          │  │          │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                              │
│  ─── Live Run Theater (3-pane) ──────────────────────────  │
│                                                              │
│  ┌────────────────┬────────────────┬────────────────────┐  │
│  │ CLI output     │ Screenshot     │ Jr düşünce balonu │  │
│  │                │ timeline       │                    │  │
│  │ $ npm run dev  │  ┌──┐ ┌──┐ ┌──┐│ "Supabase auth    │  │
│  │ > started      │  │  │ │  │ │  ││  ekranını inceli- │  │
│  │ ✓ ready :3000  │  └──┘ └──┘ └──┘│  yorum. Email kut-│  │
│  │                │  10:23 10:24 ..│  usu görünür ama..│  │
│  │ Self Jr:      │                │  password placeh- │  │
│  │ "lütfen logini│  ┌──────────┐  │  oldera tıklamam   │  │
│  │  test et"      │  │ active   │  │  lazım."          │  │
│  │ Claude:        │  │ screen   │  │                    │  │
│  │ I'll check ... │  │ preview  │  │ Next prompt:      │  │
│  │                │  │          │  │ "şimdi geçersiz   │  │
│  │ [auto-scroll]  │  └──────────┘  │  password gir ve  │  │
│  │                │                │  hatayı gözle"    │  │
│  └────────────────┴────────────────┴────────────────────┘  │
│  Active CLI: claude · turn 47/∞ · 12m 47s                  │
│                                                              │
│  ─── Jr'ın proje notları ─────────────────────────────────  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 📝 ProjectX notlarım                                 │  │
│  │                                                       │  │
│  │ • Supabase auth flow: magic-link tercih edildi.      │  │
│  │   Email confirmation REQUIRED.                       │  │
│  │ • Login flow şimdiye kadar 3 kez kırıldı —          │  │
│  │   sebep: env değişkeni yanlıştı. SUPABASE_URL.       │  │
│  │ • operator tercihi: server actions değil API route. │  │
│  │ • Yapılacak: e2e testleri Playwright ile,            │  │
│  │   CI'da headless.                                    │  │
│  │                                                       │  │
│  │ [+ Add note]  [Edit]  Last update: 8 dk önce        │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Components:**
- `<WorkspaceHeader />` — title + status + switch dropdown
- `<KanbanBoard projectId={...} />` — drag-drop, 4 column varsayılan, configurable
- `<LiveRunTheater projectId={...} />` — 3-pane composite
  - `<CLIOutputPane />` — terminal stream + ansi color + auto-scroll lock
  - `<ScreenshotTimeline />` — Body M5 vision çıktıları, hover ile büyüt
  - `<JrThoughtBubble />` — Speaker reasoning excerpt (filtered, see §5.4.1)
- `<ProjectNotes projectId={...} />` — markdown editor, RAG store backing

#### 5.4.1 Jr düşünce balonu içeriği — filtreleme

Gemma 4'ün thinking mode `<think>...</think>` çıktısı **ham** olarak gösterilmez (token barbarlığı + okunamazlık). Yerine:

- Speaker `<think>` çıktısının her segmenti için bir "summary line" Speaker tarafından üretilir (post-think compaction)
- Bu summary line `<JrThoughtBubble />` içinde gösterilir
- Operator "expand raw thinking" toggle ile ham `<think>` görebilir (power user)
- Maksimum 4 cümlelik düşünce penceresi; eskiler kayar

Speaker prompt template'inde `<thought_summary>...</thought_summary>` block beklenir, parser orchestrator'da.

#### 5.4.2 Live Run Theater state model

Three-pane data binding:

```typescript
interface LiveRunTheaterState {
  activeCLI: 'claude' | 'codex' | 'gemini' | 'minimax' | 'glm';
  cliSession: { turn: number; startedAt: ISO8601; tokensUsed: number };
  cliOutput: ANSIStream;            // streaming, ws-pushed
  screenshots: Screenshot[];        // [{ at, blob, source: 'browser'|'mobile-emu' }]
  jrThoughts: ThoughtSummary[];     // [{ at, summary, raw? }]
  nextPrompt?: string;              // preview of upcoming Speaker output
  alerts: Alert[];                  // destructive pending, error, etc.
}
```

WebSocket channel: `/ws/workspace/{slug}/theater`. Orchestrator multiplex.

### 5.5 Ekran 3 — Talk

**Amaç:** operator ↔ Speaker direkt iletişim. Project-context-aware.

**Layout (Cursor/Claude.ai tarzı):**

```
┌──────────────────────────────────────────────────────────────┐
│  Header: Talk — All projects · Speaker: Self Jr            │
│  Context: [Auto-detect (ProjectX) ▼]                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                                                              │
│  [operator] login flow nasıl ilerliyor?                    │
│                                                              │
│  [Self Jr] Magic-link auth ile ProjectX'te ilerliyorum.   │
│            Supabase email confirmation zorunlu, 2 dk önce   │
│            test mail attım, doğrulama bekliyor. Gemini'yi   │
│            kapatıp Claude'a geçtim çünkü Supabase JS API    │
│            tipleri daha karmaşıktı.                          │
│                                                              │
│            [Workspace: ProjectX] [Live → ]                  │
│                                                              │
│  [operator] Codex'i kullan, daha hızlı                     │
│                                                              │
│  [Self Jr] Anlaşıldı. Bu workspace için sticky override   │
│            uygulanıyor: ProjectX → Codex.                   │
│            Claude session'ı temiz kapatılıyor...            │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────┐    │
│  │ Type a message... (Enter to send, Shift+Enter NL)   │    │
│  └────────────────────────────────────────────────────┘    │
│  [Attach file] [Quick chips: /workspace /cli /pause]       │
└──────────────────────────────────────────────────────────────┘
```

**Context auto-detect:** "Auto-detect" mode aktifse Talk'taki son mesaj veya recent activity'den workspace çıkarımı yapılır. Operator override edebilir.

**Quick chips:**
- `/workspace ProjectY` — workspace switch
- `/cli gemini` — sticky CLI override
- `/pause` — Jr'ı durdurur (tüm aktif session'lar SIGTERM)
- `/resume` — pause sonrası devam
- `/note <text>` — aktif workspace notlarına ekler
- `/jira-sync` — Jira pull/push (opsiyonel, bkz §6)

### 5.6 Ekran 4 — Connections

**Amaç:** Subscription auth + quota tracking + Telegram bridge config tek yerde.

**Layout:**

```
┌──────────────────────────────────────────────────────────────┐
│  Connections                                                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  CLI Providers                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🟢 Claude Code (Anthropic Pro)                       │  │
│  │    Subscription: Pro · 67% quota left · resets 4h12m │  │
│  │    Active sessions: 1 · workspaces: ProjectX         │  │
│  │    [Sign out] [Test connection] [View history]       │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🟢 Codex (ChatGPT Plus)                              │  │
│  │    Subscription: Plus · 92% quota · resets in 5h     │  │
│  │    [Sign out] [Test connection]                      │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🟡 Gemini CLI (Google AI Studio)                     │  │
│  │    Subscription: Free Tier · 23% quota · 1d 8h reset │  │
│  │    [Sign out] [Test connection]                      │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ⚫ Minimax (not signed in)                            │  │
│  │    [Sign in →]                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ⚫ GLM (Zhipu)                                        │  │
│  │    [Sign in →]                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Telegram Bridge                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🟢 Connected as @yamac                              │  │
│  │    Bot: @SelfJrBot                                   │  │
│  │    Webhook: https://selffork.example.com/tg         │  │
│  │    Soft confirmation window: 4 hours                 │  │
│  │    Last activity: 5 dk önce (TASK-12 onayı)         │  │
│  │    [Send test] [View log] [Settings]                │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Sign-in flow:**

Operator "Sign in" tıklar → sunucu Playwright headless browser açar → orchestrator UI'ya browser canvas mirror eder (live screenshot stream) → operator UI içinden OAuth flow'unu tamamlar (kullanıcı adı, parola, MFA UI'da girilir, sunucu üzerinden provider'a iletilir) → auth cookies sunucuda persisted → status 🟢.

Bu Body M5'in driver'ının zaten yapabildiği bir akış; ADR-005 §provider_auth bölümü implementation referansı.

### 5.7 Ekran 5 — Settings

**Amaç:** Model endpoint + fine-tune UI + Telegram + theme + advanced.

**Layout (collapsible sections):**

```
┌──────────────────────────────────────────────────────────────┐
│  Settings                                                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ▼ Model Endpoint                                           │
│    [bkz §4.3 — Endpoint URL config]                         │
│                                                              │
│  ▼ Fine-tune                                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Training dataset                                    │  │
│  │  Source: [● Auto from session history               ]│  │
│  │          [○ Manual path: /path/to/dataset.jsonl     ]│  │
│  │                                                       │  │
│  │  Total examples: 8,432 (after CoT scoring)          │  │
│  │  Estimated turn: 5h 18m (on remote GPU)             │  │
│  │                                                       │  │
│  │  Hyperparams                                          │  │
│  │    Method:        [QLoRA ▼]                          │  │
│  │    LoRA rank:     [32      ]                         │  │
│  │    LoRA alpha:    [16      ]                         │  │
│  │    Learning rate: [2e-4    ]                         │  │
│  │    Epochs:        [3       ]                         │  │
│  │    Target modules: [attention only ▼]                │  │
│  │                                                       │  │
│  │  Training endpoint                                    │  │
│  │    [○ Same as model endpoint                        ]│  │
│  │    [● Separate: https://train.gpu.example.com       ]│  │
│  │                                                       │  │
│  │  [▶ Start training] (current adapter v1.2 — 47d old)│  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ▼ Telegram bridge                                          │
│    Soft confirmation window: [4 hours ▼]                    │
│    Destructive whitelist editor → [Open]                    │
│                                                              │
│  ▼ Theme                                                    │
│    [● Light] [○ Dark] [○ System]                            │
│    [Use enterprise palette ☑]                               │
│                                                              │
│  ▼ Advanced (power user)                                    │
│    Show Jr raw thinking ☐                                   │
│    Show audit event timeline ☐                              │
│    Show vision tier details ☐                               │
│    Workspace data directory: /opt/selffork/data             │
│    Reset RAG embeddings → [Reset]                           │
│    Open API key (acil fallback) → [Configure]               │
└──────────────────────────────────────────────────────────────┘
```

**Önceki Stitch v2'deki "6 toggle + Advanced link" sadeliği korunur, ama power user için derinlik açık.**

---

## 6. Açık Sorular (Open Questions)

ADR-006'da kilitlenmemiş, sonraki ADR/commit'lerde çözülecek noktalar:

### 6.1 Kanban kaynağı
**Soru:** Jira gerçek API mi (real-time sync), yoksa SelfFork-içi lokal kanban (Jira import/export)? Linear / GitHub Projects desteği?
**Default tutulan:** Lokal kanban (SQLite), JSON import/export (Jira CSV format dahil). Jira gerçek API faz 2.

### 6.2 Jr proje notlarının kaynağı
**Soru:** Speaker auto-extract mi (session geçmişinden RAG'le çıkarım), yoksa manuel notebook mu, yoksa hibrit mi?
**Default tutulan:** Hibrit. Speaker auto-extract daily özet üretir; operator UI'dan manuel düzenleyebilir.

### 6.3 Vision tier UI görünürlüğü
**Soru:** Body M5'in vision tier'ı (1/2/3) Live Run Theater'da görünür mü?
**Default tutulan:** Power user toggle arkasında (Settings > Advanced > Show vision tier).

### 6.4 iOS native app
**Soru:** Telegram kalıcı arayüz mü, yoksa Faz 3'te iOS native app gelir mi?
**Default tutulan:** Telegram + web cockpit yeterli (M6 hedef). iOS native app M8+ değerlendirilir.

### 6.5 Multi-machine genişletme
**Soru:** Multi-machine fleet (ARGE §8) feature flag arkasında ileride opsiyonel mi gelir?
**Default tutulan:** Evet, M9+ opsiyonel. Önce tek-sunucu vizyonu sağlamlaşsın.

### 6.6 Mobil emülasyon driver'ı
**Soru:** Body M5 mobile-use driver sunucu deployment'ta nasıl koşar? (docker-android + Android emulator sunucuda heavy)
**Default tutulan:** Cloud emulator service (Genymotion Cloud, Browserstack) opsiyonel; lokal emulator power user için.

### 6.7 Speaker context boyutu
**Soru:** Watcher iptaliyle Speaker'a tek başına 256K context dolarsa lost-in-the-middle riski?
**Default tutulan:** ARGE §5.1 hedef pencere ~12-16K, 256K uç durumda. Context manager pillar Mind'da; lost-in-the-middle önlemi compaction.

### 6.8 Destructive whitelist genişleme
**Soru:** Whitelist initial set §4.5'te; community kuralları nasıl eklenir (template, share, marketplace)?
**Default tutulan:** YAML config, faz 2 community marketplace.

### 6.9 Çoklu kullanıcı
**Soru:** SelfFork single-operator (PRD §5.1) — multi-user (aile, ekip) destek olur mu?
**Default tutulan:** HAYIR, en azından M6'da. PRD §5.1 stricture korunur; multi-user faz 4.

---

## 7. Pillar Etkisi

### 7.1 Reflex (Pillar 1)

- **Watcher iptali:** Dataset pipeline'ından Watcher classifier eğitimi maddesi düşer. Sadece Speaker turn target'lerine odaklan.
- **Fine-tune UI:** `apps/web/settings/finetune` yeni surface. Backend `packages/reflex/training/` endpoint expose eder. Operator UI'dan tetikler.
- **Remote training endpoint:** Model endpoint'ten ayrı eğitim endpoint'i (Settings'te). Sunucuda CPU training pratik değil; varsayılan training = remote GPU.
- **Adapter versioning:** UI'da current adapter version + age + "retrain" CTA.

### 7.2 Body (Pillar 2)

- **Auth flow:** ADR-005'in provider_auth implementasyonu **birinci sınıf surface** olur (Connections ekranı). Headless browser sunucuda; UI mirror canvas.
- **Vision drivers:** Live Run Theater'ın orta-pane'i Body'nin screenshot çıktısı. Vision tier seçimi Power user advanced.
- **Permission warden:** Destructive whitelist (§4.5) artık warden'in **canonical rule source**'u. ADR-005 §permission_warden patch: warden YAML whitelist okur, soft confirmation tetikler.
- **Multi-machine mesh iptal:** Body daemon **tek sunucuda**. ADR-005 §multi_machine bölümü "deferred" işaretlenir.

### 7.3 Mind (Pillar 3)

- **CLI router RAG:** Project-CLI affinity store (§4.6) Mind'a eklenir. Yeni schema: `(workspace_slug, task_type, cli) → (success_rate, avg_turns, last_used)`. **S6 (2026-05-24):** schema'ya **model** boyutu eklendi → `(workspace_slug, task_type, cli, model) → score`; `select_cli` `(cli, model)` döner. Bkz [[s6-complete-2026-05-24]].
- **Jr proje notları:** Mind'ın "decisions / historian" surface'inin yeni front-end. RAG store backing.
- **Telegram message store:** Sr ↔ Jr mesajları Mind'a ingest edilir (sessions koleksiyonu altında, source=telegram).
- **Context compaction:** Speaker 256K tek başına; compaction Mind'ın işi (PRD §3'teki "deterministic lossless context management").

---

## 8. PRD / ROADMAP Etki Patch'leri

Bu ADR ile birlikte aşağıdaki dokümanlar **revize edilmeli** (ayrı commitlerde, ADR kabul edildikten sonra):

### 8.1 PRD.md

| Bölüm | Eski (PRD) | Yeni (ADR-006) | Aksiyon |
|---|---|---|---|
| §5.1 | Single-operator senior engineer (anti-persona: Generic Assistant User) | **P+Prompt Engineer.** Non-engineer'a açık ama power-aware. Sigma: single-operator korunur. | edit |
| §8.5 Cockpit | Vite + React + vanilla CSS, "light enterprise theme", Fleet Command Center, Workspace 4-tab (Mission/Run/Chat/Ctxt) | Next.js + Tailwind + shadcn (uyumlu). Cockpit IA = 5 ekran (Dashboard/Workspace/Talk/Connections/Settings). | rewrite |
| §15 Threshold table | Statik 0-10 threshold matrix | Yerine §4.5 destructive whitelist + soft confirmation | replace |
| §19.1 Action Audit Log | Canonical surface | Power user advanced toggle (default gizli) | downgrade |

### 8.2 ROADMAP.md

| Milestone | Eski | Yeni | Aksiyon |
|---|---|---|---|
| M4 Cockpit | Fleet Command + 4-tab Workspace + slider + emergency kill | Dashboard + Workspace (3-pane theater) + Talk + Connections + Settings + (no slider) | rewrite |
| M5 Body | Provider auth + body daemon + vision drivers | KORUNUR (UI surface revize, Connections ekranı) | minor edit |
| M6 (new) | — | **v2 Pivot Implementation:** sunucu deploy + Watcher iptal + UI v3 + destructive whitelist + Telegram surface + fine-tune UI | add |

### 8.3 ADR-001 (MVP v0)

| Bölüm | Aksiyon |
|---|---|
| §UI surface (apps/ empty until M4) | "M4 → M6'ya kaydırıldı, kapsam ADR-006'ya bakın" not eklenir |
| §853 hibrit dil reddi | Korunur; cockpit Next.js + TS zaten kabul |

### 8.4 ADR-003 (M3 CLI Surfing)

| Bölüm | Aksiyon |
|---|---|
| §router-strategy | Rewrite — rotasyon→üç-girdili score function (quota + override + RAG) |

### 8.5 ADR-004 (M4 Cockpit)

| Bölüm | Aksiyon |
|---|---|
| Tüm IA (4-tab) | **Superseded by ADR-006 §5.2-§5.7.** Doküman üstüne "SUPERSEDED" banner. |

### 8.6 ADR-005 (M5 Body)

| Bölüm | Aksiyon |
|---|---|
| Multi-machine bölümü | "Deferred to M9+" işaretlenir |
| Cockpit ek route'ları (/cockpit/{fleet,providers,body}) | Connections + Dashboard'a katlanır; ayrı route'lar kaldırılır |
| Permission warden statik tablo | §4.5 destructive whitelist'e referans eklenir |

### 8.7 apps/web/DESIGN.md

| Aksiyon |
|---|
| **Rewrite to v3** — bu ADR'nin §5'iyle birebir tutarlı, Stitch v2 minimalist tek-satırlık doc'u tamamen yenilenir. |

---

## 9. Implementation Plan (M6)

ADR-006 kabul sonrası iş paketleri:

### 9.1 Faz M6.0 — Foundation (1-2 hafta)
- [ ] DESIGN.md v3 yaz (bu ADR §5'iyle bire bir)
- [ ] Stitch ile 5 ekran yeniden tasarım (DESIGN.md v3 feed)
- [ ] apps/web Stitch v2 cleanup (rollback gerekiyorsa veya progressive replace)
- [ ] ARGE §7-§9 revoke notlarını PDF özetine düş (yeni archive note)

### 9.2 Faz M6.1 — Server deployment (1 hafta)
- [ ] `infra/deploy/` Linux server provisioning (docker-compose veya bare-metal)
- [ ] CPU model fallback (lokal mlx-vlm + Mac mini'ye Tailscale sunucu erişimi)
- [ ] Browser-driven auth sunucuda (Playwright + xvfb)
- [ ] Auth state persistence schema

### 9.3 Faz M6.2 — Speaker-only refactor (1 hafta)
- [ ] Reflex pipeline: Watcher dataset+classifier kaldırma
- [ ] Orchestrator: Watcher subprocess remove
- [ ] Inject/interrupt: Speaker breakpoint mechanism

### 9.4 Faz M6.3 — Destructive whitelist + soft confirm (1 hafta)
- [ ] `packages/body/src/selffork_body/sandbox/data/destructive_actions.yaml` schema + parser
- [ ] Body warden integration
- [ ] Telegram approval flow (proaktif mesaj + onay/iptal callback)
- [ ] Pending confirmation UI badge

### 9.5 Faz M6.4 — UI v3 (3-4 hafta)
- [ ] Dashboard (quota gauges + live loop + activity + projects grid)
- [ ] Workspace (kanban + 3-pane theater + notes)
- [ ] Talk (chat + context auto-detect + slash chips)
- [ ] Connections (5 provider + Telegram surface)
- [ ] Settings (model endpoint + fine-tune + Telegram window + theme + advanced)

### 9.6 Faz M6.5 — Fine-tune UI (1-2 hafta)
- [ ] Settings > Fine-tune section
- [ ] Backend trigger endpoint (POST /api/reflex/train)
- [ ] Progress polling (WebSocket)
- [ ] Adapter version display + retrain CTA

### 9.7 Faz M6.6 — Telegram bridge surface (3-5 gün)
- [ ] Webhook setup wizard
- [ ] Bot setup instructions
- [ ] Two-way message routing (Sr → workspace inject)
- [ ] Activity log

### 9.8 Faz M6.7 — Smoke + close-out (1 hafta)
- [ ] E2E smoke checklist (sunucu deploy + 5 ekran walkthrough)
- [ ] PRD/ROADMAP/ADR-001/003/004/005 patch commitleri
- [ ] M6 close-out memory + ADR (sonraki ADR)

**Toplam tahmin:** 10-13 hafta — tek operatör, "kaliteye kaçarım" ritmi.

---

## 10. Risk ve Trade-off

### 10.1 Tam otonom destructive eylemler

**Risk:** Soft confirmation 4 saatlik pencere, fail-safe NO; ama operator **uyuyorsa veya konferansta**, kritik bir destructive eylem 4 saat sonra **iptal** olur. Bu iyi (yanlış otomatik aksiyondan koruma) ama bazen **gerçekten yapılması gereken** eylem kaçar.

**Mitigation:**
- Kategori başına timer ayrı konfigüre edilebilir (`prod_deploy = 4h`, `social_outbound = 1h`)
- operator Telegram'dan `/extend 8h` ile pencereyi uzatabilir
- `/yes-always` style global onay (workspace başına) — power user, opsiyonel
- Critical-but-routine eylemler (örn. routine CI deploy) whitelist'ten **çıkarılabilir** (manuel onaylı override "this is not destructive for ProjectX context")

### 10.2 Watcher iptaliyle inject kaybı

**Risk:** ARGE'nin full-duplex çözümü iptal; Speaker tek thread, generation sırasında dinleyemez. P+Prompt Engineer iş akışında bu kritik mi?

**Cevap:** Hayır. Operator zaten manuel CLI'ye yazar (Talk veya Telegram'dan). Watcher daemon-style auto-inject, P+Prompt Engineer döngüsünde **gereksiz karmaşa**. Eğer faz 2-3'te tekrar gerekirse Watcher reintroduce edilebilir.

### 10.3 Tek sunucu single point of failure

**Risk:** Sunucu down → her şey down. Multi-machine mesh ARGE §8 bunu çözüyordu; iptal edildi.

**Mitigation:**
- Persistent state SQLite + WAL mode, snapshot backup (`cron` günlük)
- Çoklu sunucu deployment ADR-006 §6.5'te ileride opsiyonel
- Acil fallback: Model endpoint = Anthropic/Google API (eğitilmemiş, çalışmaya devam)

### 10.4 CPU sunucu performansı (başlangıç durumu)

**Risk:** Operator GPU sunucu alana kadar SelfFork CPU sunucuda. CLI'ler + headless browser + RAG ingest CPU'ya yük bindirir.

**Mitigation:**
- Model endpoint **lokal Mac**'te (operator zaten Mac'te); ağır LLM CPU sunucudan ayrı.
- CLI'ler subprocess olduğu için CPU sunucuda hafif.
- RAG embedding Jina API (lokal embedding yok, CPU rahat).
- Headless browser × 1 instance, paylaşım.
- Beklenen CPU yük: orta. 2-4 vCPU sunucu yeterli başlangıçta.

### 10.5 Stitch v2'nin atılması

**Risk:** 2026-05-16 gecesi yapılan iş (uncommitted 13+9 dosya) çöpe gidiyor mu?

**Cevap:** Tam değil. **Foundation korunabilir:** Inter font import, Material-3 token paleti, sidebar component, topbar component. **İçerik atılır:** Home/Workspaces/Talk/Connections/Settings page'leri DESIGN.md v3 spec'iyle yeniden yazılır. Stitch design system asset (`9d2751c7cf544707904ba33bfce4602c`) korunur veya update edilir.

### 10.6 Açık kaynak self-host vs operator kendi yaşanmışlığı

**Risk:** Açık kaynak hedef = "isteyen kendi sunucusuna kurar." Bu, fine-tune dataset'in **operator-özel** olduğunu unutturmamalı. Başka biri SelfFork kurarsa, **kendi Self Jr'ını kendi datasından eğitir** — operator'ın adapter'ı paylaşılmaz.

**Mitigation:** README + onboarding wizard "Bu adapter sizin verinizden eğitilir, paylaşılmaz" mesajı verir. ARGE'nin "Yamaç = Yamaç" ruhu fork-friendly korunur (cf. `[[brand-is-selffork-not-personal-name]]`).

---

## 11. Onay Tarihçesi

Bu ADR aşağıdaki AskUserQuestion turlarıyla iteratif onaylanmıştır:

1. **2026-05-17 — UI kök yön:** "benim asıl vizyonum bu dökümanda /docs/archive/Yamac_Jr_ARGE.pdf"
2. **2026-05-17 — Hedef kitle + Watcher + akış:** "1- non-engineer kitle kalabilir... 2- watcher model iptal... 3- aslında P+Prompt engineer'ım"
3. **2026-05-17 — Slider akıbeti:** "slider iptal et yamaç JR a full otonom güven!"
4. **2026-05-17 — Model konumu:** "Hibrit — kullanıcı endpoint seçer"
5. **2026-05-17 — Live Run Theater:** "3 pane theatre seçiyorum"
6. **2026-05-17 — CLI router:** "rotasyon şeklinde değil daha çok task'e göre seçim + sessionu varsa ona göre" → quota + override + RAG
7. **2026-05-17 — Lokal makine rolü → deployment:** "isteyen herkes bir linux GPU sunucuya selffork kurup diledikleri projeyi yaptırabilsinler isterim! ... CPU sunucuda ayağa kaldırırım... settingsden benim localimdeki modeli kaldırırım"
8. **2026-05-17 — Destructive eylem:** "Soft confirmation (30sn) tarzı... ya da 3-4 saat yapalım onu!"
9. **2026-05-17 — ADR yazımı:** "BAŞLA ÖNCE UI/UX i baştan... adr-006 yı da yaz istersen hemen ama onu DOMİNE et bu adr en önemlisi olsun!"

Bu ADR **operator onayını bekleyen V1 taslak**tır. Onay sonrası 12-madde karar bloğu kilitli, §5 UI spec DESIGN.md v3'ün kaynağı, §9 Implementation Plan M6'nın iskeleti olur.

---

## 12. Bağlantılı Memory Slugs (Cross-Link)

Bu ADR aşağıdaki auto-memory girdileri ile ilişkilidir:
- `[[v2-ui-rebuild-inprogress]]` — superseded by this ADR
- `[[ui-minimalist-user-first]]` — partial supersession (non-engineer kitle açık AMA "Stitch v2 sade-çocuk-UI" reddi)
- `[[ui-stack]]` — Next.js + Tailwind + shadcn korunur, FastAPI orchestrator korunur, no-mock kuralı kuvvetlenir
- `[[project-model]]` — Workspace concept korunur, IA değişir
- `[[jr-tool-protocol]]` — Speaker `<selffork-tool-call>` korunur
- `[[provider-usage-source]]` — derived audit log kuralı korunur
- `[[gemma4-always]]` — base model değişmez
- `[[5-critical-m5-repos]]` — Body M5 referansları korunur
- `[[provider-auth-ui-plan]]` — Connections ekranında realize edilir
- `[[m5-complete-2026-05-15]]` — M5 deliverable'lar korunur, Connections'a katlanır
- `[[no-mvp-full-quality-first-time]]` — bu ADR'nin ruhu

Bu ADR sonrası yeni memory girdileri (onay sonrası):
- `[[v2-pivot-2026-05-17]]` — bu ADR'nin compact özeti
- `[[full-autonomy-soft-confirm-4h]]` — destructive whitelist + 4 saat soft confirmation
- `[[server-self-host-linux]]` — deployment kararı

---

## 13. Sözlük (Glossary)

| Terim | Anlam |
|---|---|
| **P+Prompt Engineer** | Kod yazmayan, ama project yöneten + prompt mühendisi olan operatör. operator'ın kendisi. |
| **Live Run Theater** | Workspace'in 3-pane çekirdek bölgesi (CLI output / screenshot timeline / Jr düşünce balonu). |
| **Soft confirmation** | Destructive eylem öncesi Telegram'dan onay isteme; fail-safe NO (sessizlik = iptal). |
| **Destructive whitelist** | Soft confirmation tetikleyen eylem listesi (`packages/body/src/selffork_body/sandbox/data/destructive_actions.yaml`). |
| **Model endpoint** | LLM HTTP API'sinin URL'si; UI'dan konfigüre edilir; lokal veya remote olabilir. |
| **CLI router** | Aktif task için hangi CLI provider'a (claude/codex/gemini/minimax/glm) prompt yollanacağını seçen modül. |
| **Jr düşünce balonu** | Speaker'ın `<think>` çıktısının post-think compacted özeti (Live Run Theater sağ pane). |
| **Workspace** | Bir proje + kanban + sessions + notlar koleksiyonu; UI'da ana navigasyon node'u. |
| **Quota gauge** | Provider subscription pencere remaining time + reset window görselleştirmesi. |
| **Power user toggle** | Settings > Advanced altında, default gizli, opsiyonel olarak açılan detay surface'ler. |

---

**ADR-006 son — operator onayı bekleniyor.**
