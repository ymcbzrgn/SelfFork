# ADR-008 — SelfFork Otonomi Mimarisi: Self Jr Heartbeat (Yürütme + Yaratma)

## Status

- **Status:** Proposed — operatör onayı bekliyor (2026-05-18 taslak V1).
- **Type:** Architecture ADR — SelfFork'un otonomi katmanını ("hür irade")
  tanımlar. Yeni bir pillar değil; mevcut Orchestrator'a bir **dış döngü**
  ekler.
- **Builds on:**
  - [`ADR-006_v2_Pivot.md`](./ADR-006_v2_Pivot.md) — DOMINANT ADR.
    §2 madde 3 (slider iptal, "full otonom güven"), madde 4 (destructive
    soft-confirm), §4.5 (otonomi modeli), §5.1.1 (Operatör Günlük Akışı).
  - [`ADR-007_v3_Wiring_Completion.md`](./ADR-007_v3_Wiring_Completion.md) —
    S1–S8 wiring planı. ADR-008 buraya **yeni bir sprint** ekler (§10).
- **Related:** ADR-003 (CLI router → S6'da wire edilir; Heartbeat onu
  delege olarak çağırır), ADR-002 (Mind — karar logu, idea dosyaları,
  checkpoint state Mind'da yaşar).
- **Trigger:** 2026-05-18 vizyon-durum denetimi. `explorer-god` round-loop'u
  koda baktırarak doğruladı: round-loop **motoru var ve çalışıyor** ama
  yalnızca `selffork run <prd>` ile tetikleniyor; **otonom tetikleyici hiç
  yok** ve ADR-007 S1–S8'in hiçbiri onu kurmuyor. Operatör bu boşluğu
  gördü ve otonominin ("kendi hür iradesiyle") ARGE'lenmesini istedi.

---

## 0. Yönetici Özeti

SelfFork'un round-loop **motoru** çalışıyor (`Session._run_agent`,
`packages/orchestrator/.../lifecycle/session.py:248-444` — explorer-god
doğrulaması): Self Jr modeline sorar → gerçek bir CLI subprocess'i açar →
çıktıyı yakalar → geri besler → `[SELFFORK:DONE]`'a kadar döner. Ama bu
motor yalnızca operatörün elle verdiği bir komutla (`selffork run`,
`POST /api/sessions/run`) başlar. **"Uyumayan ikinci ben" vizyonunun kalbi
olan otonom çalışma — Self Jr'ın kendi iradesiyle iş seçip başlatması —
kodda yok ve ADR-007 planında da yok.**

ADR-008 bu boşluğu **Self Jr Heartbeat** ile kapatır: mevcut round-loop'un
(iç döngü, "bir task'ı yürüt") üstüne bir **dış döngü** ("hangi task'ı,
hangi projeyi, ne zaman — yoksa bekle"). Heartbeat'in iki modu vardır:

- **Yürütme modu (Executive):** operatörün kanban'ını otonom yürütür.
- **Yaratma modu (Creative):** Settings'ten açılan opsiyonel mod —
  Self Jr boş vaktinde kendi fikirlerini üretir, bir CLI ile tartışır ve
  kademeli otonomiyle hayata geçirir.

Otonomi, **deterministik bir güvenlik zarfının içinde** yaşar: kurallar
yasal eylem kümesini üretir, model o kümeden seçer. Her karar denetlenir,
operatör her an override eder, ADR-006 §4.5 destructive guardrail altta
durur. Hedef otonomi seviyesi **bilinçli olarak sınırlıdır** — sınırlı bir
eylem uzayı içinde iş seçimi, kendini-değiştirme DEĞİL.

---

## 1. Bağlam ve Tetikleyici

### 1.1 Doğrulanmış mevcut durum (explorer-god, 2026-05-18)

| Bileşen | Durum | Kanıt |
|---|---|---|
| Round-loop motoru (iç döngü) | ✅ Çalışıyor | `lifecycle/session.py:248-444` `Session._run_agent` |
| CLI agent execution | ✅ Gerçek subprocess | `cli_agent/claude_code.py`, `sandbox/subprocess_sandbox.py:140-171` |
| Loop tetikleyici | 🔴 Sadece elle | `Session(` yalnızca `cli.py:575` (`selffork run`) ve `POST /api/sessions/run` |
| Otonom tetikleyici | 🔴 Yok | Hiçbir scheduler kanban okuyup loop başlatmıyor; `resume watch` yalnızca rate-limit'li session'ları diriltir |
| Self Jr kanban'ı yönetir | 🟡 Kısmi | Loop *içinde* tool ile kart taşıyabilir (`tools/kanban.py`); kart *seçip başlatma* yok |
| Live theater | 🔴 Boş iskele | `dashboard/theater_router.py` — `/api/loop/active` hep `None` |

**Sonuç:** SelfFork'un round-loop'u bir **araç** — operatör başlatır.
"Uyumayan ikinci ben" için gereken **dış döngü** (otonom iş seçimi)
hiçbir yerde yok.

### 1.2 Operatör beyanı

2026-05-18 oturumunda operatör iki vizyon eklemesi verdi:

1. *"modelin kendi hür iradesiyle promptlar yazması CLI'lere, bir projeye
   devam etmesi, kanbanı yönetmesi"* — otonom yürütme.
2. *"Self Jr'a Settings'ten açtığımız bir şeyle kendi fikirlerini üretme
   şansı versek? Bir fikir dosyası workspace'i açar, boş vaktinde güçlü bir
   CLI açar, bir fikir tartışır, sonra o fikri hayata geçirir... ben de
   kendi fikirlerimi böyle buluyorum."* — otonom yaratma.

Bu, ADR-006 §3.2'de korunan ARGE §3 dört-katman zaman çizgisinin
(Mevcut → Uzak → Proaktif → Otonom) son iki katmanını somutlar: **Heartbeat
"Otonom" katmanını, yaratma modu "Proaktif" katmanını** hayata geçirir.

### 1.3 Karar süreci

Otonomi tasarımı 2026-05-18 oturumunda iteratif onaylandı (ADR-006'nın
yöntemi): operatör (a) "Yol A — ARGE şimdi, kod S2'den devam, Heartbeat
S3 sonrası" seçti; (b) yaratıcı otonomi için "B×C mix" (kademeli) seçti.
ADR-008 bu konuşmanın çıktısını formalize eder.

---

## 2. ARGE — Korpus ve Araştırma Bulguları

MANDATE 9 gereği, mimari kilitlemeden önce korpus ve dış kaynaklar
okundu (`explorer-god` lokal `examples_crucial/`, `selffork-researcher`
internet). Özet bulgular:

### 2.1 Korpus (examples_crucial/)

- **Hexis** — korpustaki **tek gerçek dış otonomi loop'u; birincil
  referansımız.** Mimari: ayrı bir **zamanlayıcı** ("ne zaman" der —
  `worker_service.py:50-161`, docstring: *"only decides WHEN to fire"*)
  + ayrı bir **yürütücü** (kararı modele sordurur). Trigger duvar-saati
  tabanlı + aktif-saat penceresi. Her iterasyonun başında **bütçe
  kontrolü** (`agent_loop.py:354-363`). Yarıda kalırsa
  `{step, progress, next_action}` **checkpoint** yazar, sonraki tick
  devam eder (`heartbeat_agentic.py:241-276`). "Yapacak iş yoksa söyle ve
  dinlen" promptu birinci sınıf (`heartbeat_agentic.md:36-41`).
  Her heartbeat episodik hafızaya denetim kaydı olarak yazılır.
- **Letta** — "heartbeat" = modelin emit ettiği bir devam-bayrağı
  (`request_heartbeat`); **Letta V1 (2025) bunu DEPRECATE etti** — devam/dur
  kararı mimarinin işi, modele bırakılmaz. v3 kuralı: "tool çağrısı varsa
  devam, sadece metin varsa dur" (`letta_agent_v3.py:1979-1981`).
  Sleep-time agent'lar yalnızca **hafıza bakımı** yapar — iş seçmez.
- **Second-Me** — otonomi YOK; istek-tetiklemeli persona chatbot.
  "second self"in bir otonomi loop'u olmadan sade sohbete çöktüğünü
  gösterir — tezi doğrular.
- **Skyvern / browser-use** — tek-task yürütücüler = SelfFork'un zaten
  sahip olduğu **iç döngü**. browser-use'un 3-fazlı `step()`'i
  (perceive/decide/act, `service.py:1052-1066`) en temiz iç-döngü şekli;
  son-adım tool daraltması (`service.py:1560`) alınacak bir kalıp.

### 2.2 Dış araştırma (internet)

- **MemGPT** (arXiv 2310.08560): "heartbeat" = task-içi devam mekanizması;
  kalıcı fikir **olay modeli** — olaylar (kullanıcı mesajı, sistem uyarısı,
  **zamanlı olaylar**) çıkarımı tetikler, iş yoksa temiz "yield".
- **Kontrol-loop paradigmaları:** reaktif vs deliberatif vs zamanlanmış.
  Konsensüs = **hibrit**: hızlı deterministik reaktif katman + yavaş
  deliberatif (model) katman. **Saf cron yetersiz** — cron zamana bakar,
  duruma değil; "hangi proje, hangi kart, şimdi" yargısını veremez.
- **Ambient agents** (LangChain): arka planda çalışıp insana yalnızca
  gerektiğinde dönen ajanlar; üç insan-etkileşim deseni: *bildir / sor /
  incele*. SelfFork'un "bekle"si dördüncü.
- **Otonom kod ajanları** (Devin, OpenHands, SWE-agent, Cursor):
  hepsi insandan **verilen** task'ı yapar. **Çok-projeli bir kanban'dan
  kendi iş seçen bir kod ajanı YOK.** SelfFork'un Heartbeat çekirdeği
  alanda gerçekten öncü — bu, korpus taranarak kanıtlanmış bir "emsali
  yok" (varsayım değil).
- **Güvenlik** (Microsoft "Defense in depth for autonomous AI agents",
  2026): en güçlü konsensüs — **eskalasyon kod'da deterministik tanımlanır,
  modele bırakılmaz.** Model bir eskalasyondan ikna edilebilir, kod kuralı
  edilemez. SelfFork'un ADR-006 §4.5 whitelist'i zaten böyle.
- arXiv 2502.02649: tam-otonom (Level-5, kendini-değiştiren) ajanlar
  geliştirilmemeli; **sınırlı + override edilebilir** ajanlar önerilir.
- **Trigger:** olay-tetiklemeli hızlı yol + periyodik **reconciliation
  poll** emniyet ağı. "Olaylar kaçacak — kaçabilir değil, kaçacak."

### 2.3 Alınanlar / Reddedilenler

| Karar | Kaynak | SelfFork'a |
|---|---|---|
| Zamanlayıcı/yürütücü ayrımı | Hexis | **AL** |
| Per-cycle bütçe + hard cap + checkpoint | Hexis | **AL** |
| "Bekle/yield" birinci sınıf | Hexis, MemGPT, LangChain | **AL** |
| Olay + reconciliation hibrit trigger | araştırma | **AL** |
| Hibrit kontrol-loop (kurallar filtreler / model seçer) | araştırma | **AL** |
| Eskalasyon deterministik (kod, model değil) | Microsoft 2026 | **AL** |
| `request_heartbeat` model-bayrağı | Letta (kendisi terk etti) | **REDDET** |
| Turn-counter tetikleme | Letta sleep-time | **REDDET** (konuşma temposuna bağlar) |
| Saf cron | araştırma | **REDDET** (duruma kör) |
| SQL-as-brain | Hexis | **REDDET** (kararlar Python'da, testlenebilir) |
| Yenilenen "enerji parası" tek-bütçe | Hexis | **REDDET** (ADR-006 whitelist yeterli) |
| Tek düz backlog | Hexis | **REDDET** (Project first-class — iki seviye seçim) |
| Level-5 tam otonomi | arXiv 2502.02649 | **REDDET** (sınırlı kalır) |

---

## 3. Çekirdek Mimari — İki Katmanlı Zihin

SelfFork'un otonomisi **iki döngü**dür:

```
┌──────────────────────────────────────────────────────────┐
│  DIŞ DÖNGÜ — Heartbeat            (YENİ — ADR-008)         │
│  "Hangi proje? Hangi task? Şimdi mi, bekle mi?"            │
│  perceive → decide → act → record   (her nabızda bir tur)  │
└───────────────────────────┬──────────────────────────────┘
                            │  task_başlat / session_devam
                            ▼
┌──────────────────────────────────────────────────────────┐
│  İÇ DÖNGÜ — Round-loop            (MEVCUT — session.py)    │
│  "Verilmiş bu task'ı bitir."                               │
│  Self Jr → CLI'ye prompt → kod → gör/test → ... → [DONE]   │
└──────────────────────────────────────────────────────────┘
```

- **İç döngü** zaten var (`Session._run_agent`), *verilmiş* bir task'ı
  yürütür. ADR-008 ona dokunmaz.
- **Dış döngü** yenidir. *Hür irade burada yaşar:* işi seçmek, projeyi
  seçmek, anı seçmek — ve dinlenmeyi seçmek.

Her iki döngünün "Self Jr"ı aynı reflekstir, iki ölçekte: iç döngüde
Self Jr bir teknik lider gibi *bir CLI'yi yönlendirir*; dış döngüde bir
kurucu/PM gibi *gündemi belirler*. (Not: explorer-god, mevcut kodda iç
döngünün model istemcisinin `MlxServerRuntime`, Talk'ın istemcisinin ise
ayrı `SpeakerClient` olduğunu buldu — ADR-008 implementasyonu bu ikisinin
Heartbeat altında tek "Self Jr" arayüzünde birleştirilmesini gerektirir;
detay S-Auto sprint'inde.)

---

## 4. Heartbeat Anatomisi

### 4.1 Bir "nabız" (tick)

```
        ┌─────────────┐
        │  TETİK      │  olay (kanban değişti / [SELFFORK:DONE] /
        │             │  operatör mesajı) VEYA reconciliation timer
        └──────┬──────┘
               ▼
   1. ALGILA   →  Dünya fotoğrafı: tüm kanban'lar, aktif session'lar,
                  CLI kotaları, bekleyen onaylar, Telegram inbox,
                  son hatalar, creative-mode idle durumu.
               ▼
   2. KARAR    →  (a) Deterministik kurallar YASAL eylem kümesini üretir.
                  (b) Self Jr modeli o kümeden GEREKÇEYLE birini seçer.
               ▼
   3. EYLE     →  Seçilen tek eylemi uygula.
               ▼
   4. KAYDET   →  Karar + gerekçe + görülen durum → audit + Mind.
                  Yarıda kesilirse checkpoint {step, progress, next}.
               ▼
        [ bir sonraki nabza kadar sıfır maliyetle bekle ]
```

### 4.2 Trigger — hibrit (saf cron DEĞİL)

- **Olay-tetiklemeli hızlı yol:** kanban kartı eklendi/taşındı,
  `[SELFFORK:DONE]` session bitti, operatör/Telegram mesajı geldi → anında
  bir nabız.
- **Reconciliation timer (emniyet ağı):** her N dakikada bir (öneri 10–15
  dk) tam kanban durumu yeniden okunur — kaçan olayları yakalar.
  *"Olaylar kaçar."*
- **Aktif-saat geçidi:** Settings'te tanımlı pencere dışında nabız atmaz
  (operatörün ritmine saygı; ucuz deterministik ön-filtre).
- **Zamanlayıcı/yürütücü ayrımı (Hexis):** ince bir zamanlayıcı yalnızca
  "nabız zamanı geldi mi" der; ayrı yürütücü nabzı çalıştırır.

### 4.3 Karar — hibrit kontrol-loop

İki katman, kesin ayrık:

- **Reaktif katman (deterministik kod):** YASAL eylem kümesinin **tek
  kaynağı**. Örnek kurallar: kota eşiğin altındaysa `task_başlat` kümede
  yer almaz; operatör `/pause` dediyse tek seçenek `bekle`; eşzamanlılık
  sınırı doluysa yeni `task_başlat` yok; creative toggle kapalıysa
  `fikirleş` yok.
- **Deliberatif katman (Self Jr modeli):** yalnızca **yasal** seçenekler
  arasından seçer + gerekçe üretir. Modeli `Orient → Check → Decide`
  promptu yönlendirir (Hexis kalıbı). **Model zarfı asla aşamaz.**

Bu, "hür irade ≠ kontrolsüzlük"ün mimari karşılığıdır: kurallar
**kısıtlar**, model **seçer**.

### 4.4 Eylem sözlüğü (kapalı, denetlenebilir)

| Eylem | Anlam |
|---|---|
| `task_başlat(project, card)` | İç döngüyü bir kanban kartı için başlat |
| `session_devam(session_id)` | Duraklamış/checkpoint'li bir loop'u sürdür |
| `cli_seç(workspace, task)` | S6 CLI router'a delege (hangi CLI) |
| `kanban_task_öner(project, card)` | Self Jr bir kart önerir (inisiyatif) |
| `operatöre_sor(mesaj)` | Telegram'dan bildirim/soru |
| `fikirleş()` | Yaratma modu (§5.2) — yalnızca idle + toggle açıkken yasal |
| `uzvunu_kullan(intent)` | Body pillar'ı kullan: yaz/tıkla/screenshot (S-Vision §4) |
| `uzvunu_incele(intent)` | Body pillar'ını oku-only vision-parse (S-Vision §4) |
| `bekle(reason)` | Bilinçli olarak bu nabızda hiçbir şey yapma |
| `kendini_durdur()` | Operatör `/pause` veya kritik hata sonrası |

`bekle` **birinci sınıf bir karardır** — kota bittiyse, her şey blokeyse,
doğru davranış hiçbir şey yapmamaktır. Boş nabız sıfıra yakın maliyetlidir;
busy-loop yoktur.

> **S-Vision güncelleme (ADR-010 §4):** sözlük **8'den 10'a** çıktı —
> `uzvunu_kullan` + `uzvunu_incele` Body pillar'a granular hook verir
> (write/click/screenshot vs. read-only vision parse). Heartbeat filter
> Rule 6 (`body_daemon_alive` gate, **fail-CLOSED**) bu iki eylemi
> yalnızca Body daemon ayaktayken yasal kılar; `ActionExecutor`'a
> injectable `BodyUseDriver` / `BodyReviewDriver` callable'ları
> ``None=skipped`` pattern'iyle bağlanır (mevcut `TaskStarter` /
> `KanbanCardCreator` / `CliSelector` konvansiyonu). S-ToolFleet'in fat
> per-platform tool surface'ı (~250-380 araç) bu seam'in üstüne biner.

---

## 5. İki Mod — Yürütme ve Yaratma

Heartbeat **tek sistemdir**; "mod", eylem sözlüğünün hangi alt kümesinin
yasal olduğuyla belirlenir.

### 5.1 Yürütme modu (Executive) — varsayılan

Heartbeat operatörün kanban'larını otonom yürütür. **İki seviyeli seçim:**
önce hangi proje (kurucu gibi dikkat bölüştürme), sonra o projede hangi
kart. (Hexis tek düz backlog kullanır; SelfFork'ta Project first-class
olduğu için seçim iki seviyelidir.)

Akış: nabız → backlog'da yapılabilir kart var + kota uygun → `task_başlat`
→ iç döngü çalışır → `[SELFFORK:DONE]` → iç döngü kartı `done`'a taşır →
sonraki nabız sıradakini seçer.

### 5.2 Yaratma modu (Creative) — opsiyonel, Settings toggle

**Settings'te bir anahtarla açılır; varsayılan KAPALI.** Açıkken, Heartbeat
bir nabızda *yürütülecek executive iş yoksa* + *kota sağlıklıysa*,
`bekle` yerine `fikirleş`i seçebilir.

Bu, operatörün kendi yaratım ritüelini Self Jr'a öğretir: dosya aç →
güçlü bir CLI aç → tartış → fikri üret → kodlat.

- **Fikir workspace'i** — özel bir "Lab" workspace'i (mevcut Project/kanban
  makinesini yeniden kullanır). Kartlar = fikirler; kolonlar olgunluk:
  *kıvılcım → tartışıldı → olgun → projeye terfi*.
- **`fikirleş`** — mevcut round-loop'u "fikri tartış" hedefiyle çalıştırır
  (PRD uygulamak değil). Self Jr güçlü bir CLI (claude-code) ile beyin
  fırtınası yapar; çıktı fikir dosyasına yazılır.
- **Terfi** — olgunlaşan fikir bir kanban task'ına / yeni projeye dönüşür;
  executive Heartbeat onu kodlar. **Yaratma modu yürütme modunu besler.**

### 5.3 Kademeli yaratıcı otonomi (operatör seçimi: B×C mix)

Fikir *üretmek* bedava ve güvenli (yalnızca doküman çıkar). Düşünülmesi
gereken tek şey son adım — fikri **kodlamak**. Operatör seçimi:
**kademeli** — Self Jr fikri gerçekten hayata geçirir, ama fikrin boyutuna
göre farklı bir fren verir.

**İlke — sessizlik = DEVAM.** (ADR-006 §4.5 destructive'de sessizlik =
İPTAL'di. Fark: yaratıcı iş geri alınabilir — branch silinir — tehlikeli
değil, yalnızca kota/zaman harcar. O yüzden fren bir *kapı* değil, bir
*el freni*.)

| Fikir boyutu | Self Jr ne yapar |
|---|---|
| **Küçük** — mevcut projeye düşük-riskli iyileştirme | Yapar; sabah raporunda görünür. Sessiz. |
| **Orta** — mevcut projeye belirgin yeni özellik | Telegram'dan bildirir + yapmaya başlar. Anında veto edilebilir. |
| **Büyük** — yeni proje / büyük kota taahhüdü | Fikri tartışır, yazar, Telegram'dan sunar + **veto penceresi** açar (öneri 4h). "Dur" → iptal; sessizlik → başlar. |

Fikir boyutunu **deterministik kod sınıflandırır, model değil**
(araştırma: eskalasyon eşiği kodda).

### 5.4 İki ortogonal kapı

Yaratıcı otonominin güvenliği iki ayrı kapının üst üste binmesindedir:

| Kapı | Soru | Mekanizma | Fail-safe |
|---|---|---|---|
| **Yaratıcı-Kapsam Kapısı** (yeni — ADR-008) | "Bu fikir gerçek işe dönüşsün mü?" | bildir + veto penceresi | **GO** (sessizlik = devam) |
| **Destructive-Eylem Kapısı** (mevcut — ADR-006 §4.5 / S3) | "Bu komut tehlikeli mi?" | soft-confirm (Telegram) | **NO** (sessizlik = iptal) |

Self Jr büyük bir fikri otonom kodlarken bile, içeride `git push --prod`
veya `rm -rf` denerse Destructive-Eylem Kapısı yine yakalar. İki kapı dik
açıyla çalışır — biri **kapsamı**, biri **tehlikeyi** tutar.

Tüm yaratma modu Settings'te bir **kadranın** altındadır: operatör tümünü
"sadece fikir"e indirebilir veya sonuna açabilir. Kademe varsayılanı
operatör onayında §11'de netleşir.

### 5.5 Otonomi Settings Paneli — Operatör Kontrolü

SelfFork açık kaynaktır; her operatörün risk iştahı farklıdır. Bu yüzden
otonominin **tüm davranışı Settings UI'dan ayarlanabilir** — hiçbir kademe
kodda sabit değildir. İstemeyen operatör kapatır; "her iş bana sorulsun"
diyen denetimli moda alır; cesur operatör sonuna açar.

**ADR-006 ilişkisi (farkındalık notu):** ADR-006 §2 madde 3 belirsiz
0-10 özerklik slider'ını iptal etti. Bu panel o slider **değil** —
belirsiz bir kadran değil, **anlamlı discrete preset'ler + power-user
knob'ları.** ADR-006 §4.5 zaten soft-confirm süresini ve whitelist'i
operatöre ayarlatıyordu; bu panel onu bütünler, çelişmez.

**Dört preset:**

| Preset | Davranış |
|---|---|
| **Kapalı** | Heartbeat çalışmaz; SelfFork tamamen elle (`selffork run`). |
| **Denetimli** | Heartbeat karar verir ama her iş-başlatma eylemi önce Telegram onayı ister (sessizlik = iptal). "Her şey bana sorulsun" diyen için. |
| **Dengeli** (öneri: varsayılan) | Yürütme otonom; yalnızca destructive eylemler onay ister (ADR-006 §4.5). Yaratma kapalı. |
| **Tam** | Yürütme + Yaratma açık; yaratıcı kadran operatörce ayarlı. |

Preset, alttaki knob'ların ön-ayarıdır; power-user her knob'u tek tek de
ayarlar:

- Yaratma modu: Kapalı / Sadece-fikir / Kademeli / Tam (§5.3 kadranı)
- Yaratıcı tier eşikleri + veto penceresi süresi
- Destructive whitelist: kategori başına aç/kapa + onay penceresi (ADR-006 §4.5)
- Heartbeat aralığı, aktif-saat penceresi, eşzamanlılık sınırı
- Sabah raporu: açık/kapalı + saat

**"Denetimli" mimaride bedavadır:** deterministik kurallar katmanına tek
bir kural eklemekten ibarettir — her `act` öncesi bir onay adımı. Model
yine seçer; "Denetimli"de her karar bir öneriye dönüşüp Telegram'dan
onaylanır. Mimari (kurallar → model seçer → eyle) bunu zaten destekler.

Bu panel ADR-007 **S4 (Settings Persistence)** kapsamında wire edilir;
backing endpoint'lerini S-Auto sprint'i tanımlar.

---

## 6. Güvenlik Modeli (Defense-in-Depth)

Otonomi, üst üste binen savunma katmanlarıyla sınırlandırılır:

1. **Deterministik yasal-eylem filtresi** — model yalnızca kurallar
   katmanının ürettiği kümeden seçer; zarfı aşamaz (§4.3).
2. **Eskalasyon kod'da, modelde değil** — bir eylemin destructive olup
   olmadığına, bir confirm'in atlanıp atlanmayacağına model **asla** karar
   vermez. Bunlar ADR-006 §4.5 whitelist kuralları (kategoriler kodda).
3. **Kapalı eylem sözlüğü** — Heartbeat keyfi şey yapamaz (§4.4).
4. **Her karar denetlenir** — görülen durum + yasal küme + seçilen eylem +
   gerekçe Mind'a/audit'e yazılır. İdempotent: yapısal kimlikle anahtarlanır
   `(project, card_id, heartbeat_tick)` — model çıktısıyla değil.
5. **Eşzamanlılık sınırı** — aynı anda en fazla N aktif iç döngü
   (öneri: başlangıçta 1).
6. **Operatör override her zaman kazanır** — `/pause` Heartbeat'i dondurur;
   Talk/Telegram inject sonraki kararı ezer.
7. **Kota geçidi** — Heartbeat karşılayamayacağı işi başlatmaz.
8. **Otonomi tavanı sınırlı** — Heartbeat sınırlı bir eylem uzayında iş
   *seçer*; kendi kodunu/zarfını/güvenlik kurallarını değiştiremez
   (Level ~4, Level-5 değil — arXiv 2502.02649).
9. **Sabah raporu** — operatör girişinde "sen yokken ne yaptım/karar verdim/
   neye takıldım" özeti. Otonomiye güven bu şeffaflıktan gelir.

---

## 7. Karar Bloğu (The Locks)

Operatör onayıyla kilitlenecek maddeler:

| # | Karar |
|---|---|
| 1 | Otonomi = **iki katmanlı zihin**: mevcut round-loop (iç döngü) + yeni **Heartbeat** (dış döngü). İç döngüye dokunulmaz. |
| 2 | Heartbeat = **perceive → decide → act → record** nabzı; trigger **olay + reconciliation-timer hibrit** (saf cron DEĞİL). |
| 3 | Karar **hibrit kontrol-loop**: deterministik kurallar yasal eylem kümesini üretir, Self Jr modeli o kümeden seçer. Model zarfı aşamaz. |
| 4 | **Eskalasyon ve destructive sınıflandırması kod'da deterministiktir**, modele bırakılmaz (ADR-006 §4.5 miras alınır, yeniden açılmaz). |
| 5 | `bekle` **birinci sınıf bir karardır**; boş nabız sıfıra yakın maliyetlidir. |
| 6 | İki mod: **Yürütme** (varsayılan) + **Yaratma** (Settings toggle, varsayılan KAPALI). "Mod" = yasal eylem alt kümesi. |
| 7 | Yaratıcı otonomi **kademelidir** (B×C mix): küçük=sessiz-yap, orta=bildir+yap, büyük=veto-penceresi. **Sessizlik = devam.** Hepsi Settings kadranı altında. |
| 8 | **İki ortogonal kapı**: Yaratıcı-Kapsam Kapısı (bildir/veto, fail-safe GO) + Destructive-Eylem Kapısı (S3 soft-confirm, fail-safe NO). |
| 9 | Otonomi tavanı **sınırlı** — sınırlı eylem uzayında iş seçimi; kendini-değiştirme yok. |
| 10 | Heartbeat **M7'den ÖNCE** kurulur; heartbeat kararları + operatör düzeltmeleri + ideation oturumları M7 dataset'ini besler. |
| 11 | Heartbeat **ADR-007'ye yeni bir sprint** olarak girer (`S-Auto`), **S3'ten sonra** (§10). |
| 12 | Otonominin **tüm davranışı Settings UI'dan ayarlanabilir** — dört preset (Kapalı / Denetimli / Dengeli / Tam) + power-user knob'ları; hiçbir kademe kodda sabit değil. ADR-006'nın iptal ettiği belirsiz 0-10 slider DEĞİL — anlamlı discrete kontroller. |

---

## 8. Pillar Etkisi (MANDATE 7)

- **Reflex (Pillar 1):** Heartbeat'in her kararı + operatörün o karara
  düzeltmesi ("hayır, önce şu bug") = M7 için **prioritizasyon refleksi**
  eğitim verisi. Ayrıca operatörün **ideation oturumları** (yaratma modu)
  dataset'e girer — Self Jr yalnızca task yürütmeyi değil, *fikir üretmeyi*
  de operatör gibi öğrenir. Heartbeat M7'nin organıdır (§9).
- **Body (Pillar 2):** Destructive-Eylem Kapısı = ADR-006 §4.5 warden;
  Heartbeat'in altında değişmeden durur. Yaratma modunun "ürettiğini ayağa
  kaldır + vision'la test et" adımı Body vision driver'ını kullanır.
- **Mind (Pillar 3):** Heartbeat karar logu, idea dosyaları, checkpoint
  state, CLI-affinity skoru (S6 RAG) — hepsi Mind'da yaşar. **Boş nabız
  (idle) bir varlıktır:** o pencerede Mind arka-plan context compaction
  yapabilir (Letta sleep-time agent kalıbı) — idle zaman israf değil.
- **Orchestrator:** Heartbeat daemon'u Orchestrator'a yeni bir bileşendir;
  mevcut `resume watch` daemon'u yapısal referanstır (zaten çalışan bir
  always-on loop).

---

## 9. M7 İlişkisi

Heartbeat M7 (Reflex fine-tune) **öncesinde** kurulur. Gerekçe:

- Heartbeat, M7'nin eğittiği refleksin **içinden aktığı organdır.** Önce
  stok Gemma ile makul kararlar verir (deterministik zarf güvenliği sağlar);
  M7 gelince kararlar *operatör kalitesinde* olur.
- Bu, operatörün `[[infra-before-finetune]]` kuralıyla birebir örtüşür:
  "önce altyapı, fine-tune en sonda; model sistem davranışını fine-tune
  sırasında doğal öğrenir."
- Heartbeat çalışır çalışmaz **kendi M7 datasetini üretmeye başlar:**
  her karar + operatör düzeltmesi = refleks örneği. Yaratma modu açıksa
  ideation oturumları da eklenir.

Pre-M7'de yaratma modu kademe varsayılanı düşük tutulmalıdır (stok modelin
fikirleri jenerik olur — §12).

---

## 10. Sprint Konumu

ADR-007'nin S1–S8 dizisine yeni bir sprint eklenir: **`S-Auto`**, **S3'ten
sonra.**

```
S1 ✓  →  S2  →  S3  →  [ S-Auto: Heartbeat ]  →  S4–S8  →  M7
```

Gerekçe:
- **S2 = Heartbeat'in gözü** — Live Run Theater + Dashboard Live Loop;
  onsuz otonom loop görünmez çalışır.
- **S3 = Heartbeat'in tasması** — destructive warden + Telegram (iki yönlü);
  onsuz otonom ajan ne güvenli ne ulaşılabilir.
- S4/S5/S7 (settings/connections/workspace polish) otonomi için kritik
  değildir — beklemesine gerek yok.

`S-Auto`'nun tek sprint mi iki sprint mi olacağı (executive Heartbeat +
yaratma modu) §11'de açık sorudur. Yürütme modu yaratma modunun zeminidir
— executive Heartbeat her hâlükârda önce gelir.

ADR-007'nin §4 sprint planı ve §6 milestone konumu, bu ADR onaylandığında
`S-Auto`'yu içerecek şekilde güncellenir (ayrı commit).

---

## 11. Açık Sorular

ADR-006 yöntemi — her sorunun bir "öneri"si var; operatör onayda kabul
eder veya değiştirir:

1. **Reconciliation timer aralığı.** Öneri: 10–15 dk; Settings'te ayar.
2. **Eşzamanlılık sınırı (max aktif iç döngü).** Öneri: başlangıçta 1
   (operatör "film izler gibi" tek loop'u izler); Settings'te artırılır.
3. **Veto penceresi süresi (büyük fikir).** Öneri: 4h (ADR-006 §4.5
   destructive penceresiyle aynı, tutarlılık).
4. **Yaratıcı otonomi kadranı varsayılanı.** Öneri: pre-M7'de "orta"
   tavanlı başla (küçük+orta otomatik, büyük veto-pencereli); M7 sonrası
   operatör yükseltir.
5. **`S-Auto` tek sprint mi, iki mi?** Öneri: S-Auto-1 (executive Heartbeat)
   + S-Auto-2 (yaratma modu) — iki ince sprint, her biri kendi smoke
   gate'iyle.
6. **İsimlendirme.** "Heartbeat", "Yürütme/Yaratma modu", "Lab workspace"
   çalışma adlarıdır — operatör onayında sabitlenir.
7. **Aktif-saat penceresi varsayılanı.** Öneri: 7/24 açık (operatör
   isterse Settings'ten daraltır) — "uyumayan ikinci ben" ruhu.
8. **Varsayılan otonomi preset'i** (yeni kurulum). Öneri: **Dengeli** —
   Heartbeat yürütme açık, destructive-onaylı, yaratma kapalı. Operatör
   "Tam"a çeker; tedirgin açık-kaynak kullanıcısı "Denetimli"/"Kapalı"ya.

---

## 12. Risk ve Trade-off

- **Pre-M7 jenerik fikirler.** Stok Gemma'nın yaratıcı fikirleri sığ olur.
  *Mitigasyon:* yaratma modu varsayılan KAPALI; açıksa kadran düşük; M7
  sonrası yükseltilir.
- **Kota yanması.** Otonom loop + yaratma modu CLI kotası harcar.
  *Mitigasyon:* kota geçidi, eşzamanlılık sınırı, yaratma modu yalnızca
  idle + sağlıklı-kota'da yasal, Settings günlük cap'i.
- **Olay kaçması.** Olay-tetiklemeli yol bir kanban değişimini kaçırabilir.
  *Mitigasyon:* reconciliation timer tam durumu yeniden okur.
- **Otonom ajan korkusu / güven.** Operatör "ne yaptı bilmiyorum" hissi.
  *Mitigasyon:* her karar gerekçeli audit; sabah raporu; operatör override;
  sınırlı eylem uzayı; iki kapı.
- **İki model istemcisinin birleştirilmesi.** Mevcut kodda iç döngü
  (`MlxServerRuntime`) ve Talk (`SpeakerClient`) ayrı; Heartbeat tek bir
  "Self Jr" arayüzü ister. *Mitigasyon:* S-Auto sprint'inin ilk işi bu
  birleştirme; explorer-god ile entegrasyon yüzeyi netleştirilir.
  *Çözüm (2026-05-23):* S-Auto Faz C; Heartbeat connect-only
  `SpeakerClient` reuse + `Speaker` Protocol ile ortak yüzey.
- **Sprint kayması.** S-Auto, S2+S3'e bağımlı; onlar fail ederse S-Auto
  başlamaz (ADR-007 §9 disiplini).
- **M7 sonrası safety drift (Misevolution).** arXiv 2509.26354 (Eylül
  2025, USENIX Sec '25): LLM agent'ın bellek/araç/iş akışı evrimi
  sırasında safety alignment'ı düşebilir. Heartbeat audit.jsonl M7
  fine-tune dataset'inin SSOT'su olduğu için, *fine-tune sonrası
  periyodik safety re-alignment check* gerekir. *Mitigasyon (deferred):*
  M7 öncesi yeni ADR maddesi — kalibrasyon kadansı (ör. her 1000 tick'te
  bir held-out behavior eval). Faz E AIR detector bu evrime karşı
  birinci-katman koruma; periyodik re-alignment ikinci-katman.

---

## 13. Onay

Bu ADR **2026-05-23'te operatör onaylı + S-Auto sprint tamamlandı.**
§7 12 Karar Bloğu kilitli; §11 8 Açık Soru operatör cevaplarıyla
çözüldü:

- #1 Reconciliation timer: 10-15 dk (default 600s, Settings'te ayar).
- #2 Eşzamanlılık sınırı: 1 (Settings'te artırılır).
- #3 Veto penceresi: 4h (ADR-006 §4.5 ile tutarlı).
- #4 Yaratıcı kadran pre-M7: `spark_only` (sadece-fikir; Settings'ten
  4 kademe ayarlanabilir — operatör direktifi).
- #5 Sprint yapısı: **tek geniş S-Auto** (executive + creative + settings
  birlikte).
- #6 İsim: "Heartbeat" korundu (enterprise tutarlılık; ADR-008 §12'ye
  Letta-deprecate notu eklendi).
- #7 Aktif-saat: 7/24 default.
- #8 Default preset: `dengeli` (executive açık, destructive-confirmed,
  yaratma kapalı).

Implementation 8 faz tek sprint'te tamamlandı (Faz A scheduler → Faz H
smoke). Tüm S-Auto memory entry'si: `[[s-auto-complete-2026-05-23]]`.
Smoke gate: `docs/plans/M6_Smoke_Checklist.md` § S-Auto.

İlgili: `ADR-006_v2_Pivot.md` (§2, §4.5, §5.1.1), `ADR-007_v3_Wiring_Completion.md`,
`[[full-autonomy-soft-confirm-4h]]`, `[[infra-before-finetune]]`,
`[[yamac-jr-is-user-simulator]]`, `[[s-auto-complete-2026-05-23]]`,
`[[s-memory-scope-2026-05-23]]` (sıradaki sprint).
