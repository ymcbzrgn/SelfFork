"""Cross-domain + new-surface agentic trajectories — act -> observe -> act.

Surfaces the earlier trajectory sets don't cover: VR/spatial flows (Quest
passthrough/boundary/controller, visionOS simulator boot->find->click->logs),
desktop-heavy multi-app automation, mind-heavy survival chains
(session_state -> mind_recall -> act -> mind_note_add -> compact), and flows
that SPAN domains: browser research feeding kanban + GitHub, an Android crash
triaged into an issue and a mind note, a failed ui_verify escalated with a
screenshot into an issue comment, and crash-state snapshot/diff evidence
posted back to GitHub. Each step's reasoning reads the PRIOR observed result
and justifies the NEXT tool — often on a DIFFERENT surface, which is exactly
the hop a small model never learns from single-surface chains.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import AgenticStep, AgenticTrajectory

TRAJECTORIES: list[AgenticTrajectory] = [
    # ------------------------------------------------------------------
    # 1. VR/spatial (Quest): device check -> boundary -> passthrough ->
    #    recenter -> launch -> controller -> screenshot verify
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="quest_passthrough_mr_smoke",
        goal=(
            "[görev] Quest 3'te FitBox VR'ın karma gerçeklik (passthrough) "
            "modu test edilecek; oyuncu güvenli alan içinde başlamalı ve "
            "antrenman sahnesinin passthrough üstünde açıldığı doğrulanmalı."
        ),
        steps=[
            AgenticStep(
                tool="quest_device_info",
                args={},
                result=(
                    "[sonuç] Quest 3, OS v66, pil %78, geliştirici modu açık, "
                    "USB bağlantısı aktif."
                ),
                reasoning=(
                    "Teste başlamadan cihazın sürümünü ve pilini görmek gerek; "
                    "v66 altında passthrough API'si farklı davranıyor ve düşük "
                    "pil uzun MR oturumunu yarıda keser."
                ),
            ),
            AgenticStep(
                tool="quest_get_boundary",
                args={},
                result=(
                    "[sonuç] Roomscale sınır tanımlı: 2.5m x 2.0m, durum: "
                    "aktif, ihlal yok."
                ),
                reasoning=(
                    "Cihaz hazır göründü; FitBox hareketli bir antrenman "
                    "uygulaması, sınır tanımsızsa passthrough testi güvenli "
                    "değil. Önce boundary durumunu okuyorum."
                ),
            ),
            AgenticStep(
                tool="quest_passthrough_enable",
                args={},
                result="[sonuç] Passthrough açıldı; kamera görüntüsü aktif.",
                reasoning=(
                    "2.5x2.0m aktif sınır yeterli; MR testi kamera görüntüsü "
                    "ister, uygulamayı açmadan önce passthrough'u ben "
                    "açıyorum ki launch anındaki davranış gözlemlenebilsin."
                ),
            ),
            AgenticStep(
                tool="quest_recenter",
                args={},
                result="[sonuç] Görüş merkezi kullanıcı yönüne sıfırlandı.",
                reasoning=(
                    "Passthrough açılırken origin kayabiliyor; sahne yamuk "
                    "doğarsa test sonucu yanıltır. Launch'tan hemen önce "
                    "recenter en temiz başlangıcı verir."
                ),
            ),
            AgenticStep(
                tool="quest_app_launch",
                args={"package": "com.fitbox.vr"},
                result=(
                    "[sonuç] com.fitbox.vr açıldı; ana menü geldi, arka planda "
                    "oda passthrough olarak görünüyor."
                ),
                reasoning=(
                    "Ortam hazır: sınır aktif, passthrough açık, merkez "
                    "sıfır. Artık uygulamayı başlatıp MR modunda doğup "
                    "doğmadığına bakabilirim."
                ),
            ),
            AgenticStep(
                tool="quest_press_controller_button",
                args={"controller": "right", "button": "trigger"},
                result=(
                    "[sonuç] Sağ trigger basıldı; menüde 'Antrenmana Başla' "
                    "seçildi, ring sahnesi yüklendi."
                ),
                reasoning=(
                    "Menü passthrough üstünde geldi; asıl doğrulanacak sahne "
                    "antrenman ringi. İmleç zaten 'Antrenmana Başla' üzerinde, "
                    "sağ trigger ile seçiyorum."
                ),
            ),
            AgenticStep(
                tool="quest_screenshot",
                args={},
                result=(
                    "[sonuç] Görüntü alındı: ring ve dumbbell'ler sahnede, "
                    "arka planda oda passthrough olarak net görünüyor."
                ),
                reasoning=(
                    "Sahne yüklendi; iddia edilen davranış 'ring passthrough "
                    "üstünde'. Söze değil görüntüye güvenilir — ekran "
                    "görüntüsü kanıt olarak alınmalı."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Passthrough MR smoke testi geçti: sınır aktifken "
                        "FitBox passthrough üstünde açıldı, görüntü kanıtı "
                        "alındı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning=(
                    "Görüntü beklenen MR kompozisyonunu doğruladı; test "
                    "hedefine ulaştı, kapatıyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 2. VR/spatial (visionOS): simulator list -> boot -> launch ->
    #    find_text -> click_at -> logs -> screenshot verify
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="visionpro_new_board_flow",
        goal=(
            "[görev] visionOS simülatöründe Kanvas uygulamasının 'Yeni Pano' "
            "akışı doğrulanacak: panel açılmalı ve log'a BoardCreated "
            "düşmeli."
        ),
        steps=[
            AgenticStep(
                tool="visionpro_simulator_list",
                args={},
                result=(
                    "[sonuç] 1 simülatör: Apple Vision Pro (visionOS 2.4), "
                    "udid 4E2B77AC-9D1F-4C3A-B8E0-1A2B3C4D5E6F, durum: Shutdown."
                ),
                reasoning=(
                    "Hangi udid'nin var olduğunu ve açık olup olmadığını "
                    "bilmeden boot çağrısı körlemesine olur; önce listeyi "
                    "alıyorum."
                ),
            ),
            AgenticStep(
                tool="visionpro_simulator_boot",
                args={"udid": "4E2B77AC-9D1F-4C3A-B8E0-1A2B3C4D5E6F"},
                result="[sonuç] 4E2B77AC-9D1F-4C3A-B8E0-1A2B3C4D5E6F boot edildi; durum: Booted.",
                reasoning=(
                    "Liste tek simülatör gösterdi ve kapalıydı; testin ön "
                    "koşulu simülatörün açık olması, 4E2B77AC-9D1F-4C3A-B8E0-1A2B3C4D5E6F'yi boot "
                    "ediyorum."
                ),
            ),
            AgenticStep(
                tool="visionpro_app_launch",
                args={"bundle_id": "com.arketic.kanvas"},
                result=(
                    "[sonuç] com.arketic.kanvas başlatıldı (pid 4312); ana "
                    "pencere açıldı."
                ),
                reasoning=(
                    "Simülatör Booted; test edilen akış Kanvas içinde, "
                    "uygulamayı bundle id ile başlatıyorum."
                ),
            ),
            AgenticStep(
                tool="visionpro_find_text",
                args={"needle": "Yeni Pano"},
                result=(
                    "[sonuç] 'Yeni Pano' bulundu: 1 eşleşme, merkez "
                    "(612, 384)."
                ),
                reasoning=(
                    "Pencere açıldı ama düğmenin koordinatını tahmin etmek "
                    "kırılgan; ekranda 'Yeni Pano' metnini arayıp gerçek "
                    "konumunu alıyorum."
                ),
            ),
            AgenticStep(
                tool="visionpro_click_at",
                args={"x": 612, "y": 384},
                result=(
                    "[sonuç] (612, 384) tıklandı; 'Yeni Pano' paneli açıldı, "
                    "boş tuval görünüyor."
                ),
                reasoning=(
                    "find_text düğmeyi (612, 384) merkezinde verdi; akışı "
                    "tetiklemek için tam o noktaya tıklıyorum."
                ),
            ),
            AgenticStep(
                tool="visionpro_get_logs",
                args={
                    "predicate": 'subsystem == "com.arketic.kanvas"',
                    "last": "2m",
                },
                result=(
                    "[sonuç] Son 2 dk log: 'BoardCreated id=7' bilgi satırı "
                    "var; hata veya uyarı yok."
                ),
                reasoning=(
                    "Panel görsel olarak açıldı ama kabul ölçütü log'da "
                    "BoardCreated olayı; uygulamanın subsystem'ine "
                    "filtrelenmiş son 2 dakikayı çekiyorum."
                ),
            ),
            AgenticStep(
                tool="visionpro_screenshot",
                args={},
                result=(
                    "[sonuç] Görüntü alındı: boş pano tuvali ve 'Pano 7' "
                    "başlığı görünüyor."
                ),
                reasoning=(
                    "Log id=7 dedi; ekranın da aynı panoyu gösterdiğini "
                    "görüntüyle sabitlersem akış iki kanaldan doğrulanmış "
                    "olur ve iş biter."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 3. Desktop-heavy: iki uygulama arası otomasyon — not dosyasına yaz,
    #    kaydet, Slack'e bildir, ekran görüntüsüyle doğrula
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="desktop_ops_note_and_slack",
        goal=(
            "[görev] Gece staging yedeği alındı; operasyon not dosyasına "
            "kayıt düşülecek, sonra Slack #ops kanalına bildirilecek."
        ),
        steps=[
            AgenticStep(
                tool="desktop_list_windows",
                args={},
                result=(
                    "[sonuç] Açık pencereler: Notepad — 'operasyon-notlari"
                    ".txt', Slack — '#ops | Arketic', Chrome — 'Grafana'."
                ),
                reasoning=(
                    "İki farklı uygulamada işlem yapacağım; hangi pencereler "
                    "açık ve başlıkları ne, bilmeden odak atlamak yanlış "
                    "pencereye yazdırır."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={
                    "app_name": "Notepad",
                    "window_title": "operasyon-notlari.txt",
                },
                result="[sonuç] Notepad odaklandı; imleç dosya sonunda.",
                reasoning=(
                    "Liste doğru dosyanın Notepad'de açık olduğunu gösterdi; "
                    "ilk iş not dosyası, odağı oraya alıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_type",
                args={
                    "text": (
                        "2026-07-03 02:00 — staging yedeği alındı; "
                        "doğrulama: OK, boyut 4.2 GB."
                    ),
                },
                result="[sonuç] Satır dosya sonuna yazıldı.",
                reasoning=(
                    "Odak Notepad'de ve imleç sonda; kayıt satırını doğrudan "
                    "yazabilirim."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "ctrl+s"},
                result=(
                    "[sonuç] Kaydedildi; başlıktaki değişiklik yıldızı "
                    "kayboldu."
                ),
                reasoning=(
                    "Yazılan satır henüz diskte değil; Slack'e geçmeden "
                    "kaydetmezsem odak değişince kayıt yarım kalabilir."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={"app_name": "Slack"},
                result=(
                    "[sonuç] Slack odaklandı; #ops kanalı açık, mesaj kutusu "
                    "boş."
                ),
                reasoning=(
                    "Not diske işlendi; ikinci uygulama Slack'e geçip aynı "
                    "bilgiyi ekibe duyuracağım."
                ),
            ),
            AgenticStep(
                tool="desktop_type",
                args={
                    "text": (
                        "Staging yedeği 02:00'da alındı (4.2 GB, doğrulama "
                        "OK); operasyon-notlari.txt güncellendi."
                    ),
                },
                result="[sonuç] Mesaj kutusuna yazıldı, gönderilmedi.",
                reasoning=(
                    "Odak #ops mesaj kutusunda; duyuru metnini not dosyasına "
                    "yazdığım kayıtla tutarlı şekilde giriyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "enter"},
                result="[sonuç] Mesaj #ops kanalına gönderildi.",
                reasoning=(
                    "Metin kutuda duruyor; Slack'te göndermek enter ister, "
                    "yazmak yetmez."
                ),
            ),
            AgenticStep(
                tool="desktop_screenshot",
                args={},
                result=(
                    "[sonuç] Görüntü alındı: #ops kanalında yedek mesajı en "
                    "altta görünüyor."
                ),
                reasoning=(
                    "İki uygulamada da işlem yaptım; mesajın gerçekten "
                    "kanala düştüğünü ekran görüntüsüyle doğrulayıp işi "
                    "kapatıyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 4. Mind-heavy: session_state -> mind_recall -> pano + issue işi ->
    #    mind_note_add -> doluluk artınca compact
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="mind_resume_notify_migration",
        goal=(
            "[görev] Dün yarım kalan 'bildirim servisi taşıma' işine devam "
            "edilecek; taşımanın hangi teknolojiyle yapılacağına dün karar "
            "verilmişti ama bu oturumda yok."
        ),
        steps=[
            AgenticStep(
                tool="session_state",
                args={},
                result=(
                    "[sonuç] Bağlam %87 dolu; dünkü test logları birikmiş. "
                    "Aktif görev: bildirim servisi taşıma, kart kb-44."
                ),
                reasoning=(
                    "Uzun bir işe girmeden önce pencerenin ne durumda "
                    "olduğunu ölçmek gerek; %87 doluluk sınırda, ne zaman "
                    "compact gerekeceğini buradan izleyeceğim."
                ),
            ),
            AgenticStep(
                tool="mind_recall",
                args={"query": "bildirim servisi taşıma kararı", "top_k": 3},
                result=(
                    "[sonuç] 1 not: 'Karar: bildirimler RabbitMQ değil Redis "
                    "Streams'e taşınacak; mesaj TTL 24 saat.'"
                ),
                reasoning=(
                    "Teknoloji kararı bu pencerede yok; tahmin etmek ya da "
                    "operatöre yeniden sormak yerine dünkü kararı hafızadan "
                    "geri çağırıyorum."
                ),
            ),
            AgenticStep(
                tool="kanban_card_move",
                args={"card_id": "kb-44", "to_column": "in_progress"},
                result="[sonuç] kb-44 in_progress sütununa taşındı.",
                reasoning=(
                    "Karar netleşti (Redis Streams, TTL 24h); işe fiilen "
                    "başlıyorum, pano akışında ilk adım kartı in_progress'e "
                    "çekmek."
                ),
            ),
            AgenticStep(
                tool="github_issue_comment",
                args={
                    "repo": "arketic/notify-service",
                    "number": 12,
                    "body": (
                        "Taşıma Redis Streams ile ilerliyor (dünkü karar; "
                        "RabbitMQ elendi). Mesaj TTL 24 saat. Bugün consumer "
                        "tarafı bağlanacak; kart: kb-44."
                    ),
                },
                result="[sonuç] #12'ye yorum eklendi.",
                reasoning=(
                    "Kart taşındı ama ekip kararı issue üzerinden izliyor; "
                    "recall'dan gelen kararı #12'ye yazmak herkesi aynı "
                    "hizaya getirir."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Karar: Redis Streams consumer group adı "
                        "'notify-workers'; her pod kendi pod adını consumer "
                        "adı olarak kullanacak."
                    ),
                    "kind": "decision",
                    "importance": 7,
                },
                result="[sonuç] Not kaydedildi (kind=decision).",
                reasoning=(
                    "Yorumu yazarken consumer group adlandırmasına karar "
                    "verdim; bu karar pencere dolunca kaybolmamalı, hemen "
                    "hafızaya işliyorum."
                ),
            ),
            AgenticStep(
                tool="session_state",
                args={},
                result=(
                    "[sonuç] Bağlam %94 dolu; issue gövdesi ve log blokları "
                    "eklenince eşik aşıldı."
                ),
                reasoning=(
                    "Başta %87'ydi ve o zamandan beri uzun içerik ürettim; "
                    "kod işine girmeden doluluğu yeniden ölçüyorum."
                ),
            ),
            AgenticStep(
                tool="compact_context",
                args={
                    "strategy": "summary",
                    "reason": (
                        "bağlam %94; dünkü test logları özetlenip consumer "
                        "implementasyonuna yer açılacak"
                    ),
                },
                result=(
                    "[sonuç] Bağlam %36'ya indi; karar notları ve kart "
                    "bağlamı korundu."
                ),
                reasoning=(
                    "%94 doluluk implementasyon sırasında taşma demek; "
                    "loglar özetlenebilir içerik, summary stratejisi kararı "
                    "atmadan sıkıştırır. Kritik kararlar zaten hafızada."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Devir tamam: karar geri çağrıldı, kb-44 "
                        "in_progress, #12 bilgilendirildi, yeni karar notta, "
                        "bağlam %36."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning=(
                    "Devam turunun hedefi bağlamı kurup işi başlatmaktı; "
                    "implementasyon sonraki tur, burada bitiriyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 5. CROSS: browser araştırma -> kanban kartı -> github issue
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="browser_sentry_v9_to_board_issue",
        goal=(
            "[görev] Sentry JS SDK'nın yeni major sürümünde kırıcı "
            "değişiklik söylentisi var; changelog'dan doğrulanacak, panoya "
            "ve fieldnote-app deposuna işlenecek."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={
                    "url": (
                        "https://github.com/getsentry/sentry-javascript/"
                        "releases"
                    ),
                },
                result="[sonuç] Releases sayfasına gidildi; sayfa yükleniyor.",
                reasoning=(
                    "Söylenti kaynak göstermiyor; birincil kaynak SDK'nın "
                    "kendi release sayfası, doğrulama oradan başlar."
                ),
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "networkidle"},
                result="[sonuç] Sayfa tamamen yüklendi; release listesi DOM'da.",
                reasoning=(
                    "GitHub release listesi geç dolan içerik; extract'ı ağ "
                    "sakinleşmeden çalıştırırsam yarım liste okurum."
                ),
            ),
            AgenticStep(
                tool="browser_extract",
                args={
                    "extraction_schema": {
                        "version": "en yeni sürümün adı",
                        "date": "yayın tarihi",
                        "breaking_changes": (
                            "Breaking Changes başlığı altındaki maddeler"
                        ),
                    },
                    "instruction": (
                        "En üstteki (en yeni) sürümün adını, tarihini ve "
                        "'Breaking Changes' başlığı altındaki maddeleri çıkar."
                    ),
                },
                result=(
                    "[sonuç] version: 9.0.0, date: 2026-06-28, "
                    "breaking_changes: ['beforeSend imzası değişti (hint "
                    "zorunlu)', 'Node 18 desteği kaldırıldı']."
                ),
                reasoning=(
                    "Sayfa hazır; serbest metin okumak yerine sürüm/tarih/"
                    "kırıcı maddeleri şemayla yapılandırılmış çekiyorum, "
                    "sonraki adımlar bu alanları aynen kullanacak."
                ),
            ),
            AgenticStep(
                tool="kanban_card_add",
                args={
                    "title": "Sentry SDK v9 kırıcı değişiklikleri",
                    "body": (
                        "v9.0.0 (2026-06-28): beforeSend imzası değişti "
                        "(hint zorunlu); Node 18 desteği kalktı. Upgrade "
                        "öncesi etki analizi gerekli."
                    ),
                    "column": "backlog",
                },
                result="[sonuç] Kart kb-61 backlog sütununa eklendi.",
                reasoning=(
                    "Söylenti doğrulandı ve iki somut kırıcı madde var; bu "
                    "bir iş kalemi, kaybolmaması için önce panoya backlog "
                    "kartı olarak giriyor."
                ),
            ),
            AgenticStep(
                tool="github_issue_create",
                args={
                    "repo": "arketic/fieldnote-app",
                    "title": "chore: Sentry SDK v9 kırıcı değişiklikleri",
                    "body": (
                        "v9.0.0 (2026-06-28) iki kırıcı değişiklik getiriyor: "
                        "1) beforeSend imzası değişti, hint parametresi "
                        "zorunlu — sentry.ts'teki hook güncellenmeli. 2) Node "
                        "18 desteği kalktı — CI matrisinden 18 düşürülmeli. "
                        "Kaynak: sentry-javascript releases. Pano kartı: "
                        "kb-61."
                    ),
                    "labels": ["dependencies"],
                },
                result="[sonuç] Issue #73 açıldı.",
                reasoning=(
                    "Kart ekip panosunda ama kod işi depoda izleniyor; "
                    "extract'tan gelen maddeleri dosya/CI etkisiyle birlikte "
                    "issue'ya yazıyorum."
                ),
            ),
            AgenticStep(
                tool="kanban_card_update",
                args={
                    "card_id": "kb-61",
                    "body": (
                        "v9.0.0 (2026-06-28): beforeSend imzası değişti "
                        "(hint zorunlu); Node 18 desteği kalktı. İzleme: "
                        "arketic/fieldnote-app#73."
                    ),
                },
                result="[sonuç] kb-61 gövdesi issue bağlantısıyla güncellendi.",
                reasoning=(
                    "Issue #73 doğdu; kart ile issue birbirine bağlanmazsa "
                    "iki kayıt kopuk yaşar, kartın gövdesine #73'ü "
                    "işliyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Söylenti doğrulandı: v9.0.0 iki kırıcı madde; kb-61 "
                        "ve #73 birbirine bağlı şekilde açıldı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning=(
                    "Araştırma-kayıt turu tamamlandı; upgrade işinin kendisi "
                    "kartın sahibine ait, burada bitiriyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 6. CROSS: android repro -> crash triage -> github issue -> mind note
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="android_camera_crash_to_issue",
        goal=(
            "[görev] Kullanıcılar fieldnote Android'de 'Fotoğraf ekle'ye "
            "dokununca uygulamanın kapandığını bildiriyor; emülatörde repro "
            "edilip kök neden bulunacak ve depoya rapor edilecek."
        ),
        steps=[
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.arketic.fieldnote"},
                result=(
                    "[sonuç] com.arketic.fieldnote açıldı; not listesi "
                    "ekranı geldi."
                ),
                reasoning=(
                    "Şikayet belirli bir dokunuşta çökme; triage repro ile "
                    "başlar, önce uygulamayı emülatörde açıyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 540, "y": 1730},
                result=(
                    "[sonuç] 'Fotoğraf ekle' düğmesine dokunuldu; uygulama "
                    "anında kapandı ('fieldnote durduruldu')."
                ),
                reasoning=(
                    "Bildirilen adım tam olarak bu düğme; alt bar merkezinde "
                    "(540, 1730). Çökme dokunuşla tetikleniyorsa burada "
                    "görmeliyim."
                ),
            ),
            AgenticStep(
                tool="android_logcat",
                args={"tag_filter": "AndroidRuntime", "max_lines": 80},
                result=(
                    "[sonuç] FATAL EXCEPTION: main — NullPointerException: "
                    "CameraProvider.bind() null döndü, "
                    "PhotoPicker.kt:112'de."
                ),
                reasoning=(
                    "Repro tuttu; çökme anındaki stack trace'i görmem gerek, "
                    "AndroidRuntime etiketi fatal exception'ları verir."
                ),
            ),
            AgenticStep(
                tool="crash_log_fetch",
                args={"max_lines": 120},
                result=(
                    "[sonuç] Aynı stack; 3 satır öncesinde uyarı: 'CameraX: "
                    "no available camera on device'. Emülatörde arka kamera "
                    "tanımlı değil."
                ),
                reasoning=(
                    "Stack NPE gösteriyor ama neden bind null döndü belli "
                    "değil; çökme öncesi satırları da içeren daha geniş "
                    "crash log'u çekip tetikleyiciyi arıyorum."
                ),
            ),
            AgenticStep(
                tool="crash_bug_report",
                args={
                    "output_path": "artifacts/fieldnote-camera-crash.zip",
                },
                result=(
                    "[sonuç] Hata raporu paketlendi: "
                    "artifacts/fieldnote-camera-crash.zip (2.1 MB)."
                ),
                reasoning=(
                    "Kök neden netleşti: kamerasız cihazda CameraProvider "
                    "null. Issue'ya söz değil kanıt eklemek için tam hata "
                    "raporunu arşivliyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_create",
                args={
                    "repo": "arketic/fieldnote-app",
                    "title": (
                        "fix: kamerasız cihazda 'Fotoğraf ekle' çökmesi "
                        "(NPE, PhotoPicker.kt:112)"
                    ),
                    "body": (
                        "Repro: kamerası olmayan cihazda/emülatörde 'Fotoğraf "
                        "ekle'ye dokun -> anında çökme. Kök neden: "
                        "CameraProvider.bind() kamera yokken null dönüyor, "
                        "PhotoPicker.kt:112 null kontrolsüz. Öncesinde "
                        "'CameraX: no available camera' uyarısı düşüyor. "
                        "Tam rapor: artifacts/fieldnote-camera-crash.zip."
                    ),
                    "labels": ["bug", "crash"],
                },
                result="[sonuç] Issue #74 açıldı.",
                reasoning=(
                    "Repro adımı, kök neden ve kanıt paketi elimde; üçünü "
                    "tek issue'da birleştirip depoya rapor ediyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Kök neden kalıbı: CameraProvider.bind() kamerasız "
                        "cihazda null döner; CameraX kullanan her akışta "
                        "önce kamera varlığı kontrol edilmeli. Örnek: "
                        "fieldnote #74."
                    ),
                    "kind": "pattern",
                    "importance": 7,
                },
                result="[sonuç] Not kaydedildi (kind=pattern).",
                reasoning=(
                    "Bu kök neden fieldnote'a özgü değil, CameraX kullanan "
                    "her projede tekrar eder; kalıp olarak hafızaya "
                    "işlersem bir dahaki triage saatler değil dakikalar "
                    "sürer."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Çökme repro edildi, kök neden bulundu (kamerasız "
                        "cihazda null bind), #74 kanıtla açıldı, kalıp nota "
                        "işlendi."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning=(
                    "Triage turunun tüm çıktıları üretildi; düzeltme "
                    "issue'nun sahibine ait, kapatıyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 7. CROSS: ui_verify başarısız -> screenshot kanıtı ->
    #    github_issue_comment -> kart geri in_progress'e
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="ui_verify_fail_reopen_quota_badge",
        goal=(
            "[görev] Issue #66'daki 'kota rozeti üst bardan taşıyor' "
            "düzeltmesi staging'e çıktı; panelde doğrulanacak, geçmezse "
            "kanıtla issue'ya yazılacak (kart kb-58 review'da)."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={"url": "https://staging.fieldnote.app/panel"},
                result="[sonuç] Panel yüklendi; üst bar ve rozet görünümde.",
                reasoning=(
                    "Doğrulama iddia edilen düzeltmenin çalıştığı ortamda "
                    "yapılmalı; staging panel sayfasını açıyorum."
                ),
            ),
            AgenticStep(
                tool="ui_verify_text_visible",
                args={"text": "Kota: %62"},
                result=(
                    "[sonuç] BAŞARISIZ: 'Kota: %62' tam görünür değil; "
                    "elementin sağ kenarı viewport dışında."
                ),
                reasoning=(
                    "Kabul ölçütü rozetin metniyle birlikte tam görünmesi; "
                    "önce metin görünürlüğünü nesnel olarak kontrol "
                    "ediyorum, göz kararı yetmez."
                ),
            ),
            AgenticStep(
                tool="ui_verify_no_overflow",
                args={},
                result=(
                    "[sonuç] BAŞARISIZ: .top-bar içinde 34px yatay taşma; "
                    "taşan element .quota-badge."
                ),
                reasoning=(
                    "Metin kontrolü düştü; taşmanın hâlâ yapısal olduğunu "
                    "ayrı bir kontrolle teyit edersem 'font yüklenmedi' gibi "
                    "alternatif açıklamalar elenir."
                ),
            ),
            AgenticStep(
                tool="browser_screenshot",
                args={},
                result=(
                    "[sonuç] Görüntü alındı: rozet sağdan kırpılmış, yüzde "
                    "değeri yarım görünüyor."
                ),
                reasoning=(
                    "İki kontrol de başarısız; issue'ya yazacağım yorumun "
                    "tartışılmaz olması için görsel kanıt alıyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_comment",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 66,
                    "body": (
                        "Staging doğrulaması BAŞARISIZ: .quota-badge hâlâ "
                        ".top-bar'dan 34px taşıyor, 'Kota: %62' metni sağdan "
                        "kırpık (ekran görüntüsü ekli). Düzeltme viewport "
                        ">=1280px'te denenmiş olabilir; taşma 1080px'te "
                        "sürüyor."
                    ),
                },
                result="[sonuç] #66'ya yorum ve görüntü eklendi.",
                reasoning=(
                    "Kanıt tamam: iki nesnel kontrol + görüntü. Bulguyu "
                    "ölçümleriyle (34px, 1080px) issue'ya yazıyorum ki "
                    "geliştirici tahmin ederek değil hedefe çalışsın."
                ),
            ),
            AgenticStep(
                tool="kanban_card_move",
                args={"card_id": "kb-58", "to_column": "in_progress"},
                result="[sonuç] kb-58 review'dan in_progress'e taşındı.",
                reasoning=(
                    "Doğrulama düştü; kartın review'da kalması yanıltıcı, "
                    "işin sahibine döndüğünü pano da göstermeli."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Doğrulama turu bitti: düzeltme geçmedi, #66'ya "
                        "ölçülü kanıt yazıldı, kb-58 geri in_progress'te."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning=(
                    "Benim işim doğrulamak ve sonucu kayda geçirmekti; "
                    "yeniden düzeltme ayrı tur, kapatıyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 8. CROSS (VR -> GitHub -> Mind): Quest'te grip hatası — video kanıtı
    #    kaydet, log al, issue aç, kalıbı nota işle
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="quest_grip_release_bug_report",
        goal=(
            "[görev] FitBox oyuncuları grip'e ikinci kez basınca dumbbell'in "
            "bırakılmadığını bildiriyor; Quest'te repro edilip video ve "
            "log'la fitbox-vr deposuna rapor edilecek."
        ),
        steps=[
            AgenticStep(
                tool="quest_app_launch",
                args={"package": "com.fitbox.vr"},
                result=(
                    "[sonuç] FitBox açıldı; antrenman sahnesi ve dumbbell "
                    "rafı görünüyor."
                ),
                reasoning=(
                    "Şikayet uygulama içi etkileşimde; repro için önce "
                    "FitBox'ı cihazda başlatıyorum."
                ),
            ),
            AgenticStep(
                tool="quest_record_video",
                args={
                    "output_path": "artifacts/fitbox-grip-bug.mp4",
                    "time_limit_sec": 60,
                },
                result="[sonuç] Video kaydı başladı (limit 60 sn).",
                reasoning=(
                    "VR etkileşim hatası ekran görüntüsüyle anlatılamaz; "
                    "repro adımlarını denemeden ÖNCE kaydı açıyorum ki "
                    "hatanın oluşma anı videoda olsun."
                ),
            ),
            AgenticStep(
                tool="quest_press_controller_button",
                args={"controller": "right", "button": "grip"},
                result=(
                    "[sonuç] Grip basıldı; dumbbell sağ ele tutundu "
                    "(GrabState: HOLDING)."
                ),
                reasoning=(
                    "Kayıt dönüyor; bildirilen akışın ilk yarısı nesneyi "
                    "grip ile tutmak, aynı adımı uyguluyorum."
                ),
            ),
            AgenticStep(
                tool="quest_press_controller_button",
                args={"controller": "right", "button": "grip"},
                result=(
                    "[sonuç] Grip'e ikinci kez basıldı; dumbbell BIRAKILMADI, "
                    "elde asılı kaldı."
                ),
                reasoning=(
                    "Nesne tutuldu; şikayete göre ikinci grip bırakmalı ama "
                    "bırakmıyor. Aynı düğmeye ikinci basışla hatayı "
                    "tetiklemeyi deniyorum."
                ),
            ),
            AgenticStep(
                tool="quest_stop_record_video",
                args={},
                result=(
                    "[sonuç] Kayıt durdu; artifacts/fitbox-grip-bug.mp4 "
                    "kaydedildi (18 sn)."
                ),
                reasoning=(
                    "Hata videoya girdi; kaydı uzatmanın anlamı yok, dosyayı "
                    "kapatıp kanıt olarak sabitliyorum."
                ),
            ),
            AgenticStep(
                tool="quest_logcat",
                args={"tag_filter": "FitBox", "max_lines": 60},
                result=(
                    "[sonuç] Log: 'GrabState: release ignored, "
                    "state=HOLDING, debounce=active' — ikinci basış debounce "
                    "penceresine takılıyor."
                ),
                reasoning=(
                    "Video davranışı gösteriyor ama nedenini göstermiyor; "
                    "uygulamanın kendi etiketiyle log çekip release'in neden "
                    "yutulduğuna bakıyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_create",
                args={
                    "repo": "arketic/fitbox-vr",
                    "title": (
                        "fix: grip'e ikinci basış nesneyi bırakmıyor "
                        "(debounce release'i yutuyor)"
                    ),
                    "body": (
                        "Repro: dumbbell'i grip ile tut, grip'e tekrar bas "
                        "-> nesne bırakılmıyor. Log: 'GrabState: release "
                        "ignored, state=HOLDING, debounce=active'. Debounce "
                        "penceresi tutma sonrası release girişini de "
                        "yutuyor. Video: artifacts/fitbox-grip-bug.mp4."
                    ),
                    "labels": ["bug", "vr"],
                },
                result="[sonuç] Issue #19 açıldı.",
                reasoning=(
                    "Repro, log'daki kök neden ve video kanıtı tamam; hepsini "
                    "tek issue'da fitbox-vr deposuna raporluyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "VR etkileşim kalıbı: grab/release aynı düğmedeyse "
                        "debounce penceresi release'i yutabilir; toggle "
                        "girişlerinde debounce state'e göre ayrılmalı. "
                        "Örnek: fitbox-vr #19."
                    ),
                    "kind": "pattern",
                    "importance": 6,
                },
                result="[sonuç] Not kaydedildi (kind=pattern).",
                reasoning=(
                    "Aynı-düğme toggle + debounce tuzağı FitBox'a özgü "
                    "değil; kalıbı nota işlersem sonraki VR triage'ında "
                    "doğrudan buradan başlarım."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 9. Mind -> Desktop: karar hafızadan, uygulama masaüstünde
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="mind_recall_invoice_entry",
        goal=(
            "[görev] Haziran danışmanlık faturası muhasebe uygulamasına "
            "girilecek; açıklama alanının formatı geçen ay operatörle "
            "kararlaştırılmıştı."
        ),
        steps=[
            AgenticStep(
                tool="session_state",
                args={},
                result=(
                    "[sonuç] Bağlam %41 dolu, sorun yok; ancak fatura format "
                    "kararı bu oturumun geçmişinde yer almıyor."
                ),
                reasoning=(
                    "Kısa bir iş ama kritik bilgisi (format kuralı) bu "
                    "pencerede olmayabilir; önce oturumun neyi içerdiğini "
                    "görüyorum."
                ),
            ),
            AgenticStep(
                tool="mind_recall",
                args={"query": "fatura açıklama formatı kararı"},
                result=(
                    "[sonuç] 1 not: 'Karar: fatura açıklaması AY-YYYY / "
                    "müşteri / hizmet formatında girilecek.'"
                ),
                reasoning=(
                    "Format bu pencerede yok; uydurmak ya da operatöre "
                    "yeniden sormak yerine geçen ayki kararı hafızadan "
                    "çağırıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_list_windows",
                args={"app_name": "Muhasebe"},
                result=(
                    "[sonuç] 1 pencere: 'Muhasebe — Fatura Girişi', durum: "
                    "arka planda."
                ),
                reasoning=(
                    "Format elimde (AY-YYYY / müşteri / hizmet); girişin "
                    "yapılacağı Muhasebe penceresinin açık olup olmadığına "
                    "bakıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={"app_name": "Muhasebe"},
                result=(
                    "[sonuç] Muhasebe odaklandı; imleç 'Açıklama' alanında."
                ),
                reasoning=(
                    "Fatura Girişi ekranı zaten açık; yazmadan önce odağı "
                    "oraya almam gerekiyor."
                ),
            ),
            AgenticStep(
                tool="desktop_type",
                args={"text": "06-2026 / Arketic / danışmanlık"},
                result="[sonuç] Açıklama alanına yazıldı.",
                reasoning=(
                    "İmleç doğru alanda; recall'dan gelen kurala birebir "
                    "uyan açıklamayı giriyorum — ay-yıl, müşteri, hizmet."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "ctrl+s"},
                result=(
                    "[sonuç] Fatura kaydedildi; bildirim: 'F-1042 "
                    "oluşturuldu'."
                ),
                reasoning=(
                    "Alan doldu ama kayıt diske işlenmedi; uygulamanın "
                    "kaydet kısayoluyla girişi kalıcılaştırıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_screenshot",
                args={},
                result=(
                    "[sonuç] Görüntü alındı: fatura listesinde F-1042, "
                    "açıklama '06-2026 / Arketic / danışmanlık'."
                ),
                reasoning=(
                    "Bildirim çıktı ama listede doğru açıklamayla durduğunu "
                    "görmek asıl doğrulama; görüntüyle sabitliyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "F-1042 karar formatına uygun girildi ve görüntüyle "
                        "doğrulandı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning=(
                    "Giriş yapıldı, format karara uygun, kanıt alındı; iş "
                    "tamam."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 10. CROSS: issue -> android doğrulama -> ui_verify -> issue kapat ->
    #     kart done
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="android_darkmode_verify_close",
        goal=(
            "[görev] Issue #70'teki karanlık mod kontrast düzeltmesi main'e "
            "girdi; cihazda doğrulanacak, geçerse issue kapatılıp kart kb-72 "
            "bitirilecek."
        ),
        steps=[
            AgenticStep(
                tool="github_issue_view",
                args={"repo": "arketic/fieldnote-app", "number": 70},
                result=(
                    "[sonuç] #70: düzeltme commit'i main'de; son yorum "
                    "'cihaz doğrulaması bekleniyor'. Kabul ölçütü: karanlık "
                    "modda ayar metinleri okunur olmalı."
                ),
                reasoning=(
                    "Neyi doğrulayacağımı ve kabul ölçütünü issue'dan teyit "
                    "etmeden cihaza gitmek körlemesine olur; önce #70'i "
                    "okuyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.arketic.fieldnote"},
                result=(
                    "[sonuç] fieldnote (main build 2.4.0-rc3) açıldı; "
                    "Ayarlar ekranı erişilebilir."
                ),
                reasoning=(
                    "Ölçüt karanlık moddaki ayar ekranı; düzeltmeyi içeren "
                    "build'i cihazda başlatıyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 972, "y": 344},
                result=(
                    "[sonuç] 'Karanlık mod' anahtarına dokunuldu; tema "
                    "koyuya geçti."
                ),
                reasoning=(
                    "Doğrulama karanlık modda yapılmalı; Ayarlar'daki "
                    "anahtar (972, 344) konumunda, dokunup temayı "
                    "değiştiriyorum."
                ),
            ),
            AgenticStep(
                tool="ui_verify_ocr_contains",
                args={"text": "Karanlık mod: Açık"},
                result=(
                    "[sonuç] BAŞARILI: 'Karanlık mod: Açık' OCR ile okundu; "
                    "metin koyu zeminde seçilebilir."
                ),
                reasoning=(
                    "Kontrast şikayeti 'metin okunamıyor' idi; OCR koyu "
                    "zemindeki metni okuyabiliyorsa kontrast insan gözü için "
                    "de yeterli — nesnel bir geçme ölçütü."
                ),
            ),
            AgenticStep(
                tool="android_screenshot",
                args={},
                result=(
                    "[sonuç] Görüntü alındı: karanlık ayar ekranı, tüm "
                    "etiketler net okunuyor."
                ),
                reasoning=(
                    "OCR geçti; issue'yu kapatırken 'geçti' demek yetmez, "
                    "kapanışa görsel kanıt iliştirmek için görüntü "
                    "alıyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_comment",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 70,
                    "body": (
                        "Cihaz doğrulaması BAŞARILI (2.4.0-rc3): karanlık "
                        "modda 'Karanlık mod: Açık' ve tüm ayar etiketleri "
                        "OCR ile okunuyor; ekran görüntüsü ekli. Kapatıyorum."
                    ),
                },
                result="[sonuç] #70'e doğrulama yorumu eklendi.",
                reasoning=(
                    "Kanıt elimde; kapatmadan önce doğrulamanın nasıl "
                    "yapıldığını yoruma yazıyorum ki kapanış izlenebilir "
                    "olsun."
                ),
            ),
            AgenticStep(
                tool="github_issue_close",
                args={"repo": "arketic/fieldnote-app", "number": 70},
                result="[sonuç] #70 kapatıldı.",
                reasoning=(
                    "Kabul ölçütü sağlandı ve kanıt yorumda; issue'nun açık "
                    "kalması için neden kalmadı."
                ),
            ),
            AgenticStep(
                tool="kanban_card_done",
                args={"card_id": "kb-72"},
                result="[sonuç] kb-72 done sütununa taşındı.",
                reasoning=(
                    "Issue kapandı; kartı done'a çekmezsem pano ile depo "
                    "çelişir, akışın son adımı kartı bitirmek."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 11. CROSS: browser'dan bilgi -> mind notu -> desktop'ta duyuru
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="browser_status_to_desktop_announce",
        goal=(
            "[görev] Status sayfasındaki planlı Postgres bakım penceresi "
            "hafızaya işlenecek ve masaüstündeki DuyuruPano uygulamasından "
            "ekibe duyurulacak."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={"url": "https://status.arketic.dev"},
                result=(
                    "[sonuç] Status sayfası yüklendi; üstte bakım banner'ı "
                    "görünüyor."
                ),
                reasoning=(
                    "Duyurunun kaynağı status sayfasındaki resmi banner; "
                    "metni oradan almak için sayfayı açıyorum."
                ),
            ),
            AgenticStep(
                tool="browser_text_content",
                args={"target": ".maintenance-banner"},
                result=(
                    "[sonuç] 'Planlı bakım: 5 Temmuz 02:00-04:00 UTC — "
                    "Postgres 17 yükseltmesi. Kısa kesintiler olabilir.'"
                ),
                reasoning=(
                    "Banner göründü; tarih ve saat aralığını yorumsuz, "
                    "birebir almak için elementin metnini çekiyorum — "
                    "duyuruda saat hatası kabul edilemez."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "5 Temmuz 02:00-04:00 UTC planlı Postgres 17 bakımı; "
                        "bu aralıkta deploy ve migration planlanmamalı."
                    ),
                    "kind": "event",
                    "importance": 6,
                },
                result="[sonuç] Not kaydedildi (kind=event).",
                reasoning=(
                    "Bakım penceresi ileriki oturumlardaki deploy "
                    "kararlarını etkiler; duyuruyu yapmadan önce bilgiyi "
                    "pencereden bağımsız hale getiriyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_set_clipboard",
                args={
                    "text": (
                        "Planlı bakım: 5 Temmuz 02:00-04:00 UTC — Postgres "
                        "17 yükseltmesi. Kısa kesintiler olabilir; bu "
                        "aralıkta deploy planlamayın."
                    ),
                },
                result="[sonuç] Metin panoya kopyalandı.",
                reasoning=(
                    "Duyuru metni uzun ve tarih içeriyor; karakter karakter "
                    "yazmak yerine panoya koyup tek hamlede yapıştırmak "
                    "yazım hatası riskini sıfırlar."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={"app_name": "DuyuruPano"},
                result=(
                    "[sonuç] DuyuruPano odaklandı; 'Yeni duyuru' metin alanı "
                    "boş ve imleç içinde."
                ),
                reasoning=(
                    "Metin panoda hazır; yapıştırmadan önce hedef "
                    "uygulamanın odakta olması şart."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "ctrl+v"},
                result="[sonuç] Duyuru metni alana yapıştırıldı.",
                reasoning=(
                    "Odak doğru alanda; panodaki metni yapıştırıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "ctrl+enter"},
                result=(
                    "[sonuç] Duyuru yayınlandı; listede en üstte görünüyor."
                ),
                reasoning=(
                    "Metin alanda duruyor ama yayımlanmadı; DuyuruPano'da "
                    "gönderim ctrl+enter ile yapılıyor."
                ),
            ),
            AgenticStep(
                tool="desktop_screenshot",
                args={},
                result=(
                    "[sonuç] Görüntü alındı: duyuru listesinin başında bakım "
                    "duyurusu, tarih ve saatler doğru."
                ),
                reasoning=(
                    "Yayın onayı listede göründü; tarih/saatin bozulmadan "
                    "çıktığını görüntüyle doğrulayıp işi bitiriyorum."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 12. CROSS: crash-state snapshot/diff kanıtıyla regresyon yorumu
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="crash_diff_login_regression",
        goal=(
            "[görev] v2.4.1'in issue #58'deki giriş çökmesini çözdüğü iddia "
            "ediliyor; cihazda önce/sonra durum kaydıyla doğrulanacak, "
            "sonuç kanıtıyla issue'ya yazılacak."
        ),
        steps=[
            AgenticStep(
                tool="crash_state_snapshot",
                args={"label": "pre-login-v241", "include_logs": True},
                result=(
                    "[sonuç] 'pre-login-v241' anlık durumu kaydedildi "
                    "(loglar dahil)."
                ),
                reasoning=(
                    "Doğrulamanın kanıtı önce/sonra karşılaştırması olacak; "
                    "giriş denemesinden ÖNCE temiz bir durum kaydı almazsam "
                    "diff'in tabanı olmaz."
                ),
            ),
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.arketic.fieldnote"},
                result="[sonuç] fieldnote v2.4.1 açıldı; giriş ekranı geldi.",
                reasoning=(
                    "Taban kaydı alındı; iddia edilen düzeltmeyi içeren "
                    "v2.4.1'i başlatıp #58'deki repro adımına gidiyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 540, "y": 1418},
                result=(
                    "[sonuç] 'Giriş yap' dokunuldu; uygulama 2 sn dondu ve "
                    "kapandı — çökme sürüyor."
                ),
                reasoning=(
                    "#58'in reprosu giriş düğmesine dokunmak; düzeltme "
                    "gerçekse uygulama ana ekrana geçmeli."
                ),
            ),
            AgenticStep(
                tool="crash_state_snapshot",
                args={"label": "post-login-v241", "include_logs": True},
                result=(
                    "[sonuç] 'post-login-v241' kaydedildi; yeni crash "
                    "kayıtları içeriyor."
                ),
                reasoning=(
                    "Çökme yeniden oluştu; diff alabilmek için çökme "
                    "SONRASI durumu da aynı biçimde kaydediyorum."
                ),
            ),
            AgenticStep(
                tool="crash_state_diff",
                args={
                    "label_a": "pre-login-v241",
                    "label_b": "post-login-v241",
                },
                result=(
                    "[sonuç] Fark: 1 yeni FATAL — 'TokenStore migration "
                    "failed: column refresh_token missing'. Eski NPE stack'i "
                    "yok; çökme noktası değişmiş."
                ),
                reasoning=(
                    "İki kayıt hazır; diff, çökmenin eski hatanın devamı mı "
                    "yoksa yeni bir kök neden mi olduğunu tek bakışta "
                    "gösterir."
                ),
            ),
            AgenticStep(
                tool="github_issue_comment",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 58,
                    "body": (
                        "v2.4.1 doğrulaması: giriş hâlâ çöküyor ama kök "
                        "neden değişmiş. Önce/sonra durum diff'ine göre eski "
                        "NPE gitmiş; yeni FATAL: 'TokenStore migration "
                        "failed: column refresh_token missing'. Orijinal "
                        "düzeltme çalışıyor, ancak migration eski kurulumdan "
                        "yükseltmede refresh_token kolonunu eklemiyor."
                    ),
                },
                result="[sonuç] #58'e diff kanıtlı yorum eklendi.",
                reasoning=(
                    "Diff net bir hikaye anlatıyor: düzeltme kısmen işe "
                    "yaramış, çökme artık migration'dan. Bunu ayrıştırılmış "
                    "haliyle issue'ya yazmak yanlış 'düzeltme işe yaramadı' "
                    "sonucunu engeller."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "fieldnote #58: v2.4.1'de giriş çökmesinin kök "
                        "nedeni değişti — TokenStore migration eski "
                        "kurulumda refresh_token kolonunu eklemiyor. "
                        "Yükseltme yolu testleri temiz kurulumla "
                        "yakalanamaz."
                    ),
                    "kind": "insight",
                    "importance": 7,
                },
                result="[sonuç] Not kaydedildi (kind=insight).",
                reasoning=(
                    "'Aynı belirti, farklı kök neden' bulgusu ve yükseltme "
                    "yolu dersi bu pencere kapanınca kaybolmamalı; sonraki "
                    "turda buradan devam edilecek."
                ),
            ),
        ],
    ),
]

__all__ = ["TRAJECTORIES"]
