"""Agentic multi-tool trajectories (workflow/debug/control) — act -> observe -> act.

Dev/control chains over SelfFork's own tools: GitHub PR shipping, crash/ANR
triage, skill lifecycle, the Expo dev loop, quota rotation + scheduled sleep,
discover-then-use via tool_search, mid-flow AskUserQuestion on irreversible
forks, snapshot/diff regression checks, and kanban + context-pressure hygiene.
Each step's reasoning reads the PRIOR observed result and justifies the NEXT
call — the chaining behaviour single-call scenarios can't teach.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import AgenticStep, AgenticTrajectory

TRAJECTORIES: list[AgenticTrajectory] = [
    # ------------------------------------------------------------------
    # 1. Ship a PR: create -> discover workflows -> run CI -> verify ->
    #    merge -> record decision -> done
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="pr_ship_ci_merge",
        goal=(
            "[görev] feat/kota-paneli dalı hazır; arketic/fieldnote-app "
            "deposuna PR açılacak, CI yeşil görülünce squash-merge edilecek."
        ),
        steps=[
            AgenticStep(
                tool="github_pr_create",
                args={
                    "repo": "arketic/fieldnote-app",
                    "title": "feat: kota paneli",
                    "body": (
                        "Kota panelini oturum durumuna bağlar; pencere "
                        "yüzdesi ve sıfırlanma saati görünür."
                    ),
                    "head": "feat/kota-paneli",
                    "base": "main",
                },
                result=(
                    "[sonuç] PR #87 açıldı. Checks: hiçbir workflow koşmadı "
                    "(pending); mergeable: unknown."
                ),
                reasoning=(
                    "Dal hazır ve hedef depo/dal belli; akış PR'ı açmakla "
                    "başlar, CI ancak PR var olunca anlamlı."
                ),
            ),
            AgenticStep(
                tool="github_workflow_list",
                args={"repo": "arketic/fieldnote-app"},
                result=(
                    "[sonuç] İki workflow: ci.yml (lint+test, push/manuel "
                    "tetik) ve release.yml (yalnız tag)."
                ),
                reasoning=(
                    "PR'da hiçbir check koşmamış; hangi workflow'un CI "
                    "olduğunu tahmin etmeden önce listeyi görmek gerek."
                ),
            ),
            AgenticStep(
                tool="github_workflow_run",
                args={
                    "repo": "arketic/fieldnote-app",
                    "workflow": "ci.yml",
                    "ref": "feat/kota-paneli",
                },
                result="[sonuç] ci.yml tetiklendi; koşu #4123 kuyruğa alındı.",
                reasoning=(
                    "Liste CI'ın ci.yml olduğunu gösterdi; release.yml tag "
                    "işi. PR dalı üzerinde ci.yml'ı elle tetikliyorum."
                ),
            ),
            AgenticStep(
                tool="github_pr_view",
                args={"repo": "arketic/fieldnote-app", "number": 87},
                result=(
                    "[sonuç] PR #87: checks yeşil (ci.yml success), "
                    "mergeable: clean, 1 onay."
                ),
                reasoning=(
                    "Koşu #4123 bitmiş olmalı; merge kararından önce PR "
                    "üstünden check + mergeable durumunu doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="github_pr_merge",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 87,
                    "strategy": "squash",
                    "delete_branch": True,
                },
                result=(
                    "[sonuç] PR #87 squash ile birleşti; feat/kota-paneli "
                    "dalı silindi."
                ),
                reasoning=(
                    "Checks yeşil, mergeable clean, onay var; engel "
                    "kalmadı. Tek mantıksal değişiklik için squash uygun."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "PR #87 (kota paneli) squash-merge edildi; CI "
                        "ci.yml manuel tetikle koştu çünkü PR açılışı "
                        "workflow'u tetiklemedi."
                    ),
                    "kind": "decision",
                },
                result="[sonuç] Not kaydedildi (episodic).",
                reasoning=(
                    "Merge kalıcı bir karar ve 'PR açılışı CI tetiklemiyor' "
                    "bulgusu ileride lazım; Mind'a not düşüyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "PR #87 merge edildi, dal silindi, karar nota "
                        "işlendi; görev tamam."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Hedefin tüm adımları doğrulanarak bitti; kapatıyorum.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 2. Native crash triage: log -> thread dump -> snapshot -> issue ->
    #    note -> crit notify
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="crash_triage_native_segv",
        goal=(
            "[görev] fieldnote uygulaması cihazda az önce çöktü; kök neden "
            "toplanacak, kayıt altına alınıp ekip uyarılacak."
        ),
        steps=[
            AgenticStep(
                tool="crash_log_fetch",
                args={"max_lines": 300},
                result=(
                    "[sonuç] 10:42'de FATAL signal 11 (SIGSEGV), "
                    "libhermes.so, pid 8412. JS hata ekranı yok; çöküş "
                    "native katmanda."
                ),
                reasoning=(
                    "Çöküşün türü bilinmiyor; triyaj her zaman cihaz "
                    "günlüğünü çekmekle başlar."
                ),
            ),
            AgenticStep(
                tool="crash_thread_dump",
                args={},
                result=(
                    "[sonuç] main: JSI HostFunction -> "
                    "facebook::hermes::vm çağrısında; mqt_js kilitli "
                    "bekliyor. ANR izi yok."
                ),
                reasoning=(
                    "Günlük native SIGSEGV gösterdi; ANR değil. Native "
                    "çöküşte iş parçacığı yığınları kök nedeni verir, "
                    "crash_anr_dump konu dışı."
                ),
            ),
            AgenticStep(
                tool="crash_state_snapshot",
                args={"label": "hermes-segv", "include_logs": True},
                result=(
                    "[sonuç] 'hermes-segv' anlık durumu kaydedildi "
                    "(ekran + günlükler)."
                ),
                reasoning=(
                    "Yığın elde; cihaz durumu uçucu, yeniden başlatmada "
                    "kaybolur. Kanıtı etiketli anlık görüntüyle donduruyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_create",
                args={
                    "repo": "arketic/fieldnote-app",
                    "title": "Native crash: SIGSEGV libhermes (JSI HostFunction)",
                    "body": (
                        "pid 8412, 10:42. main iş parçacığı JSI "
                        "HostFunction içinde; anlık durum etiketi: "
                        "hermes-segv. Yığın ve günlük ektedir."
                    ),
                },
                result="[sonuç] Issue #42 oluşturuldu.",
                reasoning=(
                    "Kanıt donduruldu; kalıcı takip depoda olmalı. Yığın + "
                    "etiketle issue açıyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Hermes SIGSEGV: JSI HostFunction imzası, issue "
                        "#42, kanıt 'hermes-segv' etiketinde."
                    ),
                    "kind": "observation",
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Issue açıldı; aynı imza tekrar görülürse eşleştirmek "
                    "için gözlemi Mind'a işliyorum."
                ),
            ),
            AgenticStep(
                tool="notify_telegram",
                args={
                    "message": (
                        "Fatal native crash (SIGSEGV libhermes) — kanıt "
                        "toplandı, issue #42 açıldı."
                    ),
                    "level": "crit",
                },
                result="[sonuç] Telegram bildirimi iletildi.",
                reasoning=(
                    "Fatal çöküş operatörün hemen bilmesi gereken tek yönlü "
                    "haber; soru değil, notify_telegram crit yeter."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 3. ANR triage: log -> anr dump -> snapshot -> kanban -> pattern note
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="anr_triage_sqlite_lock",
        goal=(
            "[görev] Kullanıcılar 'uygulama donuyor' diyor; donmanın kök "
            "nedeni bulunup panoya iş olarak düşülecek."
        ),
        steps=[
            AgenticStep(
                tool="crash_log_fetch",
                args={},
                result=(
                    "[sonuç] 'ANR in com.arketic.fieldnote: Input "
                    "dispatching timed out' — senkron/kayıt ekranında. "
                    "Fatal sinyal yok."
                ),
                reasoning=(
                    "'Donma' çöküş de ANR de olabilir; ayrımı ancak cihaz "
                    "günlüğü yapar, önce onu çekiyorum."
                ),
            ),
            AgenticStep(
                tool="crash_anr_dump",
                args={},
                result=(
                    "[sonuç] main: SQLiteConnection.nativeExecute üzerinde "
                    "WAITING; sync-worker iş parçacığı yazma kilidini "
                    "tutuyor."
                ),
                reasoning=(
                    "Günlük ANR gösterdi, native çöküş değil; ANR'de doğru "
                    "kazı aracı crash_anr_dump, thread_dump genel kalır."
                ),
            ),
            AgenticStep(
                tool="crash_state_snapshot",
                args={
                    "label": "anr-sqlite-kilidi",
                    "include_a11y": True,
                    "include_logs": True,
                },
                result=(
                    "[sonuç] 'anr-sqlite-kilidi' kaydedildi: donmuş kayıt "
                    "ekranı + a11y ağacı + günlükler."
                ),
                reasoning=(
                    "Kök neden belli (ana iş parçacığı SQLite kilidinde); "
                    "donmuş ekranın kanıtını a11y dahil donduruyorum."
                ),
            ),
            AgenticStep(
                tool="kanban_card_add",
                args={
                    "title": "ANR: senkron yazması ana iş parçacığını kilitliyor",
                    "body": (
                        "main, SQLiteConnection.nativeExecute'ta WAITING; "
                        "sync-worker yazma kilidi tutuyor. Kanıt: "
                        "anr-sqlite-kilidi anlık durumu."
                    ),
                    "column": "backlog",
                },
                result="[sonuç] Kart kb-31 backlog'a eklendi.",
                reasoning=(
                    "Düzeltme bu oturumun işi değil, planlı iş; triyaj "
                    "çıktısını panoya backlog kartı olarak düşüyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Kalıp: senkron sırasında kayıt ekranı ANR'ı = "
                        "SQLite yazma kilidi ana iş parçacığını bekletiyor "
                        "(kart kb-31)."
                    ),
                    "kind": "pattern",
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Bu belirti-neden eşleşmesi tekrarlayabilir; kalıp "
                    "olarak Mind'a işleyip triyajı kapatıyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 4. Skill gap: search (0) -> list (confirm) -> create -> validate ->
    #    sync -> decision note
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="skill_gap_create_sync",
        goal=(
            "[görev] ANR triyajı her seferinde elle yapılıyor; bu akış "
            "için beceri var mı bakılacak, yoksa kurulup dağıtılacak."
        ),
        steps=[
            AgenticStep(
                tool="skill_search",
                args={"query": "anr triage"},
                result="[sonuç] 0 eşleşme.",
                reasoning=(
                    "Varlığı belirsizken create çift kayıt riski taşır; en "
                    "ucuz ilk adım kanonik dizinde arama."
                ),
            ),
            AgenticStep(
                tool="skill_list",
                args={},
                result=(
                    "[sonuç] 12 beceri listelendi; en yakını expo-triage "
                    "(kapsamı Metro/kırmızı ekran). ANR'a değinen yok."
                ),
                reasoning=(
                    "Arama 0 döndü ama beceri farklı adla durabilir; "
                    "create'ten önce tam listeyle boşluğu doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="skill_create",
                args={
                    "name": "anr-triage",
                    "description": (
                        "ANR kök neden akışı: crash_log_fetch -> "
                        "crash_anr_dump -> ana iş parçacığı kilidi analizi "
                        "-> kanıt anlık durumu"
                    ),
                },
                result=(
                    "[sonuç] anr-triage iskeleti kanonik dizinde açıldı "
                    "(SKILL.md hazır)."
                ),
                reasoning=(
                    "Boşluk iki yoldan doğrulandı; kaynak arşiv olmadığı "
                    "için install değil, sıfırdan skill_create doğru."
                ),
            ),
            AgenticStep(
                tool="skill_validate",
                args={"name": "anr-triage"},
                result=(
                    "[sonuç] anr-triage geçerli: zorunlu alanlar tam, "
                    "0 hata."
                ),
                reasoning=(
                    "İskelet yeni yazıldı; bozuk beceriyi dağıtmamak için "
                    "sync'ten önce doğrulama koşuyorum."
                ),
            ),
            AgenticStep(
                tool="skill_sync",
                args={},
                result=(
                    "[sonuç] Kanonikten 3 CLI dizinine dağıtıldı "
                    "(claude-code, codex, gemini-cli)."
                ),
                reasoning=(
                    "Beceri geçerli ama yalnız kanonik kopyada; tüm "
                    "CLI'ların görmesi için fan-out'u skill_sync yapar."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "anr-triage becerisi oluşturuldu, doğrulandı ve 3 "
                        "CLI dizinine dağıtıldı; ANR akışı artık becerili."
                    ),
                    "kind": "decision",
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Yeni yeteneğin varlığı sonraki oturumlarda "
                    "hatırlanmalı; kararı Mind'a işleyip bitiriyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 5. Expo dev loop: doctor (issue) -> install fix -> doctor clean ->
    #    dev_start -> run_android -> logs -> done
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="expo_dev_loop_doctor_fix",
        goal=(
            "[görev] fieldnote uygulaması emülatörde sağlıklı biçimde "
            "ayağa kaldırılacak; Metro kapalı, ortam durumu bilinmiyor."
        ),
        steps=[
            AgenticStep(
                tool="expo_doctor",
                args={"project_dir": "apps/fieldnote"},
                result=(
                    "[sonuç] 1 sorun: expo-updates sürümü kurulu SDK ile "
                    "uyumsuz (beklenen ~0.27, kurulu 0.24)."
                ),
                reasoning=(
                    "Ortam durumu bilinmezken sunucu kaldırmak kör uçuş; "
                    "önce doctor ile sağlık taraması."
                ),
            ),
            AgenticStep(
                tool="expo_install",
                args={"package": "expo-updates", "project_dir": "apps/fieldnote"},
                result=(
                    "[sonuç] expo-updates SDK'ya uyumlu sürüme (0.27.x) "
                    "güncellendi."
                ),
                reasoning=(
                    "Doctor sürüm uyumsuzluğu buldu; expo_install paketi "
                    "SDK'nın istediği sürümle hizalar, düz npm hizalamaz."
                ),
            ),
            AgenticStep(
                tool="expo_doctor",
                args={"project_dir": "apps/fieldnote"},
                result="[sonuç] Tüm kontroller temiz; sorun kalmadı.",
                reasoning=(
                    "Düzeltmeyi varsaymak yerine doctor'ı yeniden koşup "
                    "temiz raporu görmek gerek."
                ),
            ),
            AgenticStep(
                tool="expo_dev_start",
                args={"project_dir": "apps/fieldnote", "clear_cache": True},
                result="[sonuç] Metro 8081'de ayakta; önbellek temizlendi.",
                reasoning=(
                    "Ortam temiz; bağımlılık değiştiği için Metro'yu "
                    "önbelleği temizleyerek başlatmak bayat bundle riskini "
                    "keser."
                ),
            ),
            AgenticStep(
                tool="expo_run_android",
                args={"project_dir": "apps/fieldnote", "variant": "debug"},
                result=(
                    "[sonuç] Debug yapı emülatöre kuruldu; uygulama açıldı "
                    "ve Metro'ya bağlandı."
                ),
                reasoning=(
                    "Native bağımlılık (expo-updates) değişti; salt reload "
                    "yetmez, yapıyı cihazda yeniden kurmak gerekir."
                ),
            ),
            AgenticStep(
                tool="expo_logs_capture",
                args={"project_dir": "apps/fieldnote", "max_lines": 150},
                result=(
                    "[sonuç] Kırmızı ekran yok; yalnız bilinen bir "
                    "deprecation uyarısı. Açılış temiz."
                ),
                reasoning=(
                    "Uygulama açıldı görünse de sessiz hatalar loglarda "
                    "saklanır; sağlıklı demeden önce logları alıyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "doctor temiz, uygulama emülatörde, loglar hatasız; "
                        "dev döngüsü ayakta."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Üç kanıt da (doctor, kurulum, log) sağlıklı; bitti.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 6. Rate limit — evidence then rotate: snapshot -> available ->
    #    rotate -> verify session -> done
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="quota_exhausted_rotate",
        goal=(
            "[görev] claude-code yanıtları 'rate limited' uyarısı taşıyor; "
            "iş acil, kesintisiz sürmeli."
        ),
        steps=[
            AgenticStep(
                tool="quota_snapshot",
                args={"cli_id": "claude-code"},
                result=(
                    "[sonuç] claude-code five_hour penceresi %99 dolu; "
                    "sıfırlanmaya 3s 11d var."
                ),
                reasoning=(
                    "Belirti kota olabilir ama kanıt yok; körlemesine "
                    "rotate bağlam kaybettirir, önce pencereyi ölçüyorum."
                ),
            ),
            AgenticStep(
                tool="available_clis",
                args={},
                result=(
                    "[sonuç] codex: sağlıklı, boşta. gemini-cli: degraded "
                    "(son 3 çağrıda zaman aşımı)."
                ),
                reasoning=(
                    "Tükenme doğrulandı; geçmeden önce hangi CLI'ın "
                    "gerçekten sağlıklı olduğunu görmek gerek."
                ),
            ),
            AgenticStep(
                tool="rotate_to",
                args={
                    "cli_id": "codex",
                    "reason": (
                        "claude-code 5h penceresi %99; codex sağlıklı ve "
                        "boşta, iş bekleyemez"
                    ),
                },
                result="[sonuç] Aktif CLI codex'e döndürüldü.",
                reasoning=(
                    "İki sağlam kanıt var: pencere dolu + codex sağlıklı. "
                    "3 saat sleep kaybettirir; tek seferlik geçiş rotate_to."
                ),
            ),
            AgenticStep(
                tool="session_state",
                args={},
                result=(
                    "[sonuç] Aktif CLI: codex; görev bağlamı korunmuş, "
                    "bekleyen eylem yok."
                ),
                reasoning=(
                    "Rotasyon sonrası oturumun sağlam devrildiğini "
                    "varsaymak yerine durumdan okuyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "rotasyon doğrulandı; iş codex üzerinde kesintisiz "
                        "sürüyor."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Geçiş kanıtla yapıldı ve doğrulandı; akış tamam.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 7. Rate limit — no healthy CLI: snapshot -> available -> warn ->
    #    sleep_until -> operator interjects -> cancel_pending -> state
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="quota_all_exhausted_sleep_cancel",
        goal=(
            "[görev] Gece toplu iş koşarken tüm yanıtlar rate-limit "
            "hatasına düştü; oturum kaynak bulana dek doğru şekilde "
            "bekletilecek."
        ),
        steps=[
            AgenticStep(
                tool="quota_snapshot",
                args={},
                result=(
                    "[sonuç] claude-code %100 (ilk sıfırlanma 15:00 UTC, "
                    "epoch 1783090800); codex %100; gemini-cli %100."
                ),
                reasoning=(
                    "Hata yaygın; tek CLI değil hepsinin penceresini tek "
                    "seferde görmek için cli_id vermeden ölçüyorum."
                ),
            ),
            AgenticStep(
                tool="available_clis",
                args={},
                result="[sonuç] Sağlıklı CLI yok; üçü de kota-blokeli.",
                reasoning=(
                    "Tüm pencereler dolu görünüyor; rotate seçeneğini "
                    "kapatmadan önce sağlık listesini de doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="notify_telegram",
                args={
                    "message": (
                        "Tüm CLI kotaları doldu; ilk pencere 15:00 UTC. "
                        "Oturumu o saate dek uyutuyorum."
                    ),
                    "level": "warn",
                },
                result="[sonuç] Bildirim iletildi.",
                reasoning=(
                    "Rotasyon çıkışsız, plan uyku; operatör saatlik "
                    "sessizliği kesinti sanmasın diye önce tek yönlü uyarı."
                ),
            ),
            AgenticStep(
                tool="sleep_until",
                args={
                    "epoch_seconds": 1783090800,
                    "reason": "tüm CLI kotaları dolu; ilk pencere 15:00 UTC",
                    "kind": "five_hour",
                },
                result=(
                    "[sonuç] Uyku planlandı (action_id: sess_7b1e90). "
                    "Hemen ardından operatör yazdı: 'Bekleme! Manuel API "
                    "anahtarı taktım, şimdi devam et.'"
                ),
                reasoning=(
                    "Boş döngüde beklemek log kirletir; pencere açılış "
                    "epoch'u elimde, o ana dek sleep_until doğru araç."
                ),
            ),
            AgenticStep(
                tool="cancel_pending",
                args={
                    "action_id": "sess_7b1e90",
                    "reason": (
                        "operatör beklemeyi iptal etti; manuel anahtarla "
                        "hemen devam edilecek"
                    ),
                },
                result="[sonuç] sess_7b1e90 iptal edildi; uyku kalktı.",
                reasoning=(
                    "Uyku planlıyken koşullar değişti: operatör kaynak "
                    "sağladı. Planlı eylemi geri almanın yolu cancel_pending."
                ),
            ),
            AgenticStep(
                tool="session_state",
                args={},
                result=(
                    "[sonuç] Oturum aktif; bekleyen eylem yok, toplu iş "
                    "kaldığı adımdan sürdürülebilir."
                ),
                reasoning=(
                    "İptal sonrası askıda eylem kalmadığını doğrulamadan "
                    "işe dönmek riskli; son kontrol session_state."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 8. Discover-then-use: reload -> tool_search -> ui_verify_* x2 ->
    #    note -> done
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="ui_fix_discover_verify",
        goal=(
            "[görev] Kota panelindeki metin taşması düzeltildi; değişiklik "
            "cihazda görsel olarak doğrulanacak. Metro 8081'de çalışıyor."
        ),
        steps=[
            AgenticStep(
                tool="expo_metro_reload",
                args={},
                result=(
                    "[sonuç] Bundle yenilendi; panel yeni koduyla ekranda."
                ),
                reasoning=(
                    "Değişiklik salt JS ve Metro ayakta; cihaza yeni kodu "
                    "sıcak yenileme taşır, yeniden kurulum gerekmez."
                ),
            ),
            AgenticStep(
                tool="tool_search",
                args={"query": "ekranda metin görünürlüğü ve taşma doğrula", "top_k": 5},
                result=(
                    "[sonuç] Ertelenmiş araçlar bulundu ve açıldı: "
                    "ui_verify_text_visible, ui_verify_no_overflow, "
                    "ui_verify_ocr_contains."
                ),
                reasoning=(
                    "Görünür listede ekran doğrulama aracı yok; ad tahmin "
                    "etmek şema hatasıyla düşer, önce tool_search."
                ),
            ),
            AgenticStep(
                tool="ui_verify_text_visible",
                args={"text": "Kota: %98"},
                result=(
                    "[sonuç] Metin görünür; tam eşleşme panel başlığında."
                ),
                reasoning=(
                    "Arama doğrulama araçlarını açtı; önce kritik metnin "
                    "ekranda hâlâ göründüğünü kontrol ediyorum."
                ),
            ),
            AgenticStep(
                tool="ui_verify_no_overflow",
                args={},
                result="[sonuç] Taşma yok; tüm ögeler kapsayıcı içinde.",
                reasoning=(
                    "Metin görünüyor ama şikâyet taşmaydı; düzeltmenin asıl "
                    "iddiasını taşma kontrolüyle sınıyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Kota paneli taşma düzeltmesi cihazda doğrulandı: "
                        "metin görünür + taşma yok (reload sonrası)."
                    ),
                    "kind": "observation",
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "İki kontrol de geçti; doğrulama kanıtını Mind'a "
                    "işlemek gelecekteki gerilemede referans olur."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "görsel doğrulama iki bağımsız kontrolle geçti; "
                        "taşma düzeltmesi cihazda çalışıyor."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Doğrulama hedefi kanıtla karşılandı; kapatıyorum.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 9. Ambiguity mid-flow: doctor -> eas_build -> AskUserQuestion
    #    (irreversible fork) -> eas_submit -> notify -> note -> done
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="release_ambiguous_channel",
        goal=(
            "[görev] Operatör: 'Android sürümünü çıkar.' Yapı üretilecek; "
            "yayın kanalı komutta belirtilmemiş."
        ),
        steps=[
            AgenticStep(
                tool="expo_doctor",
                args={"project_dir": "apps/fieldnote"},
                result="[sonuç] Tüm kontroller temiz.",
                reasoning=(
                    "Üretim yapısı pahalı; bozuk ortamda 20 dakikalık "
                    "build'e girmeden önce doctor koşuyorum."
                ),
            ),
            AgenticStep(
                tool="expo_eas_build",
                args={
                    "project_dir": "apps/fieldnote",
                    "platform": "android",
                    "profile": "production",
                },
                result=(
                    "[sonuç] Build tamamlandı; imzalı .aab artefaktı hazır."
                ),
                reasoning=(
                    "Ortam temiz; 'sürüm çıkar' her iki kanalda da önce "
                    "üretim yapısı ister, build kanal seçimini bağlamaz."
                ),
            ),
            AgenticStep(
                tool="AskUserQuestion",
                args={
                    "questions": [
                        {
                            "question": (
                                "Üretim yapısı hazır; 'sürümü çıkar' ile "
                                "hangi yayın kastediliyor?"
                            ),
                            "header": "Yayın kanalı",
                            "options": [
                                {
                                    "label": "Mağaza gönderimi",
                                    "description": (
                                        "expo_eas_submit: .aab Play "
                                        "incelemesine gider; geri çekmesi "
                                        "zor"
                                    ),
                                },
                                {
                                    "label": "OTA yayını",
                                    "description": (
                                        "expo_publish: yalnız JS "
                                        "değişikliği kullanıcılara anında "
                                        "iner"
                                    ),
                                },
                            ],
                        },
                    ],
                },
                result="[sonuç] Operatör seçti: 'Mağaza gönderimi'.",
                reasoning=(
                    "Build bitti ama iki yayın yolu da makul ve ikisi de "
                    "geri dönüşsüz; yanlış tahmin kullanıcıya hatalı sürüm "
                    "basar. Tahmin değil soru gerekir."
                ),
            ),
            AgenticStep(
                tool="expo_eas_submit",
                args={
                    "project_dir": "apps/fieldnote",
                    "platform": "android",
                    "profile": "production",
                },
                result=(
                    "[sonuç] .aab Play Console'a yüklendi; inceleme "
                    "kuyruğunda."
                ),
                reasoning=(
                    "Operatör mağaza kanalını seçti; hazır artefaktı "
                    "incelemeye eas_submit gönderir."
                ),
            ),
            AgenticStep(
                tool="notify_telegram",
                args={
                    "message": (
                        "fieldnote Android production yapısı Play "
                        "incelemesine gönderildi."
                    ),
                    "level": "info",
                },
                result="[sonuç] Bildirim iletildi.",
                reasoning=(
                    "Gönderim tamam; inceleme saatler sürebilir, operatöre "
                    "tek yönlü bilgi düşmek yeterli."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Sürüm kararı: 'sürümü çıkar' bu projede mağaza "
                        "gönderimi demek (operatör seçimi, Android "
                        "production)."
                    ),
                    "kind": "decision",
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Operatörün kanal tercihi gelecek sürümlerde aynı "
                    "soruyu tekrarlatmamak için karar olarak saklanmalı."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Android production yapısı Play incelemesinde; "
                        "kanal kararı kayıtlı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Yayın operatör onaylı kanaldan yapıldı; akış tamam.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 10. Duplicate issue triage: list -> view both -> close dup ->
    #     cross-comment -> pointer note
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="issue_dedup_triage",
        goal=(
            "[görev] arketic/fieldnote-app açık issue'ları taranacak; "
            "kopyalar birleştirilip takip tek yerde toplanacak."
        ),
        steps=[
            AgenticStep(
                tool="github_issue_list",
                args={"repo": "arketic/fieldnote-app", "state": "open", "limit": 20},
                result=(
                    "[sonuç] 5 açık issue. #35 ve #38 başlıkları aynı "
                    "hermes çöküşünü anlatıyor gibi."
                ),
                reasoning=(
                    "Kopya avı envanterle başlar; kapalıları taramak "
                    "gereksiz, open + makul limit yeter."
                ),
            ),
            AgenticStep(
                tool="github_issue_view",
                args={"repo": "arketic/fieldnote-app", "number": 38},
                result=(
                    "[sonuç] #38: SIGSEGV libhermes, JSI HostFunction "
                    "yığını; cihaz Pixel 8 / Android 15."
                ),
                reasoning=(
                    "Başlık benzerliği kanıt değil; kopya kararı için önce "
                    "yeni raporun yığınını okumak gerek."
                ),
            ),
            AgenticStep(
                tool="github_issue_view",
                args={"repo": "arketic/fieldnote-app", "number": 35},
                result=(
                    "[sonuç] #35: aynı SIGSEGV imzası; daha eski, repro "
                    "adımları ve tartışma daha zengin."
                ),
                reasoning=(
                    "#38'in imzası elimde; eşleşmeyi doğrulamak ve hangisi "
                    "kalacak demek için #35'i de okuyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_close",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 38,
                    "comment": "#35 kopyası; takip orada sürecek.",
                },
                result="[sonuç] #38 açıklamayla kapatıldı.",
                reasoning=(
                    "İmzalar birebir; kanonik kayıt daha zengin olan #35. "
                    "Yeniyi gerekçeli kapatıyorum ki raporlayan izi bulsun."
                ),
            ),
            AgenticStep(
                tool="github_issue_comment",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 35,
                    "body": (
                        "#38 kopya olarak kapatıldı; oradaki ek cihaz "
                        "bilgisi: Pixel 8, Android 15."
                    ),
                },
                result="[sonuç] Yorum #35'e eklendi.",
                reasoning=(
                    "#38 kapansa da içindeki cihaz bilgisi değerli; kaybı "
                    "önlemek için kanonik issue'ya taşıyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Hermes SIGSEGV takibi #35'te birleştirildi; #38 "
                        "kopya kapatıldı, cihaz verisi taşındı."
                    ),
                    "kind": "pointer",
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Sonraki çökme raporunda doğru issue'ya gitmek için "
                    "kanonik adresi işaretçi olarak saklıyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 11. Regression check via snapshots: list -> baseline -> reload ->
    #     after -> diff -> cleanup -> note
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="regression_snapshot_diff",
        goal=(
            "[görev] Onboarding başlık düzeltmesi cihaza alınacak; ekran "
            "durumunun düzeltme dışında değişmediği kanıtlanacak."
        ),
        steps=[
            AgenticStep(
                tool="crash_state_list",
                args={},
                result=(
                    "[sonuç] Kayıtlı tek etiket: anr-sqlite-kilidi. "
                    "Onboarding için temel yok."
                ),
                reasoning=(
                    "Karşılaştırma temel ister; önce elde kullanılabilir "
                    "bir onboarding anlık durumu var mı bakıyorum."
                ),
            ),
            AgenticStep(
                tool="crash_state_snapshot",
                args={"label": "onboarding-fix-oncesi", "include_a11y": True},
                result=(
                    "[sonuç] 'onboarding-fix-oncesi' kaydedildi (ekran + "
                    "a11y ağacı)."
                ),
                reasoning=(
                    "Temel yok; düzeltmeyi almadan ÖNCE mevcut durumu "
                    "a11y ağacıyla donduruyorum, yoksa diff imkânsız."
                ),
            ),
            AgenticStep(
                tool="expo_metro_reload",
                args={},
                result="[sonuç] Düzeltilmiş bundle cihazda; ekran yenilendi.",
                reasoning=(
                    "Temel güvende; değişiklik salt JS olduğundan yeni "
                    "kodu sıcak yenileme taşır."
                ),
            ),
            AgenticStep(
                tool="crash_state_snapshot",
                args={"label": "onboarding-fix-sonrasi", "include_a11y": True},
                result="[sonuç] 'onboarding-fix-sonrasi' kaydedildi.",
                reasoning=(
                    "Yeni kod ekranda; diff'in ikinci ucu için aynı "
                    "kapsamla (a11y dahil) ikinci anlık durumu alıyorum."
                ),
            ),
            AgenticStep(
                tool="crash_state_diff",
                args={
                    "label_a": "onboarding-fix-oncesi",
                    "label_b": "onboarding-fix-sonrasi",
                },
                result=(
                    "[sonuç] Tek fark: başlık metni düzeltilmiş. A11y "
                    "ağacında kayıp/ekstra öge yok."
                ),
                reasoning=(
                    "İki uç da elimde; gerileme sorusunu göz kararı değil "
                    "makine diff'i yanıtlamalı."
                ),
            ),
            AgenticStep(
                tool="crash_state_delete",
                args={"label": "onboarding-fix-oncesi"},
                result="[sonuç] Geçici temel silindi.",
                reasoning=(
                    "Diff temiz çıktı; 'oncesi' etiketi tek kullanımlık "
                    "temeldi, bırakılırsa gelecekte yanlış temel olur."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Onboarding başlık düzeltmesi diff'le doğrulandı: "
                        "tek fark hedeflenen metin, a11y ağacı sabit."
                    ),
                    "kind": "observation",
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Kanıtın özeti kalıcı olmalı; snapshot silindiği için "
                    "sonucu Mind'a işleyip akışı kapatıyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 12. Kanban-driven work + context pressure: move in_progress ->
    #     session_state (%91) -> compact -> auto_pr -> move review -> done
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="kanban_flow_context_compact",
        goal=(
            "[görev] Pano kartı kb-12 ('kota paneli PR'ı') işlenecek. "
            "Oturum saatlerdir açık; yanıtlar yavaşladı."
        ),
        steps=[
            AgenticStep(
                tool="kanban_card_move",
                args={"card_id": "kb-12", "to_column": "in_progress"},
                result="[sonuç] kb-12 in_progress sütununa taşındı.",
                reasoning=(
                    "Pano akışında işe başlamanın ilk adımı kartı "
                    "in_progress'e çekmek; ekip kimin ne yaptığını görür."
                ),
            ),
            AgenticStep(
                tool="session_state",
                args={},
                result=(
                    "[sonuç] Bağlam %91 dolu; eski expo log blokları "
                    "birikmiş. Aktif CLI: claude-code."
                ),
                reasoning=(
                    "Yavaşlamanın olası nedeni bağlam şişkinliği; PR gibi "
                    "uzun bir üretime girmeden önce durumu ölçüyorum."
                ),
            ),
            AgenticStep(
                tool="compact_context",
                args={
                    "strategy": "summary",
                    "reason": (
                        "bağlam %91; eski log gövdeleri özetlenip PR işine "
                        "yer açılacak"
                    ),
                },
                result=(
                    "[sonuç] Bağlam %34'e indi; görev bağlamı ve kart "
                    "bilgisi korundu."
                ),
                reasoning=(
                    "%91 doluluk PR gövdesi üretirken taşma riski; log "
                    "gövdeleri özetlenebilir içerik, summary stratejisi "
                    "bilgiyi atmadan sıkıştırır."
                ),
            ),
            AgenticStep(
                tool="auto_pr_create",
                args={
                    "title": "feat: kota paneli",
                    "body": (
                        "Kota panelini oturum durumuna bağlar; taşma "
                        "düzeltmesi dahil. Pano kartı: kb-12."
                    ),
                },
                result="[sonuç] Mevcut çalışma dalından PR #91 açıldı.",
                reasoning=(
                    "Yer açıldı; değişiklikler zaten mevcut dalda. Depo ve "
                    "dal bağlamdan çıkarılabildiği için auto_pr_create "
                    "yeter, açık repo/head gerekmez."
                ),
            ),
            AgenticStep(
                tool="kanban_card_move",
                args={"card_id": "kb-12", "to_column": "review"},
                result="[sonuç] kb-12 review sütununa taşındı.",
                reasoning=(
                    "PR #91 açık; iş artık gözden geçirme bekliyor, kartın "
                    "yeri review sütunu."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": "PR #91 açık, kart kb-12 review'da; tur tamam.",
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning=(
                    "Kartın bu turdaki işi PR'a bağlanıp panoya işlendi; "
                    "merge ayrı turun işi, burada bitiriyorum."
                ),
            ),
        ],
    ),
]

__all__ = ["TRAJECTORIES"]
