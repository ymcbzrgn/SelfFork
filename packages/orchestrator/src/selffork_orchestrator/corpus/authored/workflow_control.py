"""Authored reasoning scenarios for the workflow-control domain.

Expo dev loop + crash diagnostics + skills + UI verification + git/GitHub +
kanban + the orchestration/control meta-tools. Every scenario carries a
non-None ``reasoning`` because this domain is judgement-heavy: the small
model must learn WHICH of several confusable tools fits, and — hardest of
all — the meta decisions:

* discover-first: a needed capability is NOT in the visible tool list ->
  ``tool_search`` BEFORE any call, never a hallucinated tool name.
* ask-vs-act: a genuinely ambiguous / irreversible / taste-based request ->
  ``AskUserQuestion``, never a guessed destructive call.
* inform-vs-ask: ``notify_telegram`` pushes one-way info; it never blocks
  the loop waiting for a choice.
* evidence-before-switch: ``quota_snapshot`` before ``rotate_to``;
  ``session_state`` before ``set_cli_override``.

Each confusable cluster shows BOTH sides plus a trap case. All targets are
gated against the real registry by the builder.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

SCENARIOS: list[ToolScenario] = [
    # ------------------------------------------------------------------
    # Expo dev loop: dev_start vs metro_reload vs dev_stop;
    # doctor vs eas_build vs publish; run_android for native changes
    # ------------------------------------------------------------------
    ToolScenario(
        tool="expo_dev_start",
        archetype="cold_dev_server",
        context=(
            "[expo] fieldnote-mobile çalışma alanı; Metro süreci yok, 8081 "
            "portu boş. Operatör: 'Uygulamayı telefonda canlı görelim, "
            "geliştirme sunucusunu kaldır.'"
        ),
        args={"project_dir": "apps/fieldnote"},
        reasoning=(
            "Metro hiç çalışmıyor; expo_metro_reload çalışan bir sunucu "
            "ister. Önce sunucuyu ayağa kaldırmak gerek: expo_dev_start."
        ),
        index=0,
    ),
    ToolScenario(
        tool="expo_metro_reload",
        archetype="js_hot_reload",
        context=(
            "[expo] Metro 8081'de çalışıyor (PID 4412). Bir ekran "
            "başlığındaki metni düzelttim; operatör değişikliği cihazda "
            "hemen görmek istiyor."
        ),
        args={},
        reasoning=(
            "Sunucu zaten ayakta ve değişiklik salt JS; dev_stop+start "
            "gereksiz kesinti olur. Sıcak yenileme için metro_reload yeter."
        ),
        index=1,
    ),
    ToolScenario(
        tool="expo_dev_stop",
        archetype="dev_server_teardown",
        context=(
            "[expo] Cihaz testi bitti; Metro hâlâ arka planda çalışıyor ve "
            "8081 portunu tutuyor. Operatör: 'Geliştirme oturumunu kapat.'"
        ),
        args={},
        reasoning=(
            "İstenen sunucu sürecini durdurmak; metro_reload paketi yeniler "
            "ama süreci kapatmaz. Arka plandaki expo start'ı dev_stop bitirir."
        ),
        index=2,
    ),
    ToolScenario(
        tool="expo_doctor",
        archetype="diagnose_config_first",
        context=(
            "[expo] `eas build` iki kez üst üste 'incompatible peer "
            "dependency' hatasıyla düştü. Operatör nedenini soruyor."
        ),
        args={},
        reasoning=(
            "Aynı hatayla üçüncü kez bulut derlemesi başlatmak kota yakar; "
            "önce bağımlılık/yapılandırma teşhisi gerekir. Bu doğrulamayı "
            "expo_doctor yapar."
        ),
        index=3,
    ),
    ToolScenario(
        tool="expo_eas_build",
        archetype="store_binary_build",
        context=(
            "[expo] expo-doctor temiz çıktı. Operatör: 'TestFlight'a "
            "yükleyeceğimiz iOS binary'sini hazırla.'"
        ),
        args={"platform": "ios", "profile": "production"},
        reasoning=(
            "TestFlight ikili (ipa) ister; expo_export yalnız statik JS "
            "paketi üretir, publish OTA günceller. Mağaza ikilisini "
            "eas_build derler."
        ),
        index=4,
    ),
    ToolScenario(
        tool="expo_publish",
        archetype="ota_js_fix",
        context=(
            "[expo] Üretimdeki kullanıcılarda salt-JS bir çeviri hatası "
            "düzeltildi; native kod değişmedi. Operatör: 'Mağaza incelemesi "
            "beklemeden düzeltmeyi kullanıcılara ulaştır.'"
        ),
        args={"channel": "production"},
        reasoning=(
            "Değişiklik yalnız JS; yeni ikili (eas_build) ya da mağaza "
            "süreci gerekmez. OTA JS güncellemesini expo_publish kanala iter."
        ),
        index=5,
    ),
    # --- trap: native change -> hot reload CANNOT carry it ------------
    ToolScenario(
        tool="expo_run_android",
        archetype="native_change_rebuild",
        context=(
            "[expo] Projeye yeni bir native modül (vision-camera) eklendi. "
            "Operatör değişikliği Android cihazda görmek istiyor; Metro "
            "çalışıyor."
        ),
        args={},
        reasoning=(
            "Native modül JS paketiyle gelmez; metro_reload'un sıcak "
            "yenilemesi onu içeremez. Dev client yeniden derlenip "
            "kurulmalı: expo_run_android."
        ),
        index=6,
    ),
    # ------------------------------------------------------------------
    # Crash diagnostics: symptom -> tool; state snapshot family
    # ------------------------------------------------------------------
    ToolScenario(
        tool="crash_log_fetch",
        archetype="native_crash_logcat",
        context=(
            "[cihaz] Uygulama profildeki fotoğrafa dokununca aniden "
            "kapandı; ANR penceresi çıkmadı, doğrudan çöktü. Neden lazım."
        ),
        args={"max_lines": 400},
        reasoning=(
            "Ani kapanış izini logcat'e bırakır; uygulama donmadığı için "
            "ANR dosyası oluşmaz. Son cihaz günlükleri crash_log_fetch işi."
        ),
        index=7,
    ),
    # --- trap: RedBox is a Metro error, NOT a device log --------------
    ToolScenario(
        tool="expo_logs_capture",
        archetype="metro_red_screen",
        context=(
            "[expo] Cihazda kırmızı hata ekranı (RedBox): 'Unable to "
            "resolve module'. Metro çalışıyor. Operatör hatanın tamamını "
            "istiyor."
        ),
        args={"max_lines": 200},
        reasoning=(
            "RedBox bir JS paketleme hatası; kaynağı cihaz değil Metro. "
            "Logcat (crash_log_fetch) yerine Metro günlüğünü "
            "expo_logs_capture okur."
        ),
        index=8,
    ),
    ToolScenario(
        tool="crash_anr_dump",
        archetype="anr_trace_inventory",
        context=(
            "[cihaz] Dün geceki testte uygulama iki kez 'yanıt vermiyor' "
            "penceresi göstermiş. Sistemin o anlarda yazdığı izleri "
            "incelemek istiyorum."
        ),
        args={},
        reasoning=(
            "ANR anında sistem iz dosyası yazar; geçmiş donmaların kaydı "
            "orada. Bu dosyaları crash_anr_dump listeler; canlı "
            "thread_dump geçmişi göstermez."
        ),
        index=9,
    ),
    ToolScenario(
        tool="crash_thread_dump",
        archetype="live_deadlock_probe",
        context=(
            "[cihaz] Uygulama ŞU AN takılı: ekran donuk ama bellek "
            "kullanımı normal, ANR penceresi henüz çıkmadı. Hangi iş "
            "parçacığı kilitli görmek istiyorum."
        ),
        args={},
        reasoning=(
            "Sorun canlı ve bellekle ilgili değil; heap_dump bellek analizi "
            "içindir, anr_dump geçmiş izleri listeler. Anlık iş parçacığı "
            "durumunu crash_thread_dump verir."
        ),
        index=10,
    ),
    ToolScenario(
        tool="crash_heap_dump",
        archetype="memory_growth_dump",
        context=(
            "[cihaz] Her galeri ekranı açılışında uygulamanın belleği "
            "40 MB artıyor ve geri düşmüyor; OOM yaklaşıyor. Süreç "
            "PID 12734."
        ),
        args={
            "pid": 12734,
            "output_path": "~/.selffork/dumps/heap_gallery_12734.hprof",
        },
        reasoning=(
            "Belirti bellek sızıntısı; thread listesi ya da logcat sızan "
            "nesneleri göstermez. Nesne grafiği için crash_heap_dump ile "
            "hprof alınır."
        ),
        index=11,
    ),
    ToolScenario(
        tool="crash_bug_report",
        archetype="full_device_report",
        context=(
            "[cihaz] Hata aralıklı, yeniden üretilemiyor; geliştirici ekip "
            "'cihazdan alabildiğin her şeyi' istedi: sistem durumu, "
            "günlükler, izler."
        ),
        args={"output_path": "~/.selffork/reports/bugreport_20260703.zip"},
        reasoning=(
            "Tek bir günlük ya da iz yetmez; istenen kapsamlı paket. "
            "Sistem durumu+günlük+izleri tek arşivde crash_bug_report toplar."
        ),
        index=12,
    ),
    ToolScenario(
        tool="crash_state_snapshot",
        archetype="pre_risk_snapshot",
        context=(
            "[cihaz] Birazdan onboarding akışını sıfırlayan riskli bir "
            "deney yapılacak. Operatör: 'Önce şu anki ekran durumunu "
            "kaydet ki karşılaştırabilelim.'"
        ),
        args={
            "label": "onboarding-oncesi",
            "include_a11y": True,
            "include_logs": True,
        },
        reasoning=(
            "Riskli adımdan önce dönüş noktası isteniyor; restore ancak "
            "var olan kaydı yükler. Etiketli kaydı crash_state_snapshot alır."
        ),
        index=13,
    ),
    ToolScenario(
        tool="crash_state_restore",
        archetype="rollback_after_failure",
        context=(
            "[cihaz] Deney bozuk çıktı. crash_state_list az önce "
            "['onboarding-oncesi', 'temiz-kurulum'] döndürdü. Operatör: "
            "'Deney öncesine dön.'"
        ),
        args={"label": "onboarding-oncesi"},
        reasoning=(
            "Etiket listeyle doğrulandı; hedef yeni kayıt almak değil eski "
            "duruma dönmek. Kaydı crash_state_restore yükler, snapshot "
            "yenisini alırdı."
        ),
        index=14,
    ),
    ToolScenario(
        tool="crash_state_diff",
        archetype="before_after_ui_diff",
        context=(
            "[cihaz] 'onboarding-oncesi' ve 'onboarding-sonrasi' kayıtları "
            "mevcut. Operatör: 'Akış ekranda tam olarak neyi değiştirmiş, "
            "göster.'"
        ),
        args={"label_a": "onboarding-oncesi", "label_b": "onboarding-sonrasi"},
        reasoning=(
            "Soru iki kayıt arasındaki fark; restore duruma döner, diff "
            "a11y ağaçlarını karşılaştırıp yalnız değişen satırları verir."
        ),
        index=15,
    ),
    # ------------------------------------------------------------------
    # Skills: search-first; create vs install vs update; sync vs export
    # ------------------------------------------------------------------
    ToolScenario(
        tool="skill_search",
        archetype="capability_search_first",
        context=(
            "[beceri] Operatör: 'Ekran görüntüsü karşılaştırma adımlarını "
            "anlatan bir beceri lazım.' Elimizde böyle bir şey var mı "
            "bilmiyorum."
        ),
        args={"query": "screenshot"},
        reasoning=(
            "Varlığı belirsizken create çift kayıt yaratır, install kaynak "
            "ister. En ucuz ilk adım kanonik dizini skill_search ile taramak."
        ),
        index=16,
    ),
    ToolScenario(
        tool="skill_create",
        archetype="scaffold_after_empty_search",
        context=(
            "[beceri] skill_search 'expo triage' için boş döndü; kurulacak "
            "hazır bir kaynak da yok. Operatör Metro hata ayıklama "
            "adımlarını beceriye dönüştürmemi istiyor."
        ),
        args={
            "name": "expo-triage",
            "description": (
                "Metro/Expo hata ayıklama akışı: kırmızı ekran, cache, "
                "doctor adımları"
            ),
        },
        reasoning=(
            "Arama boş ve git kaynağı yok; install kaynaksız çalışmaz. "
            "Sıfırdan SKILL.md iskeletini skill_create açar."
        ),
        index=17,
    ),
    ToolScenario(
        tool="skill_install",
        archetype="install_from_git_url",
        context=(
            "[beceri] Ekip arkadaşı hazır bir beceri paylaştı: "
            "https://github.com/arketic/skill-ui-recipes.git. Operatör: "
            "'Bunu bizim kanonik dizine al.'"
        ),
        args={
            "name": "ui-recipes",
            "source": "https://github.com/arketic/skill-ui-recipes.git",
        },
        reasoning=(
            "Beceri zaten yazılmış; create boş iskelet açıp emeği çöpe "
            "atar. Var olan git kaynağını skill_install kurar."
        ),
        index=18,
    ),
    ToolScenario(
        tool="skill_update",
        archetype="ff_update_existing",
        context=(
            "[beceri] ui-recipes git tabanlı olarak kurulu; upstream'e "
            "yeni tarifler eklendiği duyuruldu. Operatör güncel sürümü "
            "istiyor."
        ),
        args={"name": "ui-recipes"},
        reasoning=(
            "Beceri zaten kurulu; yeniden install etmek çakışma yaratır. "
            "Git tabanlı kurulumu ff-only çeken araç skill_update."
        ),
        index=19,
    ),
    # --- trap: other CLIs can't see the skill -> sync, not install ----
    ToolScenario(
        tool="skill_sync",
        archetype="fanout_to_cli_dirs",
        context=(
            "[beceri] Kanonik dizindeki expo-triage güncellendi ama codex "
            "oturumu beceriyi hâlâ eski haliyle görüyor. Operatör: 'Tüm "
            "CLI'lar aynı sürümü görsün.'"
        ),
        args={},
        reasoning=(
            "Sorun kanonik kopya değil dağıtım; install/update kanonik "
            "dizini değiştirir, export paylaşım arşividir. Kanonikten CLI "
            "dizinlerine fan-out skill_sync işidir."
        ),
        index=20,
    ),
    ToolScenario(
        tool="skill_show",
        archetype="inspect_before_use",
        context=(
            "[beceri] skill_search 'triage' için iki sonuç döndürdü. "
            "Operatör: 'expo-triage tam olarak ne yapıyor, hangi dosyaları "
            "içeriyor?'"
        ),
        args={"name": "expo-triage"},
        reasoning=(
            "Soru tek bir becerinin içeriği; search sadece eşleşme "
            "listeler. Metadata + dosya listesini skill_show döker."
        ),
        index=21,
    ),
    # ------------------------------------------------------------------
    # UI verification: assertion -> verifier
    # ------------------------------------------------------------------
    ToolScenario(
        tool="ui_verify_text_visible",
        archetype="toast_text_assert",
        context=(
            "[cihaz] Kaydet düğmesine basıldı. Operatör: 'Ekranda "
            "Kaydedildi bildirimi çıktı mı, doğrula.'"
        ),
        args={"text": "Kaydedildi"},
        reasoning=(
            "Doğrulanacak şey bir metin; öğe seçicisi ya da piksel değil. "
            "a11y ağacında metin denetimi ui_verify_text_visible."
        ),
        index=22,
    ),
    # --- trap: text lives in image pixels, not in an a11y text node ---
    ToolScenario(
        tool="ui_verify_ocr_contains",
        archetype="rendered_image_text",
        context=(
            "[cihaz] Kampanya afişi sunucudan gelen bir GÖRSEL olarak "
            "çiziliyor; 'İNDİRİM' yazısı görüntünün pikselleri içinde, "
            "ayrı bir metin düğümü yok."
        ),
        args={"text": "İNDİRİM"},
        reasoning=(
            "Metin görüntünün içinde; text_visible'ın aradığı metin düğümü "
            "burada olmayabilir. Piksel-metin denetiminin aracı "
            "ui_verify_ocr_contains."
        ),
        index=23,
    ),
    ToolScenario(
        tool="ui_verify_element_exists",
        archetype="node_presence",
        context=(
            "[cihaz] Yeni menü sürümünde 'Hesabı Sil' seçeneğinin hiç "
            "render edilmemesi gerekiyordu. Operatör: 'O öğe ağaçta var "
            "mı, yok mu?'"
        ),
        args={"selector": "Hesabı Sil"},
        reasoning=(
            "Soru salt varlık/yokluk; görünürlük ya da etkinlik durumu "
            "sorulmuyor. Seçicinin ağaçtaki varlığını element_exists söyler."
        ),
        index=24,
    ),
    # --- trap: exists is known, the QUESTION is enabled/disabled ------
    ToolScenario(
        tool="ui_verify_element_state",
        archetype="disabled_button_trap",
        context=(
            "[cihaz] 'Gönder' düğmesi ekranda duruyor ama form boşken "
            "soluk olmalı. Operatör: 'Düğme şu an tıklanabilir mi, "
            "kontrol et.'"
        ),
        args={"selector": "Gönder", "state": "enabled"},
        reasoning=(
            "Düğmenin varlığı zaten biliniyor; element_exists yeni bilgi "
            "vermez. Soru etkinlik — ui_verify_element_state state=enabled."
        ),
        index=25,
    ),
    # --- trap: visible text can still be clipped ----------------------
    ToolScenario(
        tool="ui_verify_no_overflow",
        archetype="long_translation_clip",
        context=(
            "[cihaz] Almanca çeviriler eklendi; uzun sözcüklerin düğme "
            "sınırlarını taşırıp kırpılmasından şüpheleniliyor. Operatör "
            "taşma kontrolü istiyor."
        ),
        args={},
        reasoning=(
            "Metin görünür olsa da kırpılmış olabilir; text_visible bunu "
            "yakalamaz. Kırpılma/taşma işaretlerini no_overflow tarar."
        ),
        index=26,
    ),
    ToolScenario(
        tool="ui_verify_color_at",
        archetype="brand_color_assert",
        context=(
            "[cihaz] Tasarım ekibi ana düğmenin marka mavisi (37, 99, 235) "
            "olmasını şart koştu. Düğmenin merkezi ekranda (540, 1610)."
        ),
        args={"x": 540, "y": 1610, "expected_rgb": [37, 99, 235]},
        reasoning=(
            "Doğrulanacak şey metin ya da öğe değil, bir noktadaki renk. "
            "Pikseli örnekleyip beklenenle karşılaştıran araç color_at."
        ),
        index=27,
    ),
    ToolScenario(
        tool="ui_verify_screenshot_match",
        archetype="golden_pixel_regression",
        context=(
            "[cihaz] Onboarding ekranının onaylı 'altın' görüntüsü var "
            "(sha256 kaydı elimde). Operatör: 'Ekran birebir aynı mı, tek "
            "piksel bile oynamamış olmalı.'"
        ),
        args={
            "reference_sha256": (
                "9c4e7b2fd1a35e08b6c47f92ae15d3708c1b5e9f24a6d0837bfe61c4952da0e7"
            ),
        },
        reasoning=(
            "Birebir eşitlik isteniyor; tek nokta rengi ya da metin "
            "denetimi bunu kanıtlamaz. Referans karmayla tam karşılaştırma "
            "screenshot_match."
        ),
        index=28,
    ),
    # ------------------------------------------------------------------
    # Kanban: add (new) vs update (edit) vs done (complete)
    # ------------------------------------------------------------------
    ToolScenario(
        tool="kanban_card_add",
        archetype="new_task_capture",
        context=(
            "[kanban] Test sırasında panoda olmayan yeni bir iş çıktı: "
            "karanlık temada kontrast düşük. Operatör: 'Bunu panoya ekle, "
            "sırası gelince bakarız.'"
        ),
        args={
            "title": "Karanlık temada düşük kontrast",
            "body": "Ayarlar ekranı; ikincil metinler AA eşiğinin altında.",
        },
        reasoning=(
            "Panoda böyle bir kart yok; update/done var olan kart ister. "
            "Yeni işi card_add açar; 'sırası gelince' dendiği için backlog "
            "varsayılanı doğru."
        ),
        index=29,
    ),
    # --- trap: new FINDING on an existing card -> update, not add -----
    ToolScenario(
        tool="kanban_card_update",
        archetype="scope_edit_existing",
        context=(
            "[kanban] crd_9d41 'Login hatası' kartı zaten var; kök nedenin "
            "token yenileme olduğu anlaşıldı. Operatör: 'Kartın "
            "açıklamasına bulguyu işle.'"
        ),
        args={
            "card_id": "crd_9d41",
            "body": (
                "Kök neden: refresh token 401 sonrası yenilenmiyor; "
                "interceptor eksik."
            ),
        },
        reasoning=(
            "Kart mevcut; add çift kart yaratır, iş bitmediği için done da "
            "yanlış. Var olan kartın gövdesini card_update yamalar."
        ),
        index=30,
    ),
    ToolScenario(
        tool="kanban_card_done",
        archetype="complete_after_verify",
        context=(
            "[kanban] crd_9d41 kartındaki düzeltme cihazda doğrulandı, "
            "testler geçti. Operatör: 'Kartı kapat.'"
        ),
        args={"card_id": "crd_9d41"},
        reasoning=(
            "İş doğrulanıp bitti; içerik düzenlenmeyecek, yani update "
            "değil. Tamamlanan kartı done kolonuna card_done taşır."
        ),
        index=31,
    ),
    # ------------------------------------------------------------------
    # GitHub: issue vs PR ops; fork vs clone; workflow list vs run
    # ------------------------------------------------------------------
    ToolScenario(
        tool="github_issue_create",
        archetype="repro_bug_issue",
        context=(
            "[github] arketic/fieldnote-app testinde yeniden üretilebilir "
            "bir çökme bulundu: profil fotoğrafı 10 MB üzerindeyse "
            "uygulama kapanıyor. Kayıt altına alınmalı."
        ),
        args={
            "repo": "arketic/fieldnote-app",
            "title": "10 MB üzeri profil fotoğrafında çökme",
            "body": (
                "Adımlar: Profil > Fotoğraf seç > 10 MB üzeri dosya. "
                "Beklenen: hata mesajı. Gerçekleşen: uygulama kapanıyor. "
                "Logcat: OutOfMemoryError."
            ),
            "labels": ["bug"],
        },
        reasoning=(
            "Bu yeni bir bulgu; comment/close var olan issue ister. "
            "Yeniden üretim adımlarıyla kaydı issue_create açar."
        ),
        index=32,
    ),
    # --- trap: root cause found but NOT fixed -> comment, not close ---
    ToolScenario(
        tool="github_issue_comment",
        archetype="progress_not_close",
        context=(
            "[github] arketic/fieldnote-app#87 üzerinde çalışılıyor; kök "
            "neden bulundu ama düzeltme henüz yazılmadı. Operatör bulgunun "
            "issue'ya işlenmesini istedi."
        ),
        args={
            "repo": "arketic/fieldnote-app",
            "number": 87,
            "body": (
                "Kök neden: görsel yeniden boyutlandırma ana thread'de; "
                "10 MB üzeri dosyada OOM. Plan: arka plan worker + "
                "downsample. PR hazırlanıyor."
            ),
        },
        reasoning=(
            "Sorun çözülmedi, yalnız ara bulgu paylaşılacak; close "
            "doğrulanmamış işi kapatır. Bilgiyi issue_comment ekler."
        ),
        index=33,
    ),
    ToolScenario(
        tool="github_issue_close",
        archetype="verified_fix_close",
        context=(
            "[github] #87'nin düzeltmesi merge edildi ve cihazda "
            "doğrulandı: 15 MB fotoğraf artık sorunsuz yükleniyor. "
            "Operatör: 'Issue'yu kapat.'"
        ),
        args={
            "repo": "arketic/fieldnote-app",
            "number": 87,
            "comment": (
                "Düzeltme v1.4.2'de doğrulandı: 15 MB fotoğraf downsample "
                "edilip yükleniyor, çökme yok."
            ),
        },
        reasoning=(
            "Düzeltme merge edilip cihazda doğrulandı; artık salt yorum "
            "eksik kalır. Kapanış notuyla issue_close doğru adım."
        ),
        index=34,
    ),
    # --- pr_create vs auto_pr_create: explicit repo/head vs current ---
    ToolScenario(
        tool="github_pr_create",
        archetype="explicit_head_pr",
        context=(
            "[github] fix/oom-resize dalı arketic/fieldnote-app'e "
            "push'landı ama şu anki çalışma alanı BAŞKA bir depoda; gh "
            "dal çıkarımı yapamaz. PR açılacak."
        ),
        args={
            "repo": "arketic/fieldnote-app",
            "title": "Görsel boyutlandırmayı arka plana taşı",
            "body": (
                "10 MB üzeri fotoğraflarda OOM çökmesini giderir (#87). "
                "Resize worker'a taşındı, downsample eklendi."
            ),
            "head": "fix/oom-resize",
        },
        reasoning=(
            "Çalışma alanı hedef depoda değil; auto_pr_create mevcut dala "
            "güvenir, yanlış depoyu görür. Depo+head'i açıkça veren "
            "github_pr_create gerekli."
        ),
        index=35,
    ),
    ToolScenario(
        tool="auto_pr_create",
        archetype="current_branch_pr",
        context=(
            "[github] Şu anki çalışma alanında fix/anr-startup dalı "
            "üzerindeyiz; iş bitti, commit'ler push'landı, testler yeşil. "
            "Operatör: 'PR'ı aç.'"
        ),
        args={
            "title": "Başlangıçta ANR'a yol açan senkron IO'yu kaldır",
            "body": (
                "Soğuk başlatmadaki 6 sn'lik donma giderildi: ayar okuma "
                "async'e alındı.\n\n### Tests\n- pytest tests/startup -q: "
                "14 passed\n- Cihazda soğuk başlatma < 1.2 sn"
            ),
        },
        reasoning=(
            "PR üzerinde durduğumuz dal için; depo ve head'i gh zaten "
            "biliyor. Bu akışın aracı auto_pr_create; github_pr_create'in "
            "açık repo/head'ine gerek yok."
        ),
        index=36,
    ),
    ToolScenario(
        tool="github_pr_merge",
        archetype="squash_after_green",
        context=(
            "[github] arketic/fieldnote-app#91 onaylandı, tüm kontroller "
            "yeşil; depo geçmişi tek commit'lik squash kuralıyla "
            "tutuluyor. Operatör: 'Birleştir.'"
        ),
        args={
            "repo": "arketic/fieldnote-app",
            "number": 91,
            "strategy": "squash",
            "delete_branch": True,
        },
        reasoning=(
            "Onay + yeşil kontroller tamam, bekletmenin gerekçesi yok. "
            "Depo kuralı tek commit istediği için squash; iş biten dal da "
            "temizlenmeli."
        ),
        index=37,
    ),
    # --- trap: no push rights -> fork, a clone gives no PR base -------
    ToolScenario(
        tool="github_repo_fork",
        archetype="no_push_rights_fork",
        context=(
            "[github] expo/expo deposundaki bir hatayı düzeltmek istiyoruz "
            "ama depoya yazma yetkimiz yok. PR upstream'e bizim "
            "kopyamızdan açılacak."
        ),
        args={"repo": "expo/expo"},
        reasoning=(
            "Yazma yetkisi olmadan dal push'lanamaz; clone salt yerel "
            "kopya verir, PR tabanı olmaz. Hesapta kopya için repo_fork "
            "gerekir."
        ),
        index=38,
    ),
    ToolScenario(
        tool="github_workflow_list",
        archetype="discover_workflows",
        context=(
            "[github] arketic/fieldnote-app'te dağıtımın hangi Actions "
            "workflow'uyla yapıldığı bilinmiyor. Operatör 'sürümü CI'dan "
            "tetikleyelim' dedi ama ad belirsiz."
        ),
        args={"repo": "arketic/fieldnote-app"},
        reasoning=(
            "workflow_run ad/ID ister; adı bilmeden tetiklemek körlemesine "
            "olur. Önce mevcut workflow'ları workflow_list gösterir."
        ),
        index=39,
    ),
    ToolScenario(
        tool="github_workflow_run",
        archetype="dispatch_release",
        context=(
            "[github] workflow_list 'release.yml (workflow_dispatch)' "
            "girdisini gösterdi. Operatör: 'Sürüm derlemesini main "
            "üzerinden tetikle.'"
        ),
        args={
            "repo": "arketic/fieldnote-app",
            "workflow": "release.yml",
            "ref": "main",
        },
        reasoning=(
            "Ad listeyle doğrulandı ve dispatch destekli; keşif bitti, "
            "sıra tetiklemede. workflow_run ile main ref'inde çalıştırırım."
        ),
        index=40,
    ),
    # ------------------------------------------------------------------
    # META: discover-first — a needed tool is NOT visible -> tool_search
    # ------------------------------------------------------------------
    ToolScenario(
        tool="tool_search",
        archetype="deferred_slack_discovery",
        context=(
            "[meta] Operatör: 'Derleme bitince ekibin Slack kanalına da "
            "yaz.' Görünür araç listemde Slack'e dair hiçbir araç yok; "
            "Telegram aracı var ama istenen kanal Slack."
        ),
        args={"query": "send a Slack message"},
        reasoning=(
            "Slack aracı görünür değil; notify_telegram yanlış kanala "
            "gider, olmayan bir adı uydurmak reddedilir. Ertelenmiş aracı "
            "önce tool_search ile keşfetmeliyim."
        ),
        index=41,
    ),
    ToolScenario(
        tool="tool_search",
        archetype="unknown_capability_no_guess",
        context=(
            "[meta] Operatör cihazın pil yüzdesini soruyor. Görünür "
            "listede pil okuyan bir araç yok; ama SelfFork'ta yüzlerce "
            "ertelenmiş araç var."
        ),
        args={"query": "read device battery level"},
        reasoning=(
            "Görünmeyen bir aracı tahminle çağırmak şema hatasıyla düşer; "
            "'yapamam' demek de erken teslimiyet. Doğru refleks yeteneği "
            "tool_search ile aramak."
        ),
        index=42,
    ),
    # ------------------------------------------------------------------
    # META: ask-vs-act — genuinely ambiguous / irreversible -> ASK
    # ------------------------------------------------------------------
    ToolScenario(
        tool="AskUserQuestion",
        archetype="ambiguous_cleanup_target",
        context=(
            "[meta] Operatör: 'Şu eski deney kalıntılarını temizle.' Üç "
            "aday var: cihazdaki durum kayıtları, deneysel beceri dizini, "
            "eski git dalı. Kastedilen belirsiz; hepsi silme = geri "
            "dönüşsüz."
        ),
        args={
            "questions": [
                {
                    "question": "Hangi deney kalıntıları temizlensin?",
                    "header": "Temizlik kapsamı",
                    "options": [
                        {
                            "label": "Durum kayıtları",
                            "description": (
                                "crash_state etiketleri: onboarding-oncesi "
                                "ve onboarding-sonrasi"
                            ),
                        },
                        {
                            "label": "Deneysel beceri",
                            "description": "expo-triage-deneme beceri dizini",
                        },
                        {
                            "label": "Eski git dalı",
                            "description": "deney/onboarding-reset dalı",
                        },
                    ],
                    "multiSelect": True,
                },
            ],
        },
        reasoning=(
            "Silme geri alınamaz ve hedef üç farklı araca çıkıyor; yanlış "
            "tahmin veri kaybettirir. Belirsiz yıkıcı istekte önce "
            "AskUserQuestion ile kapsam netleşir."
        ),
        index=43,
    ),
    ToolScenario(
        tool="AskUserQuestion",
        archetype="irreversible_publish_choice",
        context=(
            "[meta] Operatör: 'Sürümü yayınla.' Bu iki şey olabilir: "
            "expo_publish (kullanıcılara anında OTA) ya da eas_submit "
            "(mağaza incelemesine gönderim). Etkileri ve geri dönüşleri "
            "çok farklı."
        ),
        args={
            "questions": [
                {
                    "question": "'Yayınla' ile hangisini kastediyorsun?",
                    "header": "Yayın kanalı",
                    "options": [
                        {
                            "label": "OTA güncelleme",
                            "description": (
                                "expo_publish: JS değişikliği kullanıcılara "
                                "anında iner"
                            ),
                        },
                        {
                            "label": "Mağaza gönderimi",
                            "description": (
                                "eas_submit: binary App Store / Play "
                                "incelemesine gider"
                            ),
                        },
                    ],
                },
            ],
        },
        reasoning=(
            "İki yayın yolu da makul ama ikisi de geri dönüşsüz ve "
            "etkileri farklı; yanlış seçim kullanıcıya hatalı sürüm basar. "
            "Tahmin değil AskUserQuestion gerekir."
        ),
        index=44,
    ),
    ToolScenario(
        tool="AskUserQuestion",
        archetype="design_taste_question",
        context=(
            "[meta] Yeni boş-durum ekranı için iki yerleşim taslağı hazır. "
            "Hangisinin uygulanacağı tamamen zevk meselesi; hiçbir "
            "doğrulama aracı 'doğru' cevabı veremez."
        ),
        args={
            "questions": [
                {
                    "question": (
                        "Boş durum ekranında hangi yerleşim uygulansın?"
                    ),
                    "header": "Boş durum tasarımı",
                    "options": [
                        {
                            "label": "Minimal metin",
                            "description": "Tek satır açıklama + soluk ikon",
                        },
                        {
                            "label": "İllüstrasyonlu",
                            "description": (
                                "Büyük görsel + başlık + eylem düğmesi"
                            ),
                        },
                    ],
                },
            ],
        },
        reasoning=(
            "Bu bir tercih sorusu; teknik doğru yok, tahmin operatör "
            "iradesini gasp eder. Zevk kararını AskUserQuestion operatöre "
            "bırakır."
        ),
        index=45,
    ),
    # ------------------------------------------------------------------
    # META: inform-vs-ask — notify_telegram pushes, never blocks
    # ------------------------------------------------------------------
    ToolScenario(
        tool="notify_telegram",
        archetype="inform_done_not_ask",
        context=(
            "[meta] eas build 35 dakika sonra başarıyla bitti; operatör "
            "'bitince haber ver' demişti. Karar gerektiren bir durum yok, "
            "sadece bilgi."
        ),
        args={
            "message": (
                "eas build (ios, production) başarıyla tamamlandı: 35 dk. "
                "Artifact EAS panelinde."
            ),
            "level": "info",
        },
        reasoning=(
            "Operatörden seçim istenmiyor; AskUserQuestion döngüyü boşuna "
            "bloklar. Tek yönlü bilgi notify_telegram işidir, info yeter."
        ),
        index=46,
    ),
    ToolScenario(
        tool="notify_telegram",
        archetype="crit_crash_alert",
        context=(
            "[meta] Üretim kanalına itilen OTA sonrası crash_log_fetch her "
            "açılışta tekrarlanan bir çökme gösteriyor; kullanıcılar "
            "etkileniyor, operatör başında değil."
        ),
        args={
            "message": (
                "KRİTİK: production OTA sonrası açılışta tekrarlı çökme. "
                "Logcat topluyorum, kök nedeni araştırıyorum."
            ),
            "level": "crit",
        },
        reasoning=(
            "Kullanıcıya dokunan aktif bir arıza var; info seviyesi gözden "
            "kaçabilir. Operatörü level=crit ile derhal uyarmak gerekir."
        ),
        index=47,
    ),
    # ------------------------------------------------------------------
    # META: evidence before switching — quota_snapshot vs rotate_to
    # ------------------------------------------------------------------
    ToolScenario(
        tool="quota_snapshot",
        archetype="check_before_rotate",
        context=(
            "[meta] claude-code'dan gelen son iki yanıt 'rate limited' "
            "uyarısı taşıyor. Başka CLI'a geçmeden önce pencerenin "
            "gerçekten dolu olup olmadığını görmek istiyorum."
        ),
        args={"cli_id": "claude-code"},
        reasoning=(
            "Belirti kota olabilir ama kanıt yok; körlemesine rotate_to "
            "bağlam kaybettirir. Önce quota_snapshot pencerenin durumunu "
            "gösterir; available_clis yalnız kaba sağlık verir."
        ),
        index=48,
    ),
    ToolScenario(
        tool="rotate_to",
        archetype="swap_after_exhaustion",
        context=(
            "[meta] quota_snapshot doğruladı: claude-code'un 5 saatlik "
            "penceresi tükendi, sıfırlanmaya 3 saat var. gemini-cli "
            "sağlıklı ve boşta; iş bekleyemez."
        ),
        args={
            "cli_id": "gemini-cli",
            "reason": "claude-code 5h penceresi tükendi; sıfırlanma 3 saat sonra",
        },
        reasoning=(
            "Tükenme kanıtlandı ve iş acil; sleep_until 3 saat kaybettirir. "
            "Bu turluk geçişi rotate_to yapar; kalıcı kural olsaydı "
            "set_cli_override gerekirdi."
        ),
        index=49,
    ),
    # --- trap: permanent per-workspace rule -> override, not rotate ---
    ToolScenario(
        tool="set_cli_override",
        archetype="sticky_workspace_cli",
        context=(
            "[meta] Operatör: 'fieldnote-mobile çalışma alanındaki işleri "
            "bundan sonra HEP codex yapsın; her seferinde elle "
            "değiştirmeyeyim.'"
        ),
        args={"workspace": "fieldnote-mobile", "cli": "codex"},
        reasoning=(
            "İstek tek seferlik geçiş değil kalıcı kural; rotate_to yalnız "
            "o anki turu değiştirir. Yapışkan yönlendirmeyi "
            "set_cli_override kurar; cli_override sadece okur."
        ),
        index=50,
    ),
    ToolScenario(
        tool="set_cli_effort",
        archetype="low_effort_chore",
        context=(
            "[meta] Sıradaki iş 300 dosyada mekanik bir yeniden "
            "adlandırma; muhakeme istemiyor ama claude-code 'max' efor ile "
            "çalışıp kotayı hızla eritiyor."
        ),
        args={"cli": "claude-code", "effort": "low"},
        reasoning=(
            "Sorun hangi CLI'ın seçildiği değil ne kadar düşündüğü; "
            "rotate_to ya da model daraltmak konuyu ıskalar. Mekanik iş "
            "için eforu set_cli_effort low'a çeker."
        ),
        index=51,
    ),
    ToolScenario(
        tool="set_cli_models",
        archetype="narrow_model_subset",
        context=(
            "[meta] Bütçe kısıldı: claude-code'un opus'a yönlenmesi "
            "istenmiyor, işler sonnet ile dönmeli; efor ayarı olduğu gibi "
            "kalacak."
        ),
        args={"cli": "claude-code", "models": ["claude-sonnet-4-6"]},
        reasoning=(
            "Kısıt efor değil model seçimi; set_cli_effort düşünme "
            "derinliğini ayarlar, modeli değil. Yönlendiriciyi sonnet'e "
            "set_cli_models daraltır."
        ),
        index=52,
    ),
    # ------------------------------------------------------------------
    # META: sleep_until vs cancel_pending
    # ------------------------------------------------------------------
    ToolScenario(
        tool="sleep_until",
        archetype="quota_window_sleep",
        context=(
            "[meta] Tüm kayıtlı CLI'ların kotası tükendi; quota_snapshot "
            "en erken açılışın 15:00 UTC (epoch 1783090800) olduğunu "
            "söylüyor. Bekleyen acil iş yok."
        ),
        args={
            "epoch_seconds": 1783090800,
            "reason": "tüm CLI kotaları dolu; ilk pencere 15:00 UTC'de açılıyor",
            "kind": "five_hour",
        },
        reasoning=(
            "Geçilecek sağlıklı CLI kalmadı; rotate_to çıkışsız. Boş "
            "döngüde beklemek log kirletir; pencere açılışına dek "
            "sleep_until doğru."
        ),
        index=53,
    ),
    ToolScenario(
        tool="cancel_pending",
        archetype="revoke_scheduled_sleep",
        context=(
            "[meta] Az önce sleep_until planlandı (action_id: "
            "sess_9f2c41). Operatör hemen ardından yazdı: 'Bekleme, işi "
            "manuel API anahtarıyla şimdi bitirelim.'"
        ),
        args={
            "action_id": "sess_9f2c41",
            "reason": "operatör beklemeyi iptal etti; işe hemen devam edilecek",
        },
        reasoning=(
            "Bekleme kararı verildi ama artık geçersiz ve hâlâ kuyrukta. "
            "Yeni bir uyku değil, verilmiş kararın geri alınması gerekir: "
            "cancel_pending."
        ),
        index=54,
    ),
    # ------------------------------------------------------------------
    # META: mind_note_add (record) vs mind_recall (retrieve)
    # ------------------------------------------------------------------
    ToolScenario(
        tool="mind_note_add",
        archetype="record_operator_decision",
        context=(
            "[meta] Operatör net bir kural koydu: 'Üretim OTA yayınları "
            "bundan böyle yalnız salı günleri, önce staging kanalında 24 "
            "saat bekletilerek yapılacak.'"
        ),
        args={
            "content": (
                "Üretim OTA kuralı: yalnız salı günleri; önce staging'de "
                "24 saat bekletilir."
            ),
            "kind": "decision",
            "pinned": True,
        },
        reasoning=(
            "Bu geçmişi hatırlama değil geleceğe kural yazma; mind_recall "
            "yalnız okur. Operatör kararı kind=decision + pinned ile "
            "mind_note_add'e işlenir."
        ),
        index=55,
    ),
    ToolScenario(
        tool="mind_recall",
        archetype="retrieve_past_fix",
        context=(
            "[meta] eas build yine 'keystore mismatch' hatası verdi. Bu "
            "hatayı haftalar önce bir kez çözmüştük ama adımları "
            "hatırlamıyorum."
        ),
        args={"query": "eas build keystore mismatch çözümü", "top_k": 5},
        reasoning=(
            "Bilgi yeni değil, geçmişte kayıtlı; note_add yazma yönüdür, "
            "çözümü getirmez. Geçmiş notları mind_recall sorgusu döker."
        ),
        index=56,
    ),
    # ------------------------------------------------------------------
    # META: compact_context, session_state, mark_done
    # ------------------------------------------------------------------
    ToolScenario(
        tool="compact_context",
        archetype="summary_compaction",
        context=(
            "[meta] Uzun hata ayıklama oturumunda bağlam şişti: yüzlerce "
            "log satırı taşındı, pencere sınıra yaklaşıyor; ama kök neden "
            "analizi ve kararlar kaybolmamalı."
        ),
        args={
            "strategy": "summary",
            "reason": "log dökümleri bağlamı doldurdu; kararlar özetle korunacak",
        },
        reasoning=(
            "truncate baştaki kararları da keser, handoff oturum devri "
            "içindir. Kararları koruyup ham logları sıkıştırmak "
            "strategy=summary ile olur."
        ),
        index=57,
    ),
    ToolScenario(
        tool="session_state",
        archetype="orient_before_override",
        context=(
            "[meta] Yeni devraldığım oturumda operatör 'bu çalışma alanını "
            "codex'e sabitle' dedi ama çalışma alanının tam slug'ını "
            "bilmiyorum; yanlış slug sessizce boşa gider."
        ),
        args={},
        reasoning=(
            "set_cli_override doğru workspace slug'ı ister; tahmin sessiz "
            "hataya döner. Önce session_state oturumun proje/çalışma alanı "
            "kimliğini verir."
        ),
        index=58,
    ),
    ToolScenario(
        tool="mark_done",
        archetype="prd_complete",
        context=(
            "[meta] PRD'deki üç kabul kriterinin üçü de doğrulandı: çökme "
            "giderildi (#87 kapalı), OTA yayınlandı, kanban kartları done. "
            "Bekleyen iş kalmadı."
        ),
        args={
            "reason": (
                "PRD'nin 3/3 kabul kriteri doğrulandı: #87 kapalı, OTA "
                "yayında, kanban temiz"
            ),
        },
        reasoning=(
            "Tüm kriterler kanıtla kapandı; devam etmek meşguliyet "
            "tiyatrosu olur. Teslimi mark_done bildirir — tek görev "
            "bitince değil, PRD'nin tamamı bitince."
        ),
        index=59,
    ),
]

__all__ = ["SCENARIOS"]
