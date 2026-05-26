# 2026-05-26 — S-Vision Close + BUG-1 Live-Quota + Fine-tune CLI Migration

Bu klasör S-Vision sprint'inin **fully closed** halinin canlı uçtan-uca demo'su.
Geriye bekleyen sadece operator-onayı + commit. Mock veya sahte veri yok —
her satır gerçek `~/.selffork/` durumundan ve canlı CodexBar HTTP probe'undan.

---

## Bu session'da ne yapıldı (2026-05-26 ~15:30–16:15 GMT+3)

### 1. BUG-1 fix — Auto-runner sidecar + endpoint synthesis (RECOMMENDED yol)

Operator handoff'un karar tablosunda `Quota fix → Auto-runner sidecar` seçildi.
İki parça halinde teslim edildi:

- **Snapper auto-runner sidecar** (yeni — `snappers/runner.py:build_default_snapper_runner`).
  Backend FastAPI lifespan'a bağlı; CodexBar sidecar pattern'iyle aynı disiplinde
  start/stop. Her tick `claude-code` / `codex` / `gemini-cli` / `opencode` /
  `minimax-cli` / `zai` snapshot'larını `~/.selffork/cli-state/*.json`'a atomic
  yazıyor. Env knob'ları:
  - `SELFFORK_SNAPPER_RUNNER_ENABLED=false` → kapat (test ve CI için)
  - `SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS` (default `5`, min `0.25`)
  - `SELFFORK_CLI_STATE_DIR` → state dizini override (test'ler için zorunlu)
- **Endpoint synthesis** (`dashboard/server.py::_synthesize_proactive_rows`).
  `/api/usage/providers` artık audit-derived row'ları + proactive snapper /
  CodexBar fallback'inden synthesize edilmiş row'ları MERGE ediyor. Audit
  truth still wins on overlap; CLI'ler audit'te yoksa ama snapper/CodexBar
  window data'sı varsa, dashboard gauge'i dolduran row üretiliyor.

### 2. Fine-tune UI removal — operator direktifi "kaldır → `selffork train` CLI"

Operator: "fine tune işini ben UI'dan yapmamayı tercih ediyorum ya, kafa
karıştırıcı 1 kere yapılan bişi". AskUserQuestion ile resmi karar:
**"Kaldır → `selffork train` CLI"**.

Yapılanlar:
- `apps/web/app/settings/page.tsx` — Fine-tune section + form + adapter
  status component **tamamen silindi** (~270 satır + 5 import temizliği).
- `apps/web/lib/api.ts` — Reflex training surface block (`ReflexHyperParams`,
  `StartTrainingPayload`, `TrainingJobResponse`, `ReflexAdapterInfo` + 4
  function) silindi (~85 satır).
- `packages/orchestrator/src/selffork_orchestrator/dashboard/reflex_router.py`
  **silindi** (459 satır), `dashboard/server.py`'deki include kaldırıldı.
- Yerine geldi:
  - `packages/orchestrator/src/selffork_orchestrator/reflex_manifest.py` —
    canonical manifest path + reader (`AdapterManifest` frozen dataclass).
    Audit-god MAJOR #1 fix korundu (`_int_or_none` bool reject).
  - `packages/orchestrator/src/selffork_orchestrator/cli.py::train` — yeni
    `@app.command()`. Args: `--info`, `--method`, `--dataset`, `--lora-rank`,
    `--lora-alpha`, `--learning-rate`/`--lr`, `--epochs`, `--target-modules`,
    `--adapter-manifest`. M7 stub — gerçek QLoRA worker M7'de gelecek.

### 3. Test isolation — yeni `dashboard/conftest.py`

Dashboard test'leri artık `tmp_path / "_isolated-cli-state"`'e
yönlendiriliyor (`SELFFORK_CLI_STATE_DIR` env via autouse fixture). CodexBar
sidecar + snapper auto-runner test ortamında otomatik kapanıyor. Test'ler
operator'ın gerçek `~/.selffork/` ağacına dokunmuyor.

---

## Baseline

```
$ git log --oneline -1
b6357df feat: overhaul dashboard UI ...

$ git status --short | wc -l
47   # 33 (handoff base) + 14 yeni dosya (bu session)

$ .venv/bin/python -m pytest ... 2>&1 | tail -3
2456 passed in 43.12s   # was 2438 → +18 net

$ .venv/bin/python -m ruff check packages/ apps/web
All checks passed!

$ .venv/bin/python -m mypy packages/{orchestrator,body,mind,shared}/src
Success: no issues found in 260 source files

$ cd apps/web && npx tsc --noEmit; echo $?
0
```

**Yeni test sayısı (bu session): +18**
- `test_runner.py`: +6 (snapper sidecar factory + env knob coverage)
- `test_projects_api.py::TestUsageSynthesisFromProactive`: +3 (synthesis +
  audit-truth-wins + windowless-skip)
- `test_reflex_manifest.py`: +9 (yeni dosya, manifest reader honest empty)
- `test_cli_train.py`: +10 (yeni dosya, `selffork train` subcommand)
- `test_reflex_router.py`: **−10** (router silindi)

Toplam: +18 net.

---

## Screenshot inventory

| # | Dosya | Ne gösteriyor |
|---|-------|----------------|
| 01 | `01-home-dashboard-LIVE-QUOTA-v2.png` | **Dashboard** — CLI Quota kartı: **codex 100%/4h 59m left** + **gemini 100%/23h 59m left** canlı render (CodexBar verisi). claude/minimax/glm `—` (honest empty — local signal yok). |
| 01 | `01-home-dashboard-LIVE-QUOTA.png` | Aynı state, biraz daha önce — 2 row stable. |
| 02 | `02-connections-LIVE-QUOTA.png` | **Connections** — claude/codex/gemini 3 row gerçek window verisi (CodexBar source-tag'li): "Resets in 2d 18h" / "4h 59m" / "23h 59m". opencode/minimax/glm "No recent activity" CLI-native sign-in komutu hint. |
| 03 | `03-settings-NO-FINETUNE.png` | **Settings** — 4 panel: Model Endpoint, Telegram bridge, CodexBar (collapsed preview), Autonomy/Heartbeat. **Fine-tune section yok.** Bottom hint: "Vision adapter config lives on its own page → /cockpit/settings/vision". |
| 04 | `04-talk.png` | **Talk** — operator ↔ Self Jr chat surface. |
| 05 | `05-workspace-detail.png` | **Workspace detail** — M4 Smoke Test workspace; Kanban + Theater + Notes + header. |
| 06 | `06-cockpit-vision.png` | **Cockpit / Settings / Vision** — Vision adapter config (M5+ Body pillar). |
| 07 | `07-cockpit-home.png` | **Cockpit** — operator power-mode surface. |
| 08 | `08-projects.png` | **/projects** — proje listesi. |
| 09 | `09-run.png` | **/run** — session orchestration surface. |
| 10 | `10-session.png` | **/session** — single session detail view. |

### Önceki session'dan kalan (S-Vision close öncesi state)

| # | Dosya | Ne için tutuldu |
|---|-------|------------------|
| — | `01-home-dashboard.png` | Pre-CodexBar state — quota empty |
| — | `01-home-dashboard-after-codexbar.png` | CodexBar kurulu ama endpoint hâlâ audit-derived → empty |
| — | `02-talk.png` | (eski tour) |
| — | `03-connections.png` | Pre-fix Connections — quota numbers empty |
| — | `04-settings.png` | Pre-removal — Fine-tune section hâlâ orada |

Önce-sonra karşılaştırması için bunlar muhafaza edildi.

---

## Live evidence — uydurma yok

`/api/usage/providers` canlı response (16:08 GMT+3):

```json
[
  {
    "cli_agent": "gemini-cli",
    "window_label": "1d",
    "window_seconds": 86400,
    "calls_in_window": 0,
    "next_reset_at": "2026-05-27T13:08:30Z",
    "proactive_source": "codexbar"
  },
  {
    "cli_agent": "codex",
    "window_label": "5h",
    "window_seconds": 18000,
    "calls_in_window": 0,
    "next_reset_at": "2026-05-26T18:08:30Z",
    "proactive_source": "codexbar"
  }
]
```

CodexBar'ın doğrudan döndürdüğü (port 8766):

```json
{
  "primary": {"windowMinutes": 300, "usedPercent": 1, "resetsAt": "2026-05-26T18:08:30Z"},
  "secondary": {"windowMinutes": 10080, "usedPercent": 0, "resetsAt": "2026-06-02T13:08:30Z"},
  "identity": {"loginMethod": "plus", "providerID": "codex", "accountEmail": "gptlogin7@gmail.com"}
}
```

`resetsAt` birebir eşleşiyor. `cli-state/opencode.json` mtime 16:08 — snapper
sidecar canlı atomic yazıyor.

### `selffork train` CLI canlı

```
$ .venv/bin/selffork train --info
No adapter manifest at /Users/yamacbezirgan/.selffork/reflex/adapters/current/manifest.json.
The M7 training worker writes one after the first successful fine-tune; pre-M7
this is expected.

$ .venv/bin/selffork train --method LoRA --epochs 2
No adapter manifest at /Users/.../manifest.json. ... pre-M7 this is expected.

--- training plan (M7 worker stub) ---
method:         LoRA
dataset:        auto
lora_rank:      32
lora_alpha:     16
learning_rate:  2e-4
epochs:         2
target_modules: attention

Real QLoRA worker lands in M7 (Pillar 1 Reflex). Job not started; no GPU
held. Track progress at ~/.selffork/reflex/adapters/ once M7 ships.
```

Honest empty + dry plan stub. Hiçbir manifest dosyası yazılmadı, GPU
tutulmadı — pre-M7 doğru davranış.

---

## Bilinen gap'ler (S-Vision close ÖNCESİNDEN, hâlâ S-Bridge sprint kapsamında)

- **BUG-2** — `infra/deploy/scripts/install-codexbar.sh` symlink extract bug
  (manifest.toml `archive_member="codexbar"` symlink'i çekiyor target'sız).
  Workaround: manuel `tar -xzf ... CodexBarCLI && install -m 0755 CodexBarCLI
  ~/.local/bin/codexbar`. S-Bridge'de fix.
- **Voice Telegram inbound wire** — `voice.py` SEAM hazır (Whisper backend),
  Telegram `message.voice` detection + `transcribe()` çağrısı S-Bridge'de.
- **Correction Telegram inbound** — `audit.py::write_correction` SEAM hazır,
  `/correct <idempotency_key> <text>` Telegram command S-Bridge'de.
- **Mind T2 ingest of corrections.jsonl** — corrections file SEAM hazır,
  `selffork_mind/ingest/heartbeat.py` extension S-Bridge'de.
- **SkillInstaller dashboard invocation** — `skills.py` SEAM hazır, lifespan
  hook veya `selffork skills sync` subcommand S-Bridge'de.
- **Structured tool round-trip** — `<selffork-tool-call>` ↔
  `<selffork-tool-response>` pause/resume mechanism S-Bridge'de (ana ambition).

Bu gap'ler S-Vision'ın SEAM scope'una göre kasıtlı boş bırakıldı (operator
[[no-mvp]] direktifi: scope split kabul, quality stage yasak — şu an seam
quality day-1; wire S-Bridge sprint'inde).

---

## Sıradaki adım

1. **Operator commit** (MANDATE 1). Önerilen commit mesajı:
   ```
   feat: snapper sidecar + endpoint synthesis + selffork train CLI

   BUG-1 fix: live quota gauges populate via auto-running snapper fleet +
   /api/usage/providers synthesis from CodexBar fallback reader. Fine-tune
   UI migrated to `selffork train` CLI subcommand per operator preference
   (one-shot operation belongs outside daily-driver dashboard).

   - snappers/runner.py: build_default_snapper_runner() factory; lifespan
     auto-boot mirroring CodexBar sidecar pattern.
   - dashboard/server.py: _synthesize_proactive_rows() merges proactive
     signal with audit-derived rows; audit truth wins on overlap.
   - reflex_router.py: deleted (459 LoC); replaced by reflex_manifest.py
     (canonical path + honest empty reader, audit-god MAJOR #1 preserved).
   - cli.py: new `selffork train` subcommand (info + dry plan stub, M7
     worker hook ready).
   - tests: +18 net (snapper factory · usage synthesis · CLI train ·
     manifest reader); ruff/mypy/tsc all green; 2456 backend pass.
   ```

2. **S-Bridge sprint kickoff** — bekleyen 5 wire (Voice inbound, Correction
   Telegram, Mind T2 ingest, SkillInstaller, structured tool round-trip)
   + BUG-2 install script fix.

---

**Standing:** TAM OLSUN BİZİM OLSUN · KALİTE HIZDAN ÖNCE · BENİ TANISIN
YETER · HER MESAJ SIFIRDAN DEĞİL.
