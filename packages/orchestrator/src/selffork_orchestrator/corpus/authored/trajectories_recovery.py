"""Agentic multi-tool trajectories (recovery) — failure-driven chains.

Her zincirde en az bir adım BAŞARISIZ olur ya da şaşırtıcı bir sonuç döner;
model bir sonraki adımda bu sonucu okuyup TEŞHİS eder ve TOPARLAR: farklı
argümanla yeniden dener, başka araca düşer, yeniden gözlemler, operatöre
sorar ya da güvenle bekler. Mutlu-yol zincirlerinin öğretemediği dayanıklılık
davranışı budur: "hata gördün -> panik yok -> teşhis -> gerekçeli kurtarma".
Kapsanan desenler: kaçan tıklama sonrası yeniden gözlem, geç yüklenen/yeniden
adlandırılan seçici, split-APK -> XAPK, kırmızı CI -> yeniden koş -> merge,
eylem sonrası çökme -> logcat -> onarım, boş hafıza -> oturum durumu, kota
429 -> rotasyon ya da uyku, bot engeli -> stealth, 0 sonuç -> yeniden sorgu
-> operatöre soru, ekran dışı öğe -> kaydır -> bul, çalınan odak -> yeniden
odaklan, yanlış workflow adı -> listele -> düzelt.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import AgenticStep, AgenticTrajectory

TRAJECTORIES: list[AgenticTrajectory] = [
    # ------------------------------------------------------------------
    # 1. Tıklama hedefi ıskalıyor: banner overlay yutuyor -> yeniden
    #    a11y gözlemi -> kaymış bounds ile düzeltilmiş tıklama
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="android_tap_miss_reobserve_retry",
        goal=(
            "[görev] KargoTakip Android uygulamasında ayarlar ekranındaki "
            "'Bildirimler' anahtarı açılacak; sonucu ekrandan doğrula."
        ),
        steps=[
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.kargotakip"},
                result=(
                    "[sonuç] KargoTakip ayarlar ekranında açıldı; üstte bir "
                    "kampanya banner'ı, altında ayar listesi görünüyor."
                ),
                reasoning="Hedef ekran ayarlar; uygulamayı başlatıyorum.",
            ),
            AgenticStep(
                tool="android_a11y_tree",
                args={},
                result=(
                    "[sonuç] a11y ağacı: Switch#notifications "
                    "bounds=[560,420,660,480]; üstte View#promo_banner "
                    "bounds=[0,320,720,440] (yarı saydam, kapatılabilir)."
                ),
                reasoning=(
                    "Anahtara dokunmak için koordinat lazım; körlemesine "
                    "tıklamak yerine a11y ağacından bounds alıyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 610, "y": 450},
                result=(
                    "[sonuç] BAŞARISIZ: anahtar durumu değişmedi. Dokunuş "
                    "üstteki promo banner'a gitti; banner kapandı ve liste "
                    "yukarı kaydı."
                ),
                reasoning=(
                    "Switch bounds=[560,420,660,480]; ortası (610,450), "
                    "anahtarı oradan açıyorum."
                ),
            ),
            AgenticStep(
                tool="android_a11y_tree",
                args={},
                result=(
                    "[sonuç] Yeni ağaç: promo_banner yok; "
                    "Switch#notifications bounds=[560,300,660,360] — banner "
                    "kapanınca 120px yukarı kaymış. checked=false."
                ),
                reasoning=(
                    "Tıklama banner'a gitti ve düzen değişti; eski "
                    "koordinatlar artık geçersiz. Yeniden tıklamadan önce "
                    "ekranı yeniden gözlemliyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 610, "y": 330},
                result="[sonuç] Anahtar AÇIK konuma geçti (yeşil).",
                reasoning=(
                    "Güncel bounds=[560,300,660,360]; ortası (610,330). "
                    "Kaymış düzene göre düzeltilmiş noktaya tıklıyorum."
                ),
            ),
            AgenticStep(
                tool="android_screen_text",
                args={},
                result=(
                    "[sonuç] Ekran metni: 'Bildirimler: Açık — kargo durumu "
                    "anlık bildirilecek'."
                ),
                reasoning=(
                    "Anahtar görsel olarak açık; ekran metniyle durumu "
                    "bağımsız kanaldan doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "İlk dokunuş banner'a kaçtı; yeniden gözlem sonrası "
                        "düzeltilmiş koordinatla anahtar açıldı ve metinle "
                        "doğrulandı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Hedef durum ekran metniyle kanıtlandı; bitti.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 2. Seçici bulunamıyor: networkidle bekle -> hâlâ yok -> DOM
    #    snapshot ile yeniden zemin -> yeni id ile tıkla
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="browser_selector_missing_wait_snapshot",
        goal=(
            "[görev] panel.example.com/raporlar sayfasında aylık rapor "
            "indirme düğmesine tıklanacak."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={"url": "https://panel.example.com/raporlar"},
                result=(
                    "[sonuç] Sayfa açıldı; başlık 'Raporlar', içerik "
                    "alanında dönen bir spinner var."
                ),
                reasoning="Hedef sayfaya gidiyorum.",
            ),
            AgenticStep(
                tool="browser_query_selector",
                args={"target": "#btn-rapor-indir"},
                result=(
                    "[sonuç] BAŞARISIZ: '#btn-rapor-indir' için eşleşme yok "
                    "(0 öğe)."
                ),
                reasoning=(
                    "İndirme düğmesinin bilinen id'si #btn-rapor-indir; "
                    "tıklamadan önce varlığını kontrol ediyorum."
                ),
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "networkidle"},
                result=(
                    "[sonuç] Ağ boşta; spinner kayboldu, rapor kartları "
                    "yerleşti."
                ),
                reasoning=(
                    "Seçici bulunamadı ama ekranda spinner vardı: SPA içeriği "
                    "geç yüklüyor olabilir. Hata verip vazgeçmek yerine ağ "
                    "sakinleşene kadar bekliyorum."
                ),
            ),
            AgenticStep(
                tool="browser_query_selector",
                args={"target": "#btn-rapor-indir"},
                result=(
                    "[sonuç] YİNE BAŞARISIZ: yükleme bitti ama "
                    "'#btn-rapor-indir' hâlâ yok."
                ),
                reasoning=(
                    "İçerik artık tam yüklü; aynı seçiciyi bir kez daha "
                    "deniyorum — geç yükleme hipotezini test ediyorum."
                ),
            ),
            AgenticStep(
                tool="browser_dom_snapshot",
                args={},
                result=(
                    "[sonuç] Snapshot: indirme düğmesi mevcut ama id "
                    "değişmiş — <button id='btn-report-download' "
                    "class='btn primary'>Aylık raporu indir</button>."
                ),
                reasoning=(
                    "İki denemede de seçici boş: sorun zamanlama değil, "
                    "seçicinin kendisi. DOM snapshot ile sayfayı yeniden "
                    "zemine alıp düğmenin gerçek kimliğini arıyorum."
                ),
            ),
            AgenticStep(
                tool="browser_click",
                args={"target": "#btn-report-download"},
                result=(
                    "[sonuç] Tıklandı; 'aylik-rapor-2026-06.pdf' indirmesi "
                    "başladı."
                ),
                reasoning=(
                    "Snapshot düğmenin yeni id'sinin 'btn-report-download' "
                    "olduğunu gösterdi; eski seçici yerine bunu kullanıyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Düğme id'si değişmişti; bekleme sonrası snapshot "
                        "ile yeni id bulundu ve indirme başlatıldı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="İndirme başladı; hedef gerçekleşti.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 3. Kurulum INSTALL_FAILED_MISSING_SPLIT ile düşüyor -> XAPK
    #    kurulumuna düş -> başlat -> doğrula
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="android_split_apk_xapk_fallback",
        goal=(
            "[görev] FieldNote beta yapısı emülatöre kurulup açılış smoke "
            "testi yapılacak. Yapı dosyaları C:/builds/ altında."
        ),
        steps=[
            AgenticStep(
                tool="android_device_list",
                args={},
                result=(
                    "[sonuç] Tek cihaz: emulator-5554 (Pixel 7, API 34), "
                    "durum: device."
                ),
                reasoning=(
                    "Kurulumdan önce hedef cihazın hazır olduğunu "
                    "doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="android_install_app",
                args={"apk_path": "C:/builds/fieldnote-beta.apk"},
                result=(
                    "[sonuç] BAŞARISIZ: INSTALL_FAILED_MISSING_SPLIT — "
                    "base APK split yapı; config.arm64_v8a ve config.tr "
                    "parçaları eksik."
                ),
                reasoning=(
                    "Cihaz hazır; beta APK'yı düz kurulumla deniyorum."
                ),
            ),
            AgenticStep(
                tool="android_install_xapk",
                args={"xapk_dir": "C:/builds/fieldnote-beta-xapk"},
                result=(
                    "[sonuç] XAPK kurulumu başarılı: base + 2 split parça "
                    "birlikte yüklendi (com.arketic.fieldnote)."
                ),
                reasoning=(
                    "INSTALL_FAILED_MISSING_SPLIT tek APK'nın yetmediğini "
                    "söylüyor: yapı split. builds/ altındaki XAPK dizini tüm "
                    "parçaları içerir; düz kurulum yerine XAPK kurulumuna "
                    "düşüyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.arketic.fieldnote"},
                result=(
                    "[sonuç] Uygulama açıldı; karşılama ekranı geldi, çökme "
                    "yok."
                ),
                reasoning=(
                    "Kurulum bu kez tamam; smoke testin ilk adımı olarak "
                    "uygulamayı başlatıyorum."
                ),
            ),
            AgenticStep(
                tool="android_screen_text",
                args={},
                result=(
                    "[sonuç] Ekran metni: 'FieldNote beta — Hoş geldin! "
                    "Sahaya çıkmaya hazırsın.'"
                ),
                reasoning=(
                    "Açılış görünüyor; ekran metniyle doğru ekranın "
                    "yüklendiğini kanıtlıyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Düz APK split hatası verdi; XAPK kurulumuyla "
                        "toparlandı, uygulama açılıp karşılama ekranı "
                        "doğrulandı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Kurulum + açılış kanıtlı; smoke test tamam.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 4. Merge kırmızı zorunlu kontrole takılıyor -> PR'ı incele ->
    #    hafızadan flaky kanıtı -> workflow'u yeniden koş -> merge
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="pr_merge_blocked_flaky_rerun",
        goal=(
            "[görev] arketic/fieldnote-app deposundaki PR #91 "
            "(feat/offline-sync) squash ile merge edilecek."
        ),
        steps=[
            AgenticStep(
                tool="github_pr_merge",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 91,
                    "strategy": "squash",
                },
                result=(
                    "[sonuç] BAŞARISIZ: merge reddedildi — zorunlu kontrol "
                    "'tests' kırmızı (1 failing check)."
                ),
                reasoning=(
                    "PR incelemesi onaylı diye biliniyor; squash merge'i "
                    "deniyorum."
                ),
            ),
            AgenticStep(
                tool="github_pr_view",
                args={"repo": "arketic/fieldnote-app", "number": 91},
                result=(
                    "[sonuç] PR #91: onay 2/2, çakışma yok. Kontroller: "
                    "lint yeşil, build yeşil, tests KIRMIZI — düşen test: "
                    "test_sync_retry (TimeoutError, 1 kez)."
                ),
                reasoning=(
                    "Merge 'tests' kontrolüne takıldı; körlemesine yeniden "
                    "denemek yerine hangi testin neden düştüğünü görmek "
                    "için PR'ı açıyorum."
                ),
            ),
            AgenticStep(
                tool="mind_recall",
                args={"query": "test_sync_retry flaky timeout", "top_k": 3},
                result=(
                    "[sonuç] 1 not bulundu: 'test_sync_retry CI'da ~%10 "
                    "flaky (TimeoutError); kod hatası değil, yeniden "
                    "koşunca geçiyor (son 3 vaka).'"
                ),
                reasoning=(
                    "TimeoutError tek seferlik görünüyor; bu test daha önce "
                    "flaky diye işaretlenmiş miydi diye hafızaya bakıyorum — "
                    "kod hatasıysa yeniden koşmak israf olur."
                ),
            ),
            AgenticStep(
                tool="github_workflow_run",
                args={
                    "repo": "arketic/fieldnote-app",
                    "workflow": "tests.yml",
                    "ref": "feat/offline-sync",
                },
                result=(
                    "[sonuç] tests.yml yeniden tetiklendi; run #488 ~4 dk "
                    "sonra YEŞİL bitti (test_sync_retry geçti)."
                ),
                reasoning=(
                    "Hafıza kaydı bunun bilinen flaky olduğunu doğruladı; "
                    "kodu değiştirmeden workflow'u aynı dal üzerinde "
                    "yeniden koşuyorum."
                ),
            ),
            AgenticStep(
                tool="github_pr_merge",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 91,
                    "strategy": "squash",
                    "delete_branch": True,
                },
                result=(
                    "[sonuç] PR #91 squash ile merge edildi; "
                    "feat/offline-sync dalı silindi."
                ),
                reasoning=(
                    "Zorunlu kontrol artık yeşil; ilk denemede reddedilen "
                    "merge'i tekrarlıyorum, iş bitti diye dalı da "
                    "temizliyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "test_sync_retry 4. kez flaky çıktı (PR #91, "
                        "TimeoutError); yeniden koşmak yetti. Kalıcı çözüm "
                        "için issue açılmalı."
                    ),
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Flaky vakası tekrarladı; gelecekteki triage'ler aynı "
                    "teşhisi saniyede yapabilsin diye kanıtı hafızaya "
                    "işliyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Merge kırmızı flaky teste takılmıştı; yeniden koşum "
                        "yeşile döndürdü, PR #91 merge edildi, kanıt nota "
                        "işlendi."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Merge kanıtla tamamlandı; kapatıyorum.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 5. Dokunuş sonrası uygulama çöküyor -> logcat teşhisi (bozuk
    #    cache) -> force_stop -> clear_data -> yeniden başlat -> doğrula
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="android_tap_crash_logcat_repair",
        goal=(
            "[görev] NotDefteri uygulamasında 'Arşiv' sekmesi açılıp eski "
            "notların listelendiği doğrulanacak. Notlar bulutla senkron."
        ),
        steps=[
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.notdefteri"},
                result=(
                    "[sonuç] NotDefteri açıldı; ana not listesi görünüyor, "
                    "alt barda 'Notlar' ve 'Arşiv' sekmeleri var (Arşiv "
                    "~(540,1180))."
                ),
                reasoning="Hedef sekmeye gitmek için uygulamayı açıyorum.",
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 540, "y": 1180},
                result=(
                    "[sonuç] ÇÖKME: uygulama kapandı, launcher'a düştük; "
                    "'NotDefteri durduruldu' diyaloğu göründü."
                ),
                reasoning=(
                    "Alt bardaki Arşiv sekmesinin merkezi (540,1180); "
                    "sekmeye dokunuyorum."
                ),
            ),
            AgenticStep(
                tool="android_logcat",
                args={"max_lines": 150},
                result=(
                    "[sonuç] FATAL EXCEPTION main: JSONDecodeError — "
                    "files/archive_cache.json satır 1 bozuk; ArchiveTab "
                    "onCreate içinde parse patlıyor."
                ),
                reasoning=(
                    "Dokunuş uygulamayı çökertti; körlemesine yeniden "
                    "açmak aynı çökmeyi üretir. Önce logcat'ten çökme "
                    "nedenini okuyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_force_stop",
                args={"package": "com.example.notdefteri"},
                result="[sonuç] Süreç durduruldu; çökme diyaloğu kapandı.",
                reasoning=(
                    "Teşhis: bozuk yerel cache dosyası. Temizlik öncesi "
                    "süreci tamamen durdurup temiz bir zemin alıyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_clear_data",
                args={"package": "com.example.notdefteri"},
                result=(
                    "[sonuç] Uygulama verisi ve cache temizlendi "
                    "(archive_cache.json dahil)."
                ),
                reasoning=(
                    "Çökmenin kökü archive_cache.json'daki bozuk kayıt; "
                    "notlar bulutla senkron olduğundan yerel veriyi silmek "
                    "veri kaybettirmez, sadece bozuk cache'i yok eder."
                ),
            ),
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.notdefteri"},
                result=(
                    "[sonuç] Uygulama temiz açıldı; giriş oturumu bulut "
                    "üzerinden geri geldi, ana liste senkronla doldu."
                ),
                reasoning=(
                    "Bozuk cache gitti; uygulamayı yeniden başlatıp aynı "
                    "akışı bu kez temiz durumda deniyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 540, "y": 1180},
                result=(
                    "[sonuç] Arşiv sekmesi açıldı; 23 arşivlenmiş not "
                    "listelendi, çökme yok."
                ),
                reasoning=(
                    "İlk denemede çökerten dokunuşu tekrar ediyorum — "
                    "onarımın gerçekten işe yaradığını ancak aynı adım "
                    "kanıtlar."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Arşiv sekmesi bozuk cache yüzünden çökertiyordu; "
                        "logcat teşhisi + clear_data sonrası sekme 23 notla "
                        "sorunsuz açıldı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Çökme kökten giderildi ve aynı adımla kanıtlandı.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 6. mind_recall boş dönüyor -> session_state'e düş -> operatör
    #    varsayılanıyla ilerle -> hafızayı geriye doldur
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="recall_empty_session_state_fallback",
        goal=(
            "[görev] Operatör: 'apps/fieldnote işine her zamanki CLI ile "
            "başla.' Hangi CLI olduğu bu oturumda söylenmedi."
        ),
        steps=[
            AgenticStep(
                tool="mind_recall",
                args={
                    "query": "apps/fieldnote workspace tercih edilen cli",
                    "top_k": 3,
                },
                result=(
                    "[sonuç] BOŞ: eşleşen hafıza notu yok (0 sonuç)."
                ),
                reasoning=(
                    "'Her zamanki CLI' geçmiş bir tercihe işaret ediyor; "
                    "önce uzun süreli hafızada bu tercihi arıyorum."
                ),
            ),
            AgenticStep(
                tool="session_state",
                args={},
                result=(
                    "[sonuç] Oturum: aktif cli=claude (kota %62 dolu), son "
                    "3 fieldnote görevi de claude ile koşulmuş; workspace "
                    "override kaydı yok."
                ),
                reasoning=(
                    "Hafıza boş döndü — tercih hiç not edilmemiş. Tahmin "
                    "etmek yerine ikinci kaynağa, oturum durumundaki fiili "
                    "kullanım izine bakıyorum."
                ),
            ),
            AgenticStep(
                tool="set_cli_override",
                args={"workspace": "apps/fieldnote", "cli": "claude"},
                result=(
                    "[sonuç] apps/fieldnote için cli=claude override "
                    "yazıldı."
                ),
                reasoning=(
                    "Oturum izi net: fieldnote işleri hep claude ile "
                    "koşmuş. 'Her zamanki'ni buna bağlayıp override'ı "
                    "kalıcılaştırıyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "apps/fieldnote tercih edilen CLI: claude (oturum "
                        "izinden çıkarıldı, 2026-07-03; operatör 'her "
                        "zamanki' dedi)."
                    ),
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "İlk adımda recall boş dönmüştü; aynı soruya bir daha "
                    "düşmemek için çıkardığım tercihi hafızaya geri "
                    "yazıyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Hafıza boştu; oturum izinden claude tercihi "
                        "çıkarıldı, override kuruldu ve hafıza geriye "
                        "dolduruldu."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Workspace doğru CLI'ya bağlandı; hazırlık tamam.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 7. Akış ortasında 429: kota anlık görüntüsü -> boş kapasiteli
    #    CLI'ya rotasyon -> düşen çağrıyı tekrarla -> işi bitir
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="rate_limited_rotate_and_retry",
        goal=(
            "[görev] arketic/fieldnote-app açık issue'ları taranıp #58 "
            "numaralı çökme raporuna triage yorumu yazılacak."
        ),
        steps=[
            AgenticStep(
                tool="github_issue_list",
                args={"repo": "arketic/fieldnote-app", "state": "open"},
                result=(
                    "[sonuç] 12 açık issue; #58 'girişte çökme' etiketsiz "
                    "ve triage bekliyor."
                ),
                reasoning="Triage için önce açık issue resmini alıyorum.",
            ),
            AgenticStep(
                tool="github_issue_view",
                args={"repo": "arketic/fieldnote-app", "number": 58},
                result=(
                    "[sonuç] HATA 429: rate limit — istek reddedildi "
                    "(aktif cli: claude, pencere dolu)."
                ),
                reasoning=(
                    "#58 triage bekliyor; yorum yazmadan önce içeriğini "
                    "okumam gerek."
                ),
            ),
            AgenticStep(
                tool="quota_snapshot",
                args={},
                result=(
                    "[sonuç] claude: 5s penceresi %100 (reset 42 dk); "
                    "codex: %38 dolu; gemini: %71 dolu."
                ),
                reasoning=(
                    "429 aktif CLI'nın kotasını işaret ediyor; körlemesine "
                    "tekrar denemek yine 429 üretir. Önce tüm CLI'ların "
                    "kota resmini çekiyorum."
                ),
            ),
            AgenticStep(
                tool="rotate_to",
                args={
                    "cli_id": "codex",
                    "reason": (
                        "claude 5 saatlik kotası dolu (reset 42 dk); "
                        "codex %38 ile en boş kapasite"
                    ),
                },
                result="[sonuç] Aktif CLI codex'e geçti.",
                reasoning=(
                    "Snapshot 42 dk beklemeye gerek olmadığını gösteriyor: "
                    "codex'te bolca pay var. Beklemek yerine rotasyonla "
                    "akışı kesintisiz sürdürüyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_view",
                args={"repo": "arketic/fieldnote-app", "number": 58},
                result=(
                    "[sonuç] #58 içeriği geldi: Pixel 6 / Android 14, "
                    "girişte NullPointerException; logcat çıktısı ekli, "
                    "PR #91'deki offline-sync koduna işaret ediyor."
                ),
                reasoning=(
                    "Rotasyon tamam; 429 ile düşen çağrının aynısını yeni "
                    "CLI üzerinden tekrarlıyorum."
                ),
            ),
            AgenticStep(
                tool="github_issue_comment",
                args={
                    "repo": "arketic/fieldnote-app",
                    "number": 58,
                    "body": (
                        "Triage: çökme girişteki NullPointerException; ekli "
                        "logcat offline-sync (PR #91) değişikliğine işaret "
                        "ediyor. Öncelik: yüksek. Repro: Pixel 6 / Android "
                        "14."
                    ),
                },
                result="[sonuç] Yorum #58'e eklendi.",
                reasoning=(
                    "Issue içeriği okundu; teşhisi triage yorumu olarak "
                    "işliyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "429 rotasyonla aşıldı (claude -> codex); #58 "
                        "okundu ve triage yorumu yazıldı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Triage yorumu yerinde; akış kesintisiz bitti.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 8. 429 ama rotasyon imkânsız: TÜM CLI'lar dolu -> en erken
    #    reset'e kadar uyu -> uyanınca düşen çağrıyı tekrarla
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="all_quotas_full_sleep_resume",
        goal=(
            "[görev] arketic/fieldnote-app deposunda günlük özet raporu "
            "PR'ı açılacak (chore/daily-report dalı hazır)."
        ),
        steps=[
            AgenticStep(
                tool="github_pr_create",
                args={
                    "repo": "arketic/fieldnote-app",
                    "title": "docs: günlük özet raporu (2 Temmuz)",
                    "body": (
                        "2 Temmuz günlük özeti: merge edilen PR'lar, açık "
                        "triage kalemleri ve kota kullanımı."
                    ),
                    "head": "chore/daily-report",
                    "base": "main",
                },
                result=(
                    "[sonuç] HATA 429: rate limit — istek reddedildi "
                    "(aktif cli: claude)."
                ),
                reasoning=(
                    "Dal hazır; raporu PR olarak açıyorum."
                ),
            ),
            AgenticStep(
                tool="quota_snapshot",
                args={},
                result=(
                    "[sonuç] HEPSİ DOLU — claude: 5s penceresi dolu, reset "
                    "17:00 TSİ (epoch 1783087200); codex: 7g penceresi "
                    "dolu; gemini: günlük limit dolu. En erken reset: "
                    "claude."
                ),
                reasoning=(
                    "429 geldi; rotasyon bir seçenek mi diye tüm CLI'ların "
                    "kota resmine bakıyorum."
                ),
            ),
            AgenticStep(
                tool="sleep_until",
                args={
                    "epoch_seconds": 1783087200,
                    "kind": "five_hour",
                    "reason": (
                        "tüm CLI kotaları dolu; en erken reset claude "
                        "17:00 TSİ — rotasyon imkânsız, bekleme tek yol"
                    ),
                },
                result=(
                    "[sonuç] 17:00 TSİ'de uyanıldı; claude kotası "
                    "tazelendi."
                ),
                reasoning=(
                    "Snapshot rotasyona yer bırakmadı: üç CLI da dolu. "
                    "Boşa deneme yakmak yerine en erken reset olan "
                    "claude'un saatine kadar planlı uyuyorum."
                ),
            ),
            AgenticStep(
                tool="github_pr_create",
                args={
                    "repo": "arketic/fieldnote-app",
                    "title": "docs: günlük özet raporu (2 Temmuz)",
                    "body": (
                        "2 Temmuz günlük özeti: merge edilen PR'lar, açık "
                        "triage kalemleri ve kota kullanımı."
                    ),
                    "head": "chore/daily-report",
                    "base": "main",
                },
                result="[sonuç] PR #104 açıldı (chore/daily-report -> main).",
                reasoning=(
                    "Kota tazelendi; 429 ile düşen PR açma çağrısını "
                    "birebir tekrarlıyorum."
                ),
            ),
            AgenticStep(
                tool="notify_telegram",
                args={
                    "message": (
                        "Günlük rapor PR #104 açıldı. Not: tüm CLI kotaları "
                        "dolduğu için ~40 dk kota beklemesi yaşandı."
                    ),
                    "level": "info",
                },
                result="[sonuç] Bildirim iletildi.",
                reasoning=(
                    "İş bitti ama gecikmeli; operatör gecikmenin nedenini "
                    "bildirimden görsün."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Tüm kotalar doluydu; reset'e kadar uyunup PR #104 "
                        "açıldı, gecikme operatöre bildirildi."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="PR açıldı ve gecikme raporlandı; görev tamam.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 9. Bot engeli: sayfa 'olağan dışı trafik' duvarı -> stealth aç
    #    -> yeniden git -> fiyatı oku -> nota işle
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="bot_blocked_enable_stealth_retry",
        goal=(
            "[görev] ornekmagaza.com'daki 'Akıllı Saat X2' ürününün güncel "
            "fiyatı okunup rakip fiyat notuna işlenecek."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={
                    "url": "https://www.ornekmagaza.com/urun/akilli-saat-x2",
                },
                result=(
                    "[sonuç] ENGELLENDİ: ürün yerine doğrulama sayfası — "
                    "'Olağan dışı trafik algılandı, robot olmadığınızı "
                    "doğrulayın' (challenge duvarı)."
                ),
                reasoning="Ürün sayfasına doğrudan gidiyorum.",
            ),
            AgenticStep(
                tool="browser_enable_stealth",
                args={},
                result=(
                    "[sonuç] Stealth etkin: webdriver izleri ve headless "
                    "parmak izi maskelendi."
                ),
                reasoning=(
                    "Challenge duvarı otomasyon parmak izini yakaladı "
                    "demek; aynı imzayla tekrar denemek yine duvara çarpar. "
                    "Önce stealth modunu açıyorum."
                ),
            ),
            AgenticStep(
                tool="browser_navigate",
                args={
                    "url": "https://www.ornekmagaza.com/urun/akilli-saat-x2",
                },
                result=(
                    "[sonuç] Ürün sayfası bu kez yüklendi: 'Akıllı Saat "
                    "X2', fiyat bloğu görünüyor."
                ),
                reasoning=(
                    "Parmak izi maskelendi; engellenen navigasyonu temiz "
                    "bir sayfa yüklemesiyle tekrarlıyorum."
                ),
            ),
            AgenticStep(
                tool="browser_text_content",
                args={"target": ".price-now"},
                result="[sonuç] '.price-now' içeriği: '₺4.299'.",
                reasoning=(
                    "Sayfa gerçek içerikle geldi; hedef veriyi fiyat "
                    "seçicisinden okuyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "Rakip fiyat: Akıllı Saat X2 = 4.299 TL "
                        "(ornekmagaza.com, 2026-07-03). Not: site bot "
                        "duvarı kullanıyor; stealth şart."
                    ),
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Fiyat okundu; hem veriyi hem de 'bu siteye stealth "
                    "ile gidilir' dersini hafızaya işliyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Bot duvarı stealth ile aşıldı; fiyat 4.299 TL "
                        "okundu ve nota işlendi."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Hedef veri alındı ve kalıcılaştı; bitti.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 10. 0 sonuç dallanması: networkidle bekle -> yeniden sorgula ->
    #     hâlâ 0 -> snapshot boş-durum + yanlış yıl filtresi gösteriyor
    #     -> operatöre sor -> cevaba göre ilerle
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="zero_rows_requery_then_ask_user",
        goal=(
            "[görev] Tedarikçi panelinde 'temmuz' dönemine ait faturalar "
            "listelenecek; operatör yıl belirtmedi."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={
                    "url": (
                        "https://portal.tedarikci.example.com/faturalar"
                        "?ay=temmuz"
                    ),
                },
                result=(
                    "[sonuç] Sayfa açıldı; fatura tablosunun gövdesi boş "
                    "görünüyor."
                ),
                reasoning="Fatura listesine dönem filtresiyle gidiyorum.",
            ),
            AgenticStep(
                tool="browser_query_selector_all",
                args={"target": "table.invoices tbody tr"},
                result="[sonuç] 0 eşleşme: tabloda hiç satır yok.",
                reasoning=(
                    "Satırları saymak için tablo satırlarını sorguluyorum."
                ),
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "networkidle"},
                result="[sonuç] Ağ boşta; bekleyen XHR kalmadı.",
                reasoning=(
                    "0 satır geldi ama satırlar XHR ile geç dolabilir; "
                    "boş diye rapor etmeden önce ağın bitmesini bekliyorum."
                ),
            ),
            AgenticStep(
                tool="browser_query_selector_all",
                args={"target": "table.invoices tbody tr"},
                result="[sonuç] HÂLÂ 0 eşleşme.",
                reasoning=(
                    "Ağ sakin; geç yükleme hipotezini test etmek için aynı "
                    "sorguyu tekrarlıyorum."
                ),
            ),
            AgenticStep(
                tool="browser_dom_snapshot",
                args={},
                result=(
                    "[sonuç] Snapshot: tabloda .empty-state var — 'Bu "
                    "dönem için fatura bulunamadı'. SÜRPRİZ: filtre çipi "
                    "'Temmuz 2025' gösteriyor — panel yılı varsayılan "
                    "olarak geçen yıla kurmuş."
                ),
                reasoning=(
                    "İki sorgu da 0 döndü: sorun zamanlama değil. Liste "
                    "gerçekten mi boş yoksa seçici/filtre mi yanlış, DOM "
                    "snapshot ile ayırt ediyorum."
                ),
            ),
            AgenticStep(
                tool="AskUserQuestion",
                args={
                    "questions": [
                        {
                            "question": (
                                "Panel 'temmuz' filtresini Temmuz 2025 "
                                "olarak açtı ve o dönem boş. Hangi dönemi "
                                "listeleyeyim?"
                            ),
                            "header": "Fatura dönemi",
                            "options": [
                                {
                                    "label": "Temmuz 2026",
                                    "description": (
                                        "İçinde bulunduğumuz ay; büyük "
                                        "ihtimalle kastedilen dönem"
                                    ),
                                },
                                {
                                    "label": "Temmuz 2025",
                                    "description": (
                                        "Panelin varsayılanı; bu dönemde "
                                        "kayıt yok, boş rapor dönerim"
                                    ),
                                },
                            ],
                        }
                    ],
                },
                result="[sonuç] Operatör 'Temmuz 2026' seçti.",
                reasoning=(
                    "Snapshot belirsizliği ortaya çıkardı: operatör "
                    "'temmuz' dedi ama panel 2025'i açtı. Yanlış dönemi "
                    "raporlamak yerine yıl seçimini operatöre soruyorum."
                ),
            ),
            AgenticStep(
                tool="browser_navigate",
                args={
                    "url": (
                        "https://portal.tedarikci.example.com/faturalar"
                        "?ay=2026-07"
                    ),
                },
                result=(
                    "[sonuç] Sayfa yeniden yüklendi; filtre çipi 'Temmuz "
                    "2026', tabloda 14 fatura satırı görünüyor."
                ),
                reasoning=(
                    "Operatör 2026'yı seçti; filtreyi yıl dahil açık "
                    "biçimde vererek sayfayı yeniden açıyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Boş liste yanlış yıl varsayılanından "
                        "kaynaklanıyordu; operatör onayıyla Temmuz 2026 "
                        "açıldı, 14 fatura listelendi."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Doğru dönem listelendi; görev hedefe ulaştı.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 11. iOS öğe bulunamıyor (ekran dışı) -> kaydır -> yeniden bul ->
    #     frame merkezine tıkla -> metinle doğrula
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="ios_element_offscreen_scroll_find",
        goal=(
            "[görev] SağlıkTakip iOS uygulamasında profil ekranındaki "
            "'Verileri Dışa Aktar' düğmesine basılacak."
        ),
        steps=[
            AgenticStep(
                tool="ios_app_launch",
                args={"bundle_id": "com.arketic.saglik"},
                result=(
                    "[sonuç] Uygulama profil ekranında açıldı; uzun bir "
                    "ayar listesi görünüyor."
                ),
                reasoning="Hedef düğme profil ekranında; uygulamayı açıyorum.",
            ),
            AgenticStep(
                tool="ios_find_element",
                args={
                    "by": "accessibility id",
                    "value": "export_data_button",
                },
                result=(
                    "[sonuç] BAŞARISIZ: NoSuchElement — "
                    "'export_data_button' görünür hiyerarşide yok."
                ),
                reasoning=(
                    "Düğmeyi koordinat tahmini yerine accessibility id ile "
                    "arıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_scroll",
                args={"direction": "down", "amount": 600},
                result=(
                    "[sonuç] Liste kaydı; alt bölümde 'Veri Yönetimi' "
                    "başlığı ve yeni satırlar göründü."
                ),
                reasoning=(
                    "Öğe bulunamadı ama liste uzun: düğme büyük ihtimalle "
                    "ekranın altında, görünür hiyerarşiye girmemiş. Yok "
                    "saymadan önce aşağı kaydırıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_find_element",
                args={
                    "by": "accessibility id",
                    "value": "export_data_button",
                },
                result=(
                    "[sonuç] BULUNDU: frame x=40 y=610 w=680 h=56 — merkez "
                    "(380, 638)."
                ),
                reasoning=(
                    "Kaydırma yeni satırlar getirdi; aynı aramayı görünür "
                    "hâle gelen bölge üzerinde tekrarlıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_click",
                args={"x": 380, "y": 638},
                result=(
                    "[sonuç] Düğmeye basıldı; dışa aktarma sayfası açıldı."
                ),
                reasoning=(
                    "Frame merkezine ((40+680/2), (610+56/2)) = (380,638) "
                    "tıklıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_screen_text",
                args={},
                result=(
                    "[sonuç] Ekran metni: 'Dışa aktarma hazır: "
                    "saglik_verileri.csv'."
                ),
                reasoning=(
                    "Sayfa açıldı görünüyor; doğru akışın tetiklendiğini "
                    "ekran metniyle doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Düğme ekran dışındaydı; kaydırma sonrası bulundu, "
                        "basıldı ve dışa aktarma ekranı doğrulandı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Hedef eylem kanıtla tamamlandı.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 12. Odak çalınması: yazarken güncelleme diyaloğu odağı kapıyor ->
    #     aktif uygulamayı teşhis et -> diyaloğu kapat -> yeniden
    #     odaklan -> metni tekrar yaz
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="desktop_focus_stolen_retype",
        goal=(
            "[görev] Masaüstünde Notlar uygulamasına sprint toplantı "
            "özeti yazılacak."
        ),
        steps=[
            AgenticStep(
                tool="desktop_list_windows",
                args={},
                result=(
                    "[sonuç] Açık pencereler: Notlar, Tarayıcı, Slack."
                ),
                reasoning=(
                    "Yazmadan önce Notlar penceresinin açık olduğunu "
                    "doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={"app_name": "Notlar"},
                result="[sonuç] Odak Notlar penceresinde; imleç not alanında.",
                reasoning="Metnin doğru yere gitmesi için önce odak alıyorum.",
            ),
            AgenticStep(
                tool="desktop_type",
                args={
                    "text": (
                        "14:00 sprint değerlendirme: kota paneli demo "
                        "edildi, iki aksiyon çıktı."
                    ),
                },
                result=(
                    "[sonuç] SÜRPRİZ: metin Notlar'da görünmüyor; yazım "
                    "sırasında ekranda bir diyalog belirdi."
                ),
                reasoning="Odak Notlar'da; özeti yazıyorum.",
            ),
            AgenticStep(
                tool="desktop_get_active_app",
                args={},
                result=(
                    "[sonuç] Aktif uygulama: 'Sistem Güncelleme' diyaloğu "
                    "— yazım sırasında odağı çalmış; tuş vuruşları ona "
                    "gitmiş."
                ),
                reasoning=(
                    "Metin hedefte yok ve bir diyalog belirdi: odak "
                    "çalınmış olabilir. Tahmin yerine aktif uygulamayı "
                    "sorguluyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "escape"},
                result=(
                    "[sonuç] Güncelleme diyaloğu kapandı; masaüstü "
                    "temizlendi."
                ),
                reasoning=(
                    "Teşhis net: güncelleme diyaloğu odağı kapıp tuş "
                    "vuruşlarını yuttu. Önce bu diyaloğu escape ile "
                    "kapatıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={"app_name": "Notlar"},
                result=(
                    "[sonuç] Odak yeniden Notlar'da; not alanı boş — "
                    "kaybolan metin buraya hiç düşmemiş."
                ),
                reasoning=(
                    "Diyalog kapandı ama odak hâlâ belirsiz; yazmadan önce "
                    "Notlar'a açıkça yeniden odaklanıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_type",
                args={
                    "text": (
                        "14:00 sprint değerlendirme: kota paneli demo "
                        "edildi, iki aksiyon çıktı."
                    ),
                },
                result=(
                    "[sonuç] Metin bu kez Notlar'da görünüyor; satır "
                    "kaydedildi."
                ),
                reasoning=(
                    "Odak doğrulandı ve alan boş; yutulan metni birebir "
                    "yeniden yazıyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "Güncelleme diyaloğu odağı çalıp metni yutmuştu; "
                        "diyalog kapatıldı, yeniden odaklanıldı ve özet "
                        "Notlar'a yazıldı."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="Metin doğru pencerede görünür; görev tamam.",
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # 13. Yanlış workflow adı: 404 -> listele -> doğru adla tekrar
    #     tetikle -> adı hafızaya işle
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="workflow_404_list_then_retry",
        goal=(
            "[görev] arketic/quota-panel deposunda CI main dalı üzerinde "
            "elle tetiklenecek."
        ),
        steps=[
            AgenticStep(
                tool="github_workflow_run",
                args={
                    "repo": "arketic/quota-panel",
                    "workflow": "ci.yml",
                    "ref": "main",
                },
                result=(
                    "[sonuç] HATA 404: 'ci.yml' adında workflow yok."
                ),
                reasoning=(
                    "CI dosyası çoğu depoda ci.yml'dir; bu adla "
                    "tetiklemeyi deniyorum."
                ),
            ),
            AgenticStep(
                tool="github_workflow_list",
                args={"repo": "arketic/quota-panel"},
                result=(
                    "[sonuç] Mevcut workflow'lar: build-test.yml (CI), "
                    "release.yml (yayın)."
                ),
                reasoning=(
                    "404, dosya adının tahminimden farklı olduğunu "
                    "söylüyor; tahmin üstüne tahmin yerine gerçek listeyi "
                    "çekiyorum."
                ),
            ),
            AgenticStep(
                tool="github_workflow_run",
                args={
                    "repo": "arketic/quota-panel",
                    "workflow": "build-test.yml",
                    "ref": "main",
                },
                result=(
                    "[sonuç] build-test.yml tetiklendi; run #212 kuyruğa "
                    "girdi."
                ),
                reasoning=(
                    "Listede CI görevini taşıyan dosya build-test.yml; "
                    "404 alan çağrıyı doğru adla tekrarlıyorum."
                ),
            ),
            AgenticStep(
                tool="mind_note_add",
                args={
                    "content": (
                        "arketic/quota-panel CI workflow dosyası: "
                        "build-test.yml (ci.yml DEĞİL; 404 dersi, "
                        "2026-07-03)."
                    ),
                },
                result="[sonuç] Not kaydedildi.",
                reasoning=(
                    "Aynı 404'e bir daha düşmemek için doğru dosya adını "
                    "hafızaya işliyorum."
                ),
            ),
            AgenticStep(
                tool="mark_done",
                args={
                    "reason": (
                        "ci.yml 404 verdi; liste build-test.yml'i gösterdi, "
                        "CI tetiklendi ve ad hafızaya işlendi."
                    ),
                },
                result="[sonuç] Görev kapatıldı.",
                reasoning="CI kuyruğa girdi; tetikleme görevi tamam.",
            ),
        ],
    ),
]
