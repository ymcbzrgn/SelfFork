# M5 R1 Vision Eval — 30-Task Held-Out Corpus

> **Bağlam:** ADR-005:571 + M5_Body_Plan.md §3.5
> **R1 gate:** Action precision ≥ %85 (action + target + bbox IoU ≥ 0.5 AND)
> **Bouncing back:** R1 fail → ROADMAP §M5 vision drivers M6'a regress

## Dataset Layout (Hibrit — master index + per-task dir)

```
benchmarks/m5_vision_eval/
├── README.md                # bu dosya
├── index.jsonl              # her satır: task_id → dir mapping
├── tasks/
│   ├── web_001_google_signin/
│   │   ├── screenshot.png   # ham PNG, gerçek ekran
│   │   ├── goal.txt         # operator instruction (Türkçe veya İngilizce)
│   │   └── expected_action.json   # ground-truth eylem
│   ├── web_002_github_pr_merge/...
│   └── ...
├── run_eval.py              # R1 gate harness (real model; real_runtime)
├── validate_dataset.py      # CI hook (index ↔ dir senkron)
├── synth.py                 # sentetik fixture üretici (modelsiz smoke)
├── conftest.py              # importlib modunda sibling import köprüsü
└── test_run_eval.py         # OFFLINE harness testleri (modelsiz)
```

## index.jsonl Schema

Her satır tek bir JSON nesnesi:

```json
{
  "task_id": "web_001_google_signin",
  "surface": "web",
  "dir": "tasks/web_001_google_signin",
  "instruction_summary": "click Sign in button on Google homepage"
}
```

`surface` enum'ı: `web | desktop | android | ios | macos`.

## expected_action.json Schema

```json
{
  "action": "click",
  "target": "Sign in",
  "bbox": [1750, 80, 80, 32],
  "tolerance_px": 8,
  "notes": "Top-right corner, white text on blue button"
}
```

| Field | Required | Tip | Açıklama |
|---|---|---|---|
| `action` | ✓ | enum | `click \| type \| swipe \| scroll \| press_key \| wait` (`prompt.py:34-39`'taki enum'la birebir) |
| `target` | ✓ | string | Element label; case-insensitive substring match |
| `bbox` | optional | `[x, y, w, h]` | Sağlandıysa IoU ≥ 0.5 zorunlu, yoksa bbox kriteri atlanır |
| `tolerance_px` | optional | int | Bilgi amaçlı (eval kullanmaz; operator kullanır) |
| `notes` | optional | string | Operator için human-readable hint |

## R1 Pass Rule

```
pass = predicted.action == expected.action
   AND expected.target.lower() in predicted.target.lower()  (substring, iki yönlü)
   AND (expected.bbox sağlanmadıysa True
        veya  bbox_iou(predicted.bbox, expected.bbox) ≥ 0.5)
```

Gate: `pass_count / total ≥ 0.85`.

## 30-Task Seeding Protocol

Operator manuel olarak üretecek (yapay zeka screenshot çekemez).

Hedef dağılım:
- **10 task** web (login, form submit, OAuth callback, search, calendar, vs.)
- **10 task** macOS desktop (Finder, Settings, AppleScript launch, screenshot capture)
- **5 task** Android (Settings, Chrome, Play Store, APK install dialog)
- **5 task** iOS sim (Safari, Settings, Mail, App Store)

Her task için:

1. Driver ile gerçek ekran fotosu çek (örn. `await drv.screenshot()` → `screenshot.png`).
2. `goal.txt` yaz — operator vision'a vereceği instruction (örn. "click the Sign in button").
3. `expected_action.json` yaz — ground-truth eylem.
4. `index.jsonl`'a satır ekle.
5. `python validate_dataset.py` çalıştır — drift yok mu kontrol.
6. 30 task tamamlandığında `pytest run_eval.py -v` ile R1 gate'i kapat.

## Adapter Seçimi (Cross-Adapter Eval)

Default: MLX (Apple Silicon). Linux/Ollama tarafını da test etmek için:

```bash
# MLX
.venv/bin/pytest benchmarks/m5_vision_eval/run_eval.py -v

# Ollama
SELFFORK_R1_ADAPTER=ollama .venv/bin/pytest benchmarks/m5_vision_eval/run_eval.py -v
```

İki adapter ayrı ayrı koşulur; raporlar `~/.selffork/audit/m5_r1_eval_<adapter>_<ts>.jsonl` altında ayrılır.

## Eval Output (Audit JSONL)

Her task için bir satır:

```json
{
  "task_id": "web_001_google_signin",
  "surface": "web",
  "instruction": "click Sign in button",
  "expected": {"action": "click", "target": "Sign in", "bbox": [...]},
  "predicted": {"action": "click", "target": "Sign In", "bbox": [...], "confidence": 0.91, "tier": 1, "duration_ms": 412},
  "action_ok": true,
  "target_ok": true,
  "bbox_ok": true,
  "bbox_iou": 0.78,
  "pass": true
}
```

## Reproducibility

- **Görsel deterministik:** ham PNG dosyaları repo'da (git LFS düşünülmedi; 30 task @ ~500KB = ~15MB, OK).
- **Vision deterministik:** `temperature=0.0` (default — `runtime.py:71`).
- **Model deterministik:** `mlx-community/gemma-4-E2B-it-4bit` veya `gemma4:e2b-q4_K_M`; aktif config `GET /api/settings/vision` ile sorgulanır.

## Offline Harness Doğrulaması (modelsiz — CI + geliştirici)

Gerçek R1 gate bir vision modeli (MLX/Ollama) + gerçek ekran fotoları ister;
ikisi de CI'da veya GPU'suz makinede üretilemez. Ama **harness'ın kendi
doğruluğu** modelsiz doğrulanır ve doğrulanmalıdır — R1 gate'in ship/regress
kararı bu matematiğe dayanır:

- **`test_run_eval.py`** (pytest, `testpaths`'e dahil → her CI koşusu + `uv run
  pytest` ile çalışır): `_bbox_iou`, `_target_match`, `evaluate_decision` (R1
  pass kuralı), `summarize` birim testleri + tam skorlama hattının stub
  adapter ile uçtan uca smoke'u.
- **`synth.py`**: saf-stdlib PNG üretici (Pillow yok). Bilinen bbox'lı,
  deterministik, >1 KB sentetik ekran fotoları çizer — harness'ı gerçek model
  olmadan uçtan uca çalıştırmaya yeter. **Sentetik ≠ R1 gate**: sadece boru
  tesisatını (IoU, target match, aggregation, audit) kanıtlar. Elle smoke
  korpusu üretmek için:

  ```bash
  uv run python benchmarks/m5_vision_eval/synth.py --out /tmp/synth_corpus
  ```

- **`validate_dataset.py`**: CI'da ayrı bir adım olarak koşar
  (`.github/workflows/ci.yml` → "Validate M5 vision eval dataset"), `index.jsonl`
  ↔ `tasks/` drift'ini her PR'da yakalar (script exit 1). Aynı kontrol
  `test_run_eval.py::test_committed_dataset_in_sync` ile pytest'te de var.

Gerçek gate (`run_eval.py::test_r1_gate`) `@pytest.mark.real_runtime` ile
işaretli **ve** `test_*.py` isminde değil — yani CI'nın `-m "not real_runtime"`
filtresi onu asla çalıştırmaz; operatör gerçek model + 30-task korpusla
`pytest benchmarks/m5_vision_eval/run_eval.py -v` diyerek açıkça koşar.

## Karşı Senaryo (Bouncing Back)

R1 < %85 ise harness exit 1 + JSONL rapor üretir. Operator:

1. Failed task'ları topla: `jq 'select(.pass==false) | {task_id, predicted, expected, bbox_iou}' ~/.selffork/audit/m5_r1_eval_*.jsonl`
2. Action / target / bbox kategorilerinden hangisi en çok bozuluyor?
3. ROADMAP §M5 — "Vision drivers M6'a regress" patikasını tetikle.
