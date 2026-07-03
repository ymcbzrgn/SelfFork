"""Authored reasoning scenarios for the phone tools (Android + iOS).

Single-tool-call scenarios that teach the disambiguations a small model
gets wrong. Every scenario carries reasoning: the target explicitly
justifies the chosen tool over its confusable neighbours. Clusters:

* observation -- a11y_tree (structure/coords) vs screenshot (pixels) vs
  screen_text (just the visible text), incl. the "take a screenshot to
  find the button" trap and the empty-tree-on-canvas recovery.
* input -- click / double_click / long_press / swipe / scroll /
  press_button / press_key, incl. the Turkish "kaydır" swipe-vs-scroll
  trap and hardware-key-over-coordinates cases.
* text -- type (append vs clear_first replace) vs clear_text.
* iOS lifecycle -- app_state-driven launch vs activate, background vs
  terminate, incl. the "kapat" resume-test trap.
* install -- install_app vs install_xapk (split APKs) vs uninstall vs
  clear_data ("reinstall for a fresh start" trap).
* simulator/emulator -- boot vs shutdown (preserves data) vs erase
  (factory reset), plus list-first gathering before destructive acts.
* device state -- clipboard get/set, geolocation set/verify,
  orientation get/set, lock/unlock, biometric match vs no_match.
* logs -- logcat (event history) vs dumpsys (live service state) vs
  ios_get_logs, plus the dedicated get_battery over raw dumpsys.
* misc -- deeplink over launch+type, push vs pull direction,
  screenrecord over screenshot for intermittent glitches,
  re-observe instead of blind retry.

The four android app-lifecycle tools are authored elsewhere and are
intentionally absent here. Every row is gated by the builder.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

SCENARIOS: list[ToolScenario] = [
    # ------------------------------------------------------------------
    # OBSERVATION: a11y_tree (structure) vs screenshot (pixels) vs
    # screen_text (just the text)
    # ------------------------------------------------------------------
    ToolScenario(
        tool="android_a11y_tree",
        archetype="screenshot_trap_needs_coords",
        context=(
            "[android] Kargo uygulamasında form dolduruldu. Operatör: "
            "'Ekran görüntüsü al da Gönder butonunun yerini bulalım.'"
        ),
        args={},
        reasoning=(
            "Amaç butonun tıklanabilir koordinatı; ekran görüntüsü sadece "
            "piksel verir, konum bilgisi içermez. Elemanların bounds "
            "değerlerini a11y ağacı taşır, o yüzden a11y_tree."
        ),
        index=0,
    ),
    ToolScenario(
        tool="android_screenshot",
        archetype="visual_render_bug",
        context=(
            "[android] Hata kaydı: 'Onayla butonu yeşil olmalıyken kırmızı "
            "görünüyor, logo da bozuk çiziliyor.' Görsel kanıt isteniyor."
        ),
        args={},
        reasoning=(
            "Renk ve çizim hataları piksel dünyasına ait; a11y ağacı ve "
            "screen_text renk/görsel bilgisi taşımaz. Görsel doğrulama "
            "ancak screenshot ile yapılır."
        ),
        index=1,
    ),
    ToolScenario(
        tool="android_screen_text",
        archetype="read_price_text",
        context=(
            "[android] Sepet ekranı açık. Operatör: 'Ekranda toplam tutar "
            "ne yazıyor, sadece değeri söyle.'"
        ),
        args={},
        reasoning=(
            "Yalnızca görünen metin isteniyor; koordinat gerekmez, görsel "
            "gerekmez. Tam a11y ağacı gereksiz gürültü, screenshot ise "
            "okunamaz piksel. En dar doğru araç screen_text."
        ),
        index=2,
    ),
    ToolScenario(
        tool="ios_screenshot",
        archetype="canvas_tree_empty",
        context=(
            "[ios] WebGL tabanlı oyun ekranında ios_a11y_tree boş bir "
            "kök düğüm döndürdü. Operatör: 'Ekranda skor kaç, bak.'"
        ),
        args={},
        reasoning=(
            "Canvas içeriği a11y ağacına yansımıyor; screen_text de aynı "
            "ağaçtan beslendiği için boş kalır. Tek bilgi kaynağı "
            "piksellerin kendisi: screenshot alıyorum."
        ),
        index=3,
    ),
    ToolScenario(
        tool="ios_screen_text",
        archetype="read_otp_code",
        context=(
            "[ios] Banka uygulaması SMS doğrulama kodunu ekranda gösterdi. "
            "Operatör: 'Kodu oku, birazdan öbür cihaza gireceğiz.'"
        ),
        args={},
        reasoning=(
            "İhtiyaç ekrandaki metin değeri; ağacın tam yapısı da piksel "
            "görüntüsü de fazlalık. screen_text a11y ağacından görünen "
            "metni doğrudan çıkarır."
        ),
        index=4,
    ),
    ToolScenario(
        tool="ios_find_element",
        archetype="single_element_lookup",
        context=(
            "[ios] Geliştirici, giriş düğmesinin accessibility id'sinin "
            "'loginButton' olduğunu söyledi. Sadece bu elemanın konumu ve "
            "durumu lazım."
        ),
        args={"value": "loginButton", "by": "accessibility id"},
        reasoning=(
            "Tek ve kimliği bilinen bir eleman aranıyor; tüm ekranın a11y "
            "ağacını dökmek israf. find_element accessibility id ile "
            "doğrudan o elemanı getirir."
        ),
        index=5,
    ),
    # ------------------------------------------------------------------
    # INPUT: click / double_click / long_press / swipe / scroll /
    # press_key / press_button / pinch
    # ------------------------------------------------------------------
    ToolScenario(
        tool="android_click",
        archetype="tap_send_button",
        context=(
            "[android] a11y ağacında 'Gönder' butonunun merkezi (540, "
            "1710) olarak okundu. Operatör: 'Formu gönder.'"
        ),
        args={"x": 540, "y": 1710},
        reasoning=(
            "Koordinatı bilinen bir butona tek dokunuş yeterli; menü "
            "açılmayacak (long_press değil), çift dokunuş yan etki "
            "yaratır. Düz click doğru araç."
        ),
        index=6,
    ),
    ToolScenario(
        tool="android_double_click",
        archetype="double_tap_like",
        context=(
            "[android] Instagram'da fotoğraf (540, 1000) merkezinde. "
            "Operatör: 'Bu fotoğrafı beğen; tek dokunuş sadece arayüzü "
            "gizleyip açıyor.'"
        ),
        args={"x": 540, "y": 1000},
        reasoning=(
            "Beğeni jesti çift dokunuş; tek click burada farklı bir "
            "davranış (arayüz gizleme) tetikliyor. Amaca ancak "
            "double_click ulaşır."
        ),
        index=7,
    ),
    ToolScenario(
        tool="android_long_press",
        archetype="message_context_menu",
        context=(
            "[android] WhatsApp sohbetinde kopyalanacak mesaj (540, 860) "
            "konumunda. Operatör: 'Mesajı kopyalama menüsünü aç.'"
        ),
        args={"x": 540, "y": 860, "duration_ms": 800},
        reasoning=(
            "Bağlam menüsü basılı tutmayla açılır; kısa click mesajı "
            "seçmez, sadece dokunur. Menüyü güvenle açmak için 800 ms "
            "long_press kullanıyorum."
        ),
        index=8,
    ),
    ToolScenario(
        tool="android_swipe",
        archetype="kaydir_delete_row_trap",
        context=(
            "[android] Gmail listesinde silinecek e-posta satırı y=640 "
            "hizasında. Operatör: 'Bu maili sola kaydır, silinsin.'"
        ),
        args={"start_x": 980, "start_y": 640, "end_x": 120, "end_y": 640},
        reasoning=(
            "'Kaydır' dense de bu bir liste kaydırma değil; tek satır "
            "üzerinde hedefli bir jest. scroll tüm yüzeyi oynatır ve "
            "satır aksiyonunu tetiklemez; koordinatlı swipe gerekir."
        ),
        index=9,
    ),
    ToolScenario(
        tool="android_scroll",
        archetype="kaydir_list_scroll",
        context=(
            "[android] Ayarlar listesi uzun; 'Geliştirici seçenekleri' "
            "ekranda görünmüyor. Operatör: 'Aşağı kaydır da bulalım.'"
        ),
        args={"direction": "down"},
        reasoning=(
            "Amaç listenin devamını görünür kılmak; belirli bir satıra "
            "jest yapılmıyor. Koordinat hesaplamaya gerek olmayan bu iş "
            "için yön bazlı scroll, hedefli swipe'tan doğru."
        ),
        index=10,
    ),
    ToolScenario(
        tool="android_press_key",
        archetype="hardware_back",
        context=(
            "[android] Yanlış ürün sayfası açıldı; ekrandaki geri okunun "
            "koordinatı bilinmiyor. Operatör: 'Önceki ekrana dön.'"
        ),
        args={"key": "back"},
        reasoning=(
            "Koordinatsız click atılamaz; Android'de donanım geri tuşu "
            "her ekranda çalışır ve gözlem gerektirmez. press_key back "
            "en sağlam dönüş yolu."
        ),
        index=11,
    ),
    ToolScenario(
        tool="android_press_button",
        archetype="lock_screen_button",
        context=(
            "[android] Test bitti, ekran açık kaldı. Operatör: 'Cihazı "
            "kilitle, öyle bırak.'"
        ),
        args={"button": "lock"},
        reasoning=(
            "Kilitleme donanım kilit düğmesinin işi; press_key'in "
            "seçenekleri arasında lock yok, press_button'da var. Ekranda "
            "tıklanacak bir kilit düğmesi de bulunmuyor."
        ),
        index=12,
    ),
    ToolScenario(
        tool="android_pinch",
        archetype="map_pinch_zoom",
        context=(
            "[android] Haritalar açık, mahalle detayı görünmüyor. "
            "Operatör: 'İki parmakla yakınlaştır, sokak adları çıksın.'"
        ),
        args={"scale": 2.0},
        reasoning=(
            "Kontrollü yakınlaştırma iki parmak jesti ister; scale > 1 "
            "yakınlaştırır. Çift dokunuş sabit kademeli zoom yapar, "
            "swipe ise haritayı sadece kaydırır."
        ),
        index=13,
    ),
    ToolScenario(
        tool="ios_swipe",
        archetype="slider_drag",
        context=(
            "[ios] Ses ayarı slider'ının tutamacı (80, 500) noktasında; "
            "hedef konum (300, 500). Operatör: 'Sesi yükselt, tutamacı "
            "sağa çek.'"
        ),
        args={
            "start_x": 80,
            "start_y": 500,
            "end_x": 300,
            "end_y": 500,
            "duration_ms": 600,
        },
        reasoning=(
            "Tutamacı sürüklemek başlangıç ve bitiş noktası belli bir "
            "jest; scroll yüzeyi kaydırır, tutamacı yakalamaz. Yavaş bir "
            "koordinatlı swipe slider'ı taşır."
        ),
        index=14,
    ),
    ToolScenario(
        tool="ios_press_button",
        archetype="invoke_siri",
        context=(
            "[ios] Sesli asistan entegrasyonu test edilecek. Operatör: "
            "'Siri'yi tetikle.'"
        ),
        args={"button": "siri"},
        reasoning=(
            "Siri ekrandaki bir öğe değil, donanım düğmesiyle çağrılır; "
            "click için koordinat da yok. press_button'un siri değeri "
            "tam bunu yapar."
        ),
        index=15,
    ),
    ToolScenario(
        tool="ios_terminate_keyboard",
        archetype="keyboard_blocks_button_trap",
        context=(
            "[ios] Form dolduruldu ama 'Kaydet' butonu açık klavyenin "
            "altında kaldı. Operatör: 'Butona ulaşmak için aşağı kaydır.'"
        ),
        args={},
        reasoning=(
            "Buton sayfanın dışında değil, klavyenin arkasında; scroll "
            "klavyeyi kaldırmaz. Önce klavyeyi kapatmak butonu görünür "
            "kılar: terminate_keyboard."
        ),
        index=16,
    ),
    # ------------------------------------------------------------------
    # TEXT: type (append / clear_first replace) vs clear_text
    # ------------------------------------------------------------------
    ToolScenario(
        tool="android_type",
        archetype="append_text",
        context=(
            "[android] Not alanında 'Toplantı saat 14' yazılı, imleç "
            "sonda. Operatör: 'Sonuna \":30, B blok\" ekle.'"
        ),
        args={"text": ":30, B blok"},
        reasoning=(
            "Mevcut metin korunacak, yalnızca ekleme yapılacak; "
            "clear_first açılırsa notun tamamı silinir. Düz type ile "
            "imlecin olduğu yerden yazıyorum."
        ),
        index=17,
    ),
    ToolScenario(
        tool="android_type",
        archetype="replace_atomic_trap",
        context=(
            "[android] Adres alanında eski adres duruyor. Operatör: "
            "'Önce alandaki eski adresi sil, sonra yenisini yaz: "
            "Moda Cad. 15, Kadıköy.'"
        ),
        args={"text": "Moda Cad. 15, Kadıköy", "clear_first": True},
        reasoning=(
            "Operatör iki adım tarif etse de type'ın clear_first "
            "parametresi sil+yaz işini tek atomik çağrıda yapar; ayrı "
            "clear_text çağrısı gereksiz bir ara adım olur."
        ),
        index=18,
    ),
    ToolScenario(
        tool="android_clear_text",
        archetype="empty_field_only",
        context=(
            "[android] Arama kutusunda 'kablosuz kulaklık' yazıyor. "
            "Operatör: 'Arama kutusunu boşalt, öyle kalsın; yeni bir şey "
            "yazma.'"
        ),
        args={},
        reasoning=(
            "Hedef yalnızca alanı boşaltmak; yazılacak yeni metin yok. "
            "type metin ister, boş yazmak onun işi değil; clear_text "
            "alanı tek başına temizler."
        ),
        index=19,
    ),
    ToolScenario(
        tool="ios_clear_text",
        archetype="wrong_text_wipe",
        context=(
            "[ios] Kullanıcı adı alanına yanlışlıkla e-posta yazıldı. "
            "Operatör: 'Yanlış yazdın, hepsini sil; doğrusunu sonra "
            "kararlaştıracağız.'"
        ),
        args={},
        reasoning=(
            "Yeni metin henüz belli değil, sadece silme isteniyor; "
            "clear_first ancak type ile birlikte yeni metin varken "
            "anlamlı. Alanı clear_text ile boşaltıyorum."
        ),
        index=20,
    ),
    # ------------------------------------------------------------------
    # iOS LIFECYCLE: app_state -> launch / activate; background vs
    # terminate
    # ------------------------------------------------------------------
    ToolScenario(
        tool="ios_app_state",
        archetype="check_before_foreground",
        context=(
            "[ios] Operatör: 'Safari'yi öne getir.' Safari'nin çalışıp "
            "çalışmadığına dair bu oturumda hiçbir gözlem yok."
        ),
        args={"bundle_id": "com.apple.mobilesafari"},
        reasoning=(
            "Launch ile activate arasındaki seçim uygulamanın durumuna "
            "bağlı; körlemesine seçmek yanlış araca düşürür. Önce "
            "app_state: 1 dönerse launch, arka plandaysa activate."
        ),
        index=21,
    ),
    ToolScenario(
        tool="ios_app_launch",
        archetype="not_running_foreground_trap",
        context=(
            "[ios] ios_app_state 'com.getir.customer' için 1 döndürdü "
            "(yüklü ama çalışmıyor). Operatör: 'Getir'i öne getir.'"
        ),
        args={"bundle_id": "com.getir.customer"},
        reasoning=(
            "'Öne getir' activate'i çağrıştırıyor ama durum 1: ortada "
            "öne alınacak bir süreç yok. Çalışmayan uygulama ancak "
            "launch ile soğuk başlatılır."
        ),
        index=22,
    ),
    ToolScenario(
        tool="ios_app_activate",
        archetype="background_to_front",
        context=(
            "[ios] ios_app_state 'com.spotify.client' için 3 döndürdü "
            "(arka planda, müzik çalıyor). Operatör: 'Spotify'a dön, "
            "çalma listesini değiştireceğiz.'"
        ),
        args={"bundle_id": "com.spotify.client"},
        reasoning=(
            "Durum 3: uygulama arka planda canlı ve oturumu korunmalı. "
            "Yeniden launch etmek değil, mevcut oturumu öne almak "
            "gerekiyor; bu activate'in tanımı."
        ),
        index=23,
    ),
    ToolScenario(
        tool="ios_app_background",
        archetype="resume_test_kapat_trap",
        context=(
            "[ios] Sipariş formu yarıya kadar dolduruldu. Operatör: "
            "'Uygulamayı kapat, 15 saniye sonra dönünce form kaldığı "
            "yerden devam ediyor mu bakalım.'"
        ),
        args={"seconds": 15},
        reasoning=(
            "'Kapat' dese de test edilen şey arka plandan dönüş; "
            "terminate süreci öldürür ve form durumu yok olur, test "
            "anlamsızlaşır. background 15 sn sonra kendiliğinden döner."
        ),
        index=24,
    ),
    ToolScenario(
        tool="ios_app_terminate",
        archetype="cold_start_measure",
        context=(
            "[ios] Sıradaki test 'com.trendyol.app' için soğuk başlatma "
            "süresini ölçecek; uygulama şu an ön planda çalışıyor."
        ),
        args={"bundle_id": "com.trendyol.app"},
        reasoning=(
            "Soğuk başlatma ölçümü ölü bir süreçle başlamalı; background "
            "süreci canlı bırakır ve ölçümü sıcak başlatmaya çevirir. "
            "Süreci tamamen bitirmek için terminate."
        ),
        index=25,
    ),
    # ------------------------------------------------------------------
    # INSTALL: install_app vs install_xapk vs uninstall vs clear_data
    # ------------------------------------------------------------------
    ToolScenario(
        tool="android_install_app",
        archetype="plain_apk_install",
        context=(
            "[android] CI, tek dosyalık derlemeyi "
            "'/builds/app-release.apk' yoluna bıraktı. Operatör: 'Yeni "
            "sürümü cihaza kur.'"
        ),
        args={"apk_path": "/builds/app-release.apk"},
        reasoning=(
            "Kurulacak şey tek bir .apk dosyası; split parçaları yok, "
            "install_xapk klasör ister. Tek dosya için doğru araç "
            "install_app (adb install -r)."
        ),
        index=26,
    ),
    ToolScenario(
        tool="android_install_xapk",
        archetype="split_dir_trap",
        context=(
            "[android] Operatör: 'Şu APK'yı kur: /builds/oyun/'. Klasörde "
            "base.apk, split_config.arm64_v8a.apk ve split_config.tr.apk "
            "var."
        ),
        args={"xapk_dir": "/builds/oyun"},
        reasoning=(
            "Operatör 'APK' dese de içerik split parçalı bir paket; "
            "install_app tek dosya yükler ve split'ler eksik kalır. "
            "Parçaları birlikte kuran araç install_xapk."
        ),
        index=27,
    ),
    ToolScenario(
        tool="android_install_xapk",
        archetype="missing_split_recovery",
        context=(
            "[android] android_install_app '/builds/market/base.apk' "
            "için INSTALL_FAILED_MISSING_SPLIT hatası verdi; klasörde "
            "diğer split dosyaları duruyor."
        ),
        args={"xapk_dir": "/builds/market"},
        reasoning=(
            "Hata, paketin split bütününden koptuğunu söylüyor; aynı "
            "çağrıyı tekrarlamak aynı hatayı üretir. Tüm parçaları "
            "install-multiple ile kuran install_xapk'a geçiyorum."
        ),
        index=28,
    ),
    ToolScenario(
        tool="android_uninstall_app",
        archetype="remove_package",
        context=(
            "[android] Test cihazında depolama doldu; eski deneme "
            "uygulaması 'com.demo.eskiuygulama' artık kullanılmıyor. "
            "Operatör: 'Bunu cihazdan tamamen kaldır.'"
        ),
        args={"package": "com.demo.eskiuygulama"},
        reasoning=(
            "İstek uygulamanın kendisini kaldırmak ve yer açmak; "
            "clear_data yalnızca veriyi siler, paketi cihazda bırakır. "
            "Tam kaldırma uninstall'un işi."
        ),
        index=29,
    ),
    ToolScenario(
        tool="android_app_clear_data",
        archetype="fresh_state_trap",
        context=(
            "[android] Onboarding testi tekrar koşulacak. Operatör: "
            "'Uygulamayı silip yeniden kur da ilk açılış gibi olsun.' "
            "Paket: com.hepsiburada.ecommerce"
        ),
        args={"package": "com.hepsiburada.ecommerce"},
        reasoning=(
            "Amaç temiz ilk-açılış durumu; pm clear veriyi ve önbelleği "
            "sıfırlayıp aynı sonucu tek adımda verir. Kaldırıp yeniden "
            "kurmak iki riskli adım ve APK yolu bile elimizde yok."
        ),
        index=30,
    ),
    ToolScenario(
        tool="ios_uninstall_app",
        archetype="remove_bundle",
        context=(
            "[ios] ios_list_apps çıktısında TestFlight denemesi "
            "'com.demo.beta' görünüyor. Operatör: 'Şu beta denemesini "
            "cihazdan sil.'"
        ),
        args={"bundle_id": "com.demo.beta"},
        reasoning=(
            "Uygulama kalıcı olarak kaldırılacak; terminate sadece "
            "süreci kapatır, paket kalır. Listeden doğrulanan bundle_id "
            "ile uninstall doğru araç."
        ),
        index=31,
    ),
    # ------------------------------------------------------------------
    # SIMULATOR / EMULATOR: boot vs shutdown (preserves) vs erase
    # (wipes); list-first before destructive acts
    # ------------------------------------------------------------------
    ToolScenario(
        tool="ios_simulator_list",
        archetype="list_before_erase",
        context=(
            "[ios] Operatör: 'Simülatörü sıfırla.' Makinada birden fazla "
            "simülatör tanımlı ve hangisinin kastedildiği, UDID'si "
            "bilinmiyor."
        ),
        args={},
        reasoning=(
            "Erase geri alınamaz bir fabrika sıfırlaması ve UDID ister; "
            "yanlış cihazı silmek telafisiz. Körlemesine davranmak "
            "yerine önce simulator_list ile adayları görüyorum."
        ),
        index=32,
    ),
    ToolScenario(
        tool="ios_simulator_erase",
        archetype="factory_reset_clean_device",
        context=(
            "[ios] Dünkü testler simülatörde hesaplar ve kirli veri "
            "bıraktı; UDID doğrulandı: 3E4C2F1A-8B6D-4E2A-9C0D-"
            "7F5A1B2C3D4E. Operatör: 'Yarınki koşu için tertemiz cihaz "
            "istiyorum, her şey gitsin.'"
        ),
        args={"udid": "3E4C2F1A-8B6D-4E2A-9C0D-7F5A1B2C3D4E"},
        reasoning=(
            "İstek verinin tamamen yok olması; shutdown sadece kapatır, "
            "hesaplar ve veriler yerinde kalır. Fabrika durumuna ancak "
            "erase döndürür."
        ),
        index=33,
    ),
    ToolScenario(
        tool="ios_simulator_shutdown",
        archetype="preserve_session_trap",
        context=(
            "[ios] Gün bitti. Operatör: 'Simülatörü temizle... yani "
            "kapat işte; yarın aynı hesap açık kalsın, kurulumla "
            "uğraşmayalım.' UDID: A1B2C3D4-0000-4444-8888-1234567890AB"
        ),
        args={"udid": "A1B2C3D4-0000-4444-8888-1234567890AB"},
        reasoning=(
            "'Temizle' sözü erase'i çağrıştırsa da niyet oturumu KORUMAK. "
            "Erase hesabı ve veriyi siler, yarınki kurulumu yeniden "
            "yaptırır; veriyi koruyan kapanış shutdown."
        ),
        index=34,
    ),
    ToolScenario(
        tool="ios_simulator_boot",
        archetype="boot_known_udid",
        context=(
            "[ios] simulator_list çıktısında 'iPhone 15 Pro' kapalı "
            "(Shutdown) görünüyor, UDID: 9F8E7D6C-1111-4222-8333-"
            "445566778899. Operatör: 'Bu simülatörü başlat, test "
            "edeceğiz.'"
        ),
        args={"udid": "9F8E7D6C-1111-4222-8333-445566778899"},
        reasoning=(
            "Cihaz kapalı ve teste hazırlanacak; veri silmek gerekmiyor, "
            "erase yanlış olur. Bilinen UDID ile simulator_boot cihazı "
            "olduğu haliyle açar."
        ),
        index=35,
    ),
    ToolScenario(
        tool="android_emulator_boot",
        archetype="boot_avd",
        context=(
            "[android] adb devices boş liste döndürdü; tanımlı AVD adı "
            "biliniyor: Pixel_8_API_35. Operatör: 'Emülatörü aç, "
            "testlere başlayalım.'"
        ),
        args={"avd": "Pixel_8_API_35"},
        reasoning=(
            "Çalışan cihaz yok, bağlanılacak bir serial de yok; önce "
            "emülatörün kendisi ayağa kalkmalı. emulator_boot AVD adıyla "
            "cihazı başlatır."
        ),
        index=36,
    ),
    ToolScenario(
        tool="android_emulator_shutdown",
        archetype="kill_emulator_serial",
        context=(
            "[android] Testler bitti; device_list tek emülatör gösterdi: "
            "emulator-5554. Operatör: 'Emülatörü kapat, makine "
            "rahatlasın.'"
        ),
        args={"serial": "emulator-5554"},
        reasoning=(
            "İstek emülatörü kapatmak; AVD diskteki verisiyle kalır, bu "
            "bir silme değil. android_reboot cihazı yeniden başlatır, "
            "kapatmaz; doğru araç serial ile emulator_shutdown."
        ),
        index=37,
    ),
    ToolScenario(
        tool="android_device_list",
        archetype="serial_unknown_gather",
        context=(
            "[android] Operatör: 'Emülatörü kapat.' Makinada iki emülatör "
            "birden çalışıyor olabilir; hangi serial'ın hedef olduğu "
            "belirsiz."
        ),
        args={},
        reasoning=(
            "emulator_shutdown serial ister ve yanlış serial yanlış "
            "cihazı öldürür. Tahmin etmek yerine önce device_list ile "
            "bağlı cihazları ve serial'ları görüyorum."
        ),
        index=38,
    ),
    # ------------------------------------------------------------------
    # DEVICE STATE: clipboard, geolocation, orientation, lock/unlock,
    # biometrics
    # ------------------------------------------------------------------
    ToolScenario(
        tool="android_set_clipboard",
        archetype="clipboard_paste_flow",
        context=(
            "[android] 380 karakterlik API anahtarı bir alana girilecek; "
            "karakter karakter yazım hataya açık. Operatör: 'Anahtarı "
            "panoya koy, sonra yapıştırırız.'"
        ),
        args={"text": "sk-live-7f3a9c1e2b8d4f6a0e5c9b3d7a1f4e8c"},
        reasoning=(
            "Akışın ilk adımı panoya veri YAZMAK; get_clipboard okur, "
            "yazmaz. Uzun metni type ile dökmek yerine set_clipboard + "
            "yapıştır daha güvenilir."
        ),
        index=39,
    ),
    ToolScenario(
        tool="android_get_clipboard",
        archetype="verify_copied_value",
        context=(
            "[android] Uygulamada 'Kopyala' düğmesine basıldı ve "
            "'IBAN kopyalandı' bildirimi çıktı. Operatör: 'Gerçekten "
            "doğru IBAN kopyalanmış mı kontrol et.'"
        ),
        args={},
        reasoning=(
            "Doğrulama panonun MEVCUT içeriğini okumayı gerektirir; "
            "set_clipboard yazarak kanıtı ezer. Okuma işi get_clipboard."
        ),
        index=40,
    ),
    ToolScenario(
        tool="android_set_geolocation",
        archetype="fake_gps_istanbul",
        context=(
            "[android] Emülatörde konum tabanlı kampanya testi: uygulama "
            "İstanbul'daki kullanıcıya özel kupon göstermeli."
        ),
        args={"latitude": 41.0082, "longitude": 28.9784},
        reasoning=(
            "Testin ön koşulu cihazın kendini İstanbul'da sanması; bu "
            "emülatör GPS'ine değer YAZMA işi (emu geo fix). Okumak "
            "değil ayarlamak gerekiyor: set_geolocation."
        ),
        index=41,
    ),
    ToolScenario(
        tool="ios_get_geolocation",
        archetype="geo_verify_recovery",
        context=(
            "[ios] ios_set_geolocation ile Ankara ayarlandı ama hava "
            "durumu uygulaması hâlâ İstanbul gösteriyor. Operatör: "
            "'Konumu bir daha ayarla.'"
        ),
        args={},
        reasoning=(
            "Sorun ayarın alınmaması mı, uygulama önbelleği mi belli "
            "değil; körlemesine yeniden set etmek teşhisi karartır. "
            "Önce get_geolocation ile simülatörün gerçek değerine "
            "bakıyorum."
        ),
        index=42,
    ),
    ToolScenario(
        tool="ios_set_orientation",
        archetype="video_landscape",
        context=(
            "[ios] Video oynatıcının tam ekran düzeni test edilecek; "
            "cihaz şu an dikey. Operatör: 'Yatay moda geç.'"
        ),
        args={"orientation": "LANDSCAPE"},
        reasoning=(
            "Mevcut durum zaten biliniyor (dikey), tekrar okumak "
            "gereksiz; cihaz fiilen döndürülecek. set_orientation ile "
            "LANDSCAPE'e geçiyorum."
        ),
        index=43,
    ),
    ToolScenario(
        tool="android_get_orientation",
        archetype="orientation_report",
        context=(
            "[android] Hata kaydı: 'Ekran bazen dönmüyor.' Operatör: "
            "'Müdahale etmeden önce cihaz şu an hangi yönelimde, "
            "raporla.'"
        ),
        args={},
        reasoning=(
            "İstenen mevcut durumun tespiti; set_orientation durumu "
            "değiştirir ve hatanın izini bozar. Salt okuma için "
            "get_orientation."
        ),
        index=44,
    ),
    ToolScenario(
        tool="ios_biometric_match",
        archetype="faceid_happy_path",
        context=(
            "[ios] Banka uygulaması Face ID istemi gösteriyor; senaryo "
            "'başarılı girişte ana ekran açılır' adımında."
        ),
        args={},
        reasoning=(
            "Happy-path testi başarılı bir kimlik eşleşmesi ister; "
            "no_match hata akışını tetikler ve senaryoyu saptırır. "
            "Başarılı taramayı biometric_match simüle eder."
        ),
        index=45,
    ),
    ToolScenario(
        tool="ios_biometric_no_match",
        archetype="faceid_fallback_trap",
        context=(
            "[ios] Operatör: 'Face ID'yi test et.' Senaryo dosyası "
            "açık: 'Tanınmayan yüzde uygulama PIN ekranına düşmeli.'"
        ),
        args={},
        reasoning=(
            "'Test et' sözü match'i çağrıştırsa da doğrulanan davranış "
            "BAŞARISIZ taramanın PIN'e düşürmesi. Bu akışı ancak "
            "biometric_no_match tetikler."
        ),
        index=46,
    ),
    ToolScenario(
        tool="ios_lock_device",
        archetype="lockscreen_notification_test",
        context=(
            "[ios] Kilit ekranında bildirim önizlemesinin gizlendiği "
            "doğrulanacak; cihaz şu an açık ve kilitsiz."
        ),
        args={},
        reasoning=(
            "Kilit ekranı davranışını görmek için cihaz önce "
            "kilitlenmeli; unlock tam tersini yapar. lock_device kilit "
            "düğmesine basıp ekranı kilitler."
        ),
        index=47,
    ),
    ToolScenario(
        tool="ios_unlock_device",
        archetype="wake_to_continue",
        context=(
            "[ios] Bildirim testi bitti, cihaz kilitli ve ekran karanlık. "
            "Operatör: 'Devam edelim, cihazı uyandır.'"
        ),
        args={},
        reasoning=(
            "Etkileşime dönmek için ekranın uyanması gerekiyor; "
            "lock_device zaten kilitli cihazda anlamsız. unlock_device "
            "cihazı uyandırır."
        ),
        index=48,
    ),
    # ------------------------------------------------------------------
    # LOGS: logcat (event history) vs dumpsys (live service state) vs
    # ios_get_logs; dedicated get_battery
    # ------------------------------------------------------------------
    ToolScenario(
        tool="android_logcat",
        archetype="crash_stacktrace",
        context=(
            "[android] Uygulama az önce çöktü ve kapandı. Operatör: "
            "'Çökme kaydını bul, stack trace lazım.'"
        ),
        args={"tag_filter": "AndroidRuntime", "max_lines": 200},
        reasoning=(
            "Çökme geçmişte olmuş bir OLAY; dumpsys anlık servis durumu "
            "verir, geçmiş olayı göstermez. Stack trace logcat'te "
            "AndroidRuntime etiketiyle bulunur."
        ),
        index=49,
    ),
    ToolScenario(
        tool="android_logcat",
        archetype="clear_before_repro",
        context=(
            "[android] Hata yeniden üretilecek ama log tamponu saatlerce "
            "birikmiş kayıtla dolu; eski gürültü analizi boğuyor."
        ),
        args={"clear": True},
        reasoning=(
            "Tek denemenin logunu izole etmek için tampon repro "
            "ÖNCESİNDE temizlenmeli; clear=true bunu yapar. Kirli "
            "tamponla okumak yanlış eşleştirmeye götürür."
        ),
        index=50,
    ),
    ToolScenario(
        tool="android_dumpsys",
        archetype="wifi_state_trap",
        context=(
            "[android] Operatör: 'Loglara bak, Wi-Fi neden kopuk?' Asıl "
            "ihtiyaç bağlantının ŞU ANKİ durumu: hangi ağ, sinyal, "
            "supplicant durumu."
        ),
        args={"service": "wifi"},
        reasoning=(
            "'Loglara bak' dense de soru anlık servis durumuyla ilgili; "
            "logcat geçmiş olay akışı verir. Wi-Fi servisinin canlı "
            "durumunu dumpsys wifi döker."
        ),
        index=51,
    ),
    ToolScenario(
        tool="ios_get_logs",
        archetype="unified_log_window",
        context=(
            "[ios] 'YemekSepeti' uygulaması son beş dakikadır sipariş "
            "adımında sessizce takılıyor. Operatör: 'Bu aralıktaki "
            "kayıtlarına bak.'"
        ),
        args={"predicate": 'process == "YemekSepeti"', "last": "5m"},
        reasoning=(
            "iOS'ta uygulama kayıtları birleşik log'da; logcat Android "
            "aracı. Predicate ile süreci, last ile son 5 dakikayı "
            "daraltıp get_logs kullanıyorum."
        ),
        index=52,
    ),
    ToolScenario(
        tool="android_get_battery",
        archetype="dedicated_over_dumpsys_trap",
        context=(
            "[android] Uzun koşu testi öncesi şarj kontrolü. Operatör: "
            "'dumpsys battery çek, seviyeye bakalım.'"
        ),
        args={},
        reasoning=(
            "Operatör dumpsys dese de pil için özel araç var: "
            "get_battery zaten dumpsys battery'yi sarar ve çıktıyı "
            "ayrıştırır. Genel araç yerine özel olanı seçiyorum."
        ),
        index=53,
    ),
    # ------------------------------------------------------------------
    # MISC: deeplink over launch+type, file transfer direction,
    # re-observe over blind retry, video over screenshot
    # ------------------------------------------------------------------
    ToolScenario(
        tool="android_deeplink",
        archetype="open_url_one_step_trap",
        context=(
            "[android] Operatör: 'Chrome'u aç, sonra adres çubuğuna "
            "https://kampanya.ornek.com/yaz yaz ve git.'"
        ),
        args={"url": "https://kampanya.ornek.com/yaz"},
        reasoning=(
            "Tarif üç adım ama hedef tek: URL'nin açılması. deeplink "
            "(am start VIEW) adresi tek çağrıda varsayılan tarayıcıda "
            "açar; launch+tıkla+yaz zinciri kırılgan ve gereksiz."
        ),
        index=54,
    ),
    ToolScenario(
        tool="ios_open_url",
        archetype="universal_link",
        context=(
            "[ios] Universal link testi: 'https://app.ornek.com/urun/42' "
            "bağlantısı uygulamanın ürün sayfasını doğrudan açmalı."
        ),
        args={"url": "https://app.ornek.com/urun/42"},
        reasoning=(
            "Test edilen şey bağlantının kendisinin yönlendirmesi; "
            "uygulamayı launch edip gezinmek senaryoyu boşa çıkarır. "
            "open_url bağlantıyı sisteme verir ve yönlendirmeyi sınar."
        ),
        index=55,
    ),
    ToolScenario(
        tool="android_a11y_tree",
        archetype="reobserve_after_noop_click",
        context=(
            "[android] android_click(540, 1710) gönderildi ama ekran hiç "
            "değişmedi; buton kaymış ya da devre dışı olabilir. Operatör: "
            "'Bir daha tıkla.'"
        ),
        args={},
        reasoning=(
            "Aynı koordinata kör tekrar aynı sonucu verir; önce ekranın "
            "gerçek durumunu görmek gerek. a11y_tree butonun yeni "
            "konumunu ve enabled durumunu gösterir."
        ),
        index=56,
    ),
    ToolScenario(
        tool="android_push",
        archetype="host_to_device",
        context=(
            "[android] Galeri testinin ön koşulu: host'taki "
            "'/work/assets/test_foto.jpg' dosyası cihazda Pictures "
            "klasöründe bulunmalı."
        ),
        args={
            "local": "/work/assets/test_foto.jpg",
            "remote": "/sdcard/Pictures/test_foto.jpg",
        },
        reasoning=(
            "Dosya bilgisayardan CİHAZA gidecek; pull ters yönde, "
            "cihazdan çeker. Host'tan cihaza kopyalama push'un işi."
        ),
        index=57,
    ),
    ToolScenario(
        tool="android_pull",
        archetype="device_to_host",
        context=(
            "[android] Uygulama cihazda '/sdcard/Android/data/"
            "com.ornek.app/files/app.log' dosyasına yazdı. Operatör: "
            "'Log dosyasını al, analiz edeceğiz.'"
        ),
        args={
            "remote": "/sdcard/Android/data/com.ornek.app/files/app.log",
            "local": "/work/logs/app.log",
        },
        reasoning=(
            "Dosya CİHAZDAN bilgisayara gelecek; push ters yön. Cihazdan "
            "host'a kopyalama pull ile yapılır; logcat da yanlış olur, "
            "bu sistem logu değil uygulamanın kendi dosyası."
        ),
        index=58,
    ),
    ToolScenario(
        tool="android_screenrecord_start",
        archetype="intermittent_glitch_video",
        context=(
            "[android] Geçiş animasyonu ara sıra bir kare titriyor; "
            "önceki üç screenshot hep temiz anı yakaladı. Operatör: "
            "'Şu hatayı bir yakala artık.'"
        ),
        args={"output_path": "/work/kayit/animasyon_titreme.mp4"},
        reasoning=(
            "Aralıklı ve anlık bir hata tek kareyle yakalanmıyor; "
            "screenshot denemeleri bunu kanıtladı. Süreklilik isteyen "
            "kanıt için ekran KAYDI başlatıyorum."
        ),
        index=59,
    ),
]

__all__ = ["SCENARIOS"]
