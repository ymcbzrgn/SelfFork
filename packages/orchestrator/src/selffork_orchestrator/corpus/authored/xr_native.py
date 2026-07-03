"""Authored reasoning scenarios for the xr_native surface: Quest VR,
Vision Pro (simulator), macOS desktop and the abstract body driver.

Every scenario carries a non-None ``reasoning`` -- the point is teaching a
small model the *judgement* between confusable tools, per surface:

* Quest: launch vs terminate ('kaldır' trap) vs app_list vs list_vr_apps;
  passthrough enable/disable (+ 'odayı göster' trap); controller button vs
  Meta button vs voice_command; recenter; boundary vs battery vs device_info;
  record_video vs stop_record_video vs screenshot ('kaydet' trap).
* Vision Pro: find_text (semantic, no coords) vs click_at (known coords);
  simulator list/boot/shutdown; get_logs for crashes; screenshot for layout;
  error recovery: launch failed because the simulator was not booted.
* Desktop: click vs double_click ('aç' trap) vs right_click; get_active_app
  vs focus_window vs list_windows vs list_apps; screenshot vs region;
  press_key ('cmd+s yaz' trap) vs type; say vs notification (meeting trap);
  clipboard get/set; error recovery: typed into the wrong window.
* Body: abstract body_* when the surface is unknown / the flow must be
  portable, platform tools when it is not; ax_tree (structure) vs screenshot
  (pixels); storage_state save vs load (login-screen trap).
* Refusals: destructive mass-uninstall and passthrough-off without Guardian
  are NOT executed -- the model asks via AskUserQuestion instead.

Every scenario is gated against the real registry by the builder.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

_UDID = "7D2F31A4-9C0B-4E2D-B1A6-3F8E5C7D9A21"

SCENARIOS: list[ToolScenario] = [
    # ------------------------------------------------------------------
    # Quest: app lifecycle -- launch vs terminate vs list vs list_vr
    # ------------------------------------------------------------------
    ToolScenario(
        tool="quest_app_launch",
        archetype="vr_session_start",
        context=(
            "[quest] Kulaklık ana menüde, hiçbir uygulama çalışmıyor. "
            "Operatör: 'Showroom uygulamasını aç, VR test turuna başlayalım.'"
        ),
        args={"package": "com.arketic.vrshowroom"},
        reasoning=(
            "Uygulama çalışmıyor ve hedef paket belli; soğuk başlatma gerekiyor. "
            "Sesli komut ya da menü gezintisi dolaylı kalır; doğrudan "
            "quest_app_launch kullanıyorum."
        ),
        index=0,
    ),
    # --- trap: 'kaldır' = close, NOT uninstall ------------------------------
    ToolScenario(
        tool="quest_app_terminate",
        archetype="kaldir_means_close_trap",
        context=(
            "[quest] Showroom testi bitti, uygulama hâlâ ön planda ve kulaklık "
            "ısınıyor. Operatör: 'Şu oyunu kaldır artık, yarın aynı build ile "
            "devam edeceğiz.'"
        ),
        args={"package": "com.arketic.vrshowroom"},
        reasoning=(
            "'Kaldır' burada silmek değil kapatmak: yarın aynı build ile devam "
            "edilecek, uygulama cihazda kalmalı. quest_uninstall_app kurulumu yok "
            "eder; doğru araç quest_app_terminate."
        ),
        index=1,
    ),
    ToolScenario(
        tool="quest_app_list",
        archetype="full_inventory",
        context=(
            "[quest] Sideload öncesi cihaz envanteri gerekiyor. Operatör: "
            "'2D araçlar dahil kulaklıkta kurulu ne varsa tam listesini çıkar.'"
        ),
        args={},
        reasoning=(
            "İstenen VR filtreli değil, sistem ve 2D uygulamalar dahil tam "
            "envanter. quest_list_vr_apps VR sezgisel filtresi uygular; eksiksiz "
            "liste için quest_app_list doğru."
        ),
        index=2,
    ),
    ToolScenario(
        tool="quest_list_vr_apps",
        archetype="vr_only_titles",
        context=(
            "[quest] Operatör: 'Bu kulaklıkta oynanabilir VR oyunları neler? "
            "Sistem araçları listeyi kirletmesin.'"
        ),
        args={},
        reasoning=(
            "Operatör yalnızca VR başlıklarını istiyor; quest_app_list her paketi "
            "döker ve elle ayıklamak gerekir. VR/Meta sezgisel bayrağıyla "
            "quest_list_vr_apps tam bu iş için."
        ),
        index=3,
    ),
    # ------------------------------------------------------------------
    # Quest: passthrough enable vs disable
    # ------------------------------------------------------------------
    ToolScenario(
        tool="quest_passthrough_disable",
        archetype="back_to_immersion",
        context=(
            "[quest] Kullanıcı kumandayı masadan aldı, passthrough hâlâ açık. "
            "Operatör: 'Gerçek dünya görüntüsünü kapat, sahne testine dönelim.' "
            "Guardian sınırı tanımlı."
        ),
        args={},
        reasoning=(
            "Passthrough açık ve istek tam VR'a dönmek; Guardian tanımlı "
            "olduğundan güvenli. quest_passthrough_disable kamerayı kapatır; "
            "enable tam tersini yapardı."
        ),
        index=4,
    ),
    # --- trap: 'göremiyorum, odayı göster' -> ENABLE ------------------------
    ToolScenario(
        tool="quest_passthrough_enable",
        archetype="show_room_trap",
        context=(
            "[quest] Kullanıcı tam VR sahnesinde: 'Dur, hiçbir şey göremiyorum, "
            "telefonum çalıyor; odayı göster.'"
        ),
        args={},
        reasoning=(
            "'Odayı göster' gerçek dünyayı görmek demek, yani passthrough "
            "AÇILMALI. Sahneyi kapatan bir araç aramak yanlış; "
            "quest_passthrough_enable kamera görüntüsünü açar."
        ),
        index=5,
    ),
    # ------------------------------------------------------------------
    # Quest: controller button vs Meta button vs voice_command
    # ------------------------------------------------------------------
    ToolScenario(
        tool="quest_press_controller_button",
        archetype="ingame_confirm",
        context=(
            "[quest] Oyun içinde 'İlerlemeyi kaydet?' penceresi açık; Evet "
            "düğmesi A tuşuna bağlı, imleç üzerinde."
        ),
        args={"button": "a"},
        reasoning=(
            "Onay oyun İÇİ bir tuşa bağlı; Meta tuşu sistem menüsünü açar, sesli "
            "komut oyuna ulaşmaz. Sağ kumandanın A tuşu için "
            "quest_press_controller_button."
        ),
        index=6,
    ),
    ToolScenario(
        tool="quest_press_meta_button",
        archetype="universal_menu",
        context=(
            "[quest] Test bitti; operatör: 'Oyundan çıkmadan evrensel menüyü aç, "
            "saate bakalım.' Sesli asistan kapalı."
        ),
        args={},
        reasoning=(
            "Evrensel menü sistem katmanıdır ve Meta/Oculus tuşuyla açılır; "
            "A/B tuşları oyuna gider, sesli asistan da kapalı. "
            "quest_press_meta_button doğru araç."
        ),
        index=7,
    ),
    ToolScenario(
        tool="quest_voice_command",
        archetype="no_dedicated_tool_cast",
        context=(
            "[quest] Operatör ekranı TV'ye yansıtmak istiyor: 'Cast'i başlat.' "
            "Yayın için özel bir SelfFork aracı yok."
        ),
        args={"text": "TV'ye ekran yansıtmayı başlat"},
        reasoning=(
            "Yansıtma için özel araç yok; Meta tuşu yalnızca menüyü açar, menüde "
            "gezinmek kırılgan olur. Sistem eylemini quest_voice_command ile "
            "sesli komut olarak enjekte ediyorum."
        ),
        index=8,
    ),
    # ------------------------------------------------------------------
    # Quest: recenter / boundary / battery / device_info
    # ------------------------------------------------------------------
    ToolScenario(
        tool="quest_recenter",
        archetype="view_drift",
        context=(
            "[quest] Kullanıcı sandalyesini pencere kenarına taşıdı; menü artık "
            "omzunun arkasında kalıyor ve görüş eğik duruyor."
        ),
        args={},
        reasoning=(
            "Sorun sınır ya da pil değil, görüş referansının kayması. "
            "quest_recenter görünümü kullanıcının yeni yönüne sıfırlar; "
            "passthrough veya boundary araçları bunu çözmez."
        ),
        index=9,
    ),
    ToolScenario(
        tool="quest_get_boundary",
        archetype="guardian_warnings",
        context=(
            "[quest] Kullanıcı oyun sırasında sürekli ızgara uyarısı gördüğünü "
            "söylüyor. Operatör: 'Guardian tarafında durum ne, bir bak.'"
        ),
        args={},
        reasoning=(
            "Izgara uyarıları Guardian sınırına yaklaşınca çıkar; teşhis için "
            "sınır durumunu okumak gerek. quest_get_boundary OVRGuardian verisini "
            "döker; battery ya da device_info alakasız."
        ),
        index=10,
    ),
    # --- trap: dead controller -> battery, NOT device_info ------------------
    ToolScenario(
        tool="quest_get_battery",
        archetype="controller_dead_trap",
        context=(
            "[quest] Sol kumanda girişlere tepki vermiyor ama kulaklık çalışıyor. "
            "Operatör: 'Eşleşme mi bozuldu acaba?'"
        ),
        args={},
        reasoning=(
            "Eşleşmeden önce en olası neden kumanda pilinin bitmesi; "
            "quest_get_battery kulaklıkla birlikte kumanda pillerini de raporlar. "
            "quest_device_info yalnız model/OS verir, teşhise katkısı yok."
        ),
        index=11,
    ),
    ToolScenario(
        tool="quest_device_info",
        archetype="os_version_gate",
        context=(
            "[quest] Sideload edilecek APK en az v66 çalışma zamanı istiyor. "
            "Operatör: 'Önce cihaz sürümünü doğrula, sonra kurarız.'"
        ),
        args={},
        reasoning=(
            "Kurulum öncesi kapı koşulu OS/runtime sürümü; quest_device_info "
            "getprop ile model ve sürümü okur. Pil ya da boundary değil sürüm "
            "sorulduğu için doğru araç bu."
        ),
        index=12,
    ),
    # ------------------------------------------------------------------
    # Quest: record_video vs stop_record_video vs screenshot
    # ------------------------------------------------------------------
    ToolScenario(
        tool="quest_record_video",
        archetype="flicker_needs_motion",
        context=(
            "[quest] Showroom'da gökyüzü dokusunda aralıklı titreme var; hata tek "
            "karede değil, birkaç saniyelik harekette görülüyor."
        ),
        args={
            "output_path": "/sdcard/selffork/flicker_repro.mp4",
            "time_limit_sec": 30,
        },
        reasoning=(
            "Titreme zamana yayılan bir hata; tek kare quest_screenshot bunu "
            "kanıtlayamaz. 30 saniyelik quest_record_video ile hareketli kanıt "
            "topluyorum."
        ),
        index=13,
    ),
    ToolScenario(
        tool="quest_stop_record_video",
        archetype="repro_captured_stop",
        context=(
            "[quest] Ekran kaydı sürüyor ve titreme az önce net biçimde "
            "tekrarlandı. Operatör: 'Tamam, yakaladık; kaydı bitir.'"
        ),
        args={},
        reasoning=(
            "Aktif bir screenrecord süreci var ve kanıt alındı; süre sınırını "
            "beklemek dosyayı gereksiz büyütür. quest_stop_record_video kaydı "
            "SIGINT ile düzgün kapatır."
        ),
        index=14,
    ),
    # --- trap: 'kaydet şu hatayı' on a STATIC dialog -> screenshot ----------
    ToolScenario(
        tool="quest_screenshot",
        archetype="static_error_kaydet_trap",
        context=(
            "[quest] Ekranda sabit bir 'Sunucuya bağlanılamadı' penceresi "
            "duruyor. Operatör: 'Şu hatayı kaydet, rapora koyacağız.'"
        ),
        args={},
        reasoning=(
            "'Kaydet' videoya işaret etmiyor: hata penceresi sabit, hareket yok. "
            "Tek kare yeterli olduğundan quest_screenshot alıyorum; video kaydı "
            "burada gereksiz yük."
        ),
        index=15,
    ),
    # ------------------------------------------------------------------
    # Vision Pro: simulator list / boot / shutdown
    # ------------------------------------------------------------------
    ToolScenario(
        tool="visionpro_simulator_list",
        archetype="find_udid_first",
        context=(
            "[visionpro] Teste başlanacak ama hangi visionOS simülatörlerinin "
            "kurulu olduğu ve UDID'leri bilinmiyor."
        ),
        args={},
        reasoning=(
            "Boot için UDID zorunlu ve elimizde yok; körlemesine boot çağrısı "
            "yapılamaz. Önce visionpro_simulator_list ile cihazları ve "
            "durumlarını çıkarıyorum."
        ),
        index=16,
    ),
    ToolScenario(
        tool="visionpro_simulator_boot",
        archetype="boot_known_udid",
        context=(
            "[visionpro] Listede 'Apple Vision Pro' UDID "
            f"{_UDID} durumu Shutdown görünüyor. Test bu cihazda koşacak."
        ),
        args={"udid": _UDID},
        reasoning=(
            "UDID biliniyor ve cihaz Shutdown durumunda; uygulama başlatmadan "
            "önce simülatörün açık olması şart. visionpro_simulator_boot ile "
            "başlatıyorum."
        ),
        index=17,
    ),
    ToolScenario(
        tool="visionpro_app_launch",
        archetype="launch_by_bundle",
        context=(
            "[visionpro] Simülatör Booted durumda. Operatör: 'Spatial demo "
            "uygulamasını başlat, ilk ekranı doğrulayacağız.'"
        ),
        args={"bundle_id": "com.arketic.spatialdemo"},
        reasoning=(
            "Simülatör açık ve hedef bundle id belli; simctl launch en kısa yol. "
            "Ekrandan simge aramak (find_text + click_at) kırılgan ve yavaş "
            "kalır."
        ),
        index=18,
    ),
    # ------------------------------------------------------------------
    # Vision Pro: find_text (semantic) vs click_at (coordinate)
    # ------------------------------------------------------------------
    # --- trap: operator says 'tıkla' but there are NO coordinates -----------
    ToolScenario(
        tool="visionpro_find_text",
        archetype="click_without_coords_trap",
        context=(
            "[visionpro] Operatör: 'Karşılama ekranındaki Devam düğmesine "
            "tıkla.' Düğmenin ekrandaki konumu bilinmiyor; elimizde koordinat "
            "yok."
        ),
        args={"needle": "Devam"},
        reasoning=(
            "'Tıkla' dense de koordinat yok; visionpro_click_at körlemesine "
            "basar, ıskalarsa durumu bozar. Önce visionpro_find_text ile 'Devam' "
            "metninin konumunu buluyorum."
        ),
        index=19,
    ),
    ToolScenario(
        tool="visionpro_click_at",
        archetype="click_verified_coords",
        context=(
            "[visionpro] visionpro_find_text az önce 'Devam' düğmesini merkez "
            "(612, 488) olarak raporladı."
        ),
        args={"x": 612, "y": 488},
        reasoning=(
            "Hedefin koordinatı doğrulanmış durumda; yeniden OCR koşmak gereksiz "
            "maliyet. visionpro_click_at ile bilinen noktaya tıklıyorum."
        ),
        index=20,
    ),
    ToolScenario(
        tool="visionpro_get_logs",
        archetype="crash_triage_logs",
        context=(
            "[visionpro] Uygulama başlatıldıktan iki saniye sonra kapandı; "
            "ekranda iz yok. Operatör: 'Neden düştüğünü bul.'"
        ),
        args={"predicate": 'process == "spatialdemo"', "last": "5m"},
        reasoning=(
            "Çökme nedeni görsel değil, günlüklerde; kapanmış uygulamanın ekran "
            "görüntüsü bilgi vermez. visionpro_get_logs'u süreç predikatı ve 5 "
            "dakikalık pencereyle çekiyorum."
        ),
        index=21,
    ),
    ToolScenario(
        tool="visionpro_screenshot",
        archetype="layout_visual_verify",
        context=(
            "[visionpro] Yeni cam panel tasarımı yüklendi. Operatör: 'Panelin "
            "yerleşimi ve saydamlığı doğru mu, gözle bakalım.'"
        ),
        args={},
        reasoning=(
            "İstenen belirli bir metni bulmak değil, yerleşimi bütün olarak "
            "görmek. visionpro_find_text tek iğne arar; tam kare için "
            "visionpro_screenshot gerekir."
        ),
        index=22,
    ),
    ToolScenario(
        tool="visionpro_simulator_shutdown",
        archetype="free_resources",
        context=(
            "[visionpro] Tüm senaryolar geçti; Mac'te bellek azaldı ve "
            f"simülatöre bugün başka iş yok. UDID {_UDID} hâlâ Booted."
        ),
        args={"udid": _UDID},
        reasoning=(
            "İş bitti ve simülatör kaynak tüketiyor; yalnızca uygulamayı "
            "kapatmak belleği geri vermez. visionpro_simulator_shutdown bu "
            "UDID'yi kapatıp kaynağı serbest bırakır."
        ),
        index=23,
    ),
    # --- error recovery: launch failed because sim was not booted -----------
    ToolScenario(
        tool="visionpro_simulator_boot",
        archetype="recover_not_booted",
        context=(
            "[visionpro] visionpro_app_launch 'Unable to launch: device is not "
            f"booted' hatası döndürdü. Hedef simülatör UDID {_UDID} listede "
            "Shutdown görünüyor."
        ),
        args={"udid": _UDID},
        reasoning=(
            "Hatanın kök nedeni uygulama değil, kapalı simülatör; launch'u "
            "tekrarlamak aynı hatayı verir. Önce visionpro_simulator_boot ile "
            "cihazı açıyorum, launch ondan sonra."
        ),
        index=24,
    ),
    # ------------------------------------------------------------------
    # Desktop: click vs double_click vs right_click
    # ------------------------------------------------------------------
    ToolScenario(
        tool="desktop_click",
        archetype="single_click_button",
        context=(
            "[mac] Safari'de indirme onayı penceresi açık; 'İzin Ver' düğmesi "
            "(742, 415) konumunda. Uygulama zaten ön planda."
        ),
        args={"x": 742, "y": 415},
        reasoning=(
            "Hedef macOS'ta ve piksel koordinatı kesin; düğme tek tıkla çalışır. "
            "Çift tık ikinci bir olay gönderip pencereyi kapatabilir; "
            "desktop_click yeterli ve güvenli."
        ),
        index=25,
    ),
    # --- trap: 'aç şu dosyayı' in Finder -> double_click, not click ---------
    ToolScenario(
        tool="desktop_double_click",
        archetype="finder_open_trap",
        context=(
            "[mac] Finder'da rapor.pdf simgesi (388, 302) konumunda duruyor. "
            "Operatör: 'Şu dosyayı aç.'"
        ),
        args={"x": 388, "y": 302},
        reasoning=(
            "Finder'da tek tık yalnızca seçer, dosyayı açmaz; 'aç' talebi çift "
            "tık gerektirir. desktop_double_click simgeyi doğrudan açar."
        ),
        index=26,
    ),
    ToolScenario(
        tool="desktop_right_click",
        archetype="context_menu_rename",
        context=(
            "[mac] Masaüstündeki eski_logo.png yeniden adlandırılacak; bunun "
            "için dosyanın bağlam menüsündeki 'Yeniden Adlandır' seçeneği "
            "gerekiyor. Simge (512, 640) konumunda."
        ),
        args={"x": 512, "y": 640},
        reasoning=(
            "Hedef eylem bağlam menüsünde; sol tık menüyü açmaz, çift tık "
            "dosyayı açar. Menü için desktop_right_click şart."
        ),
        index=27,
    ),
    # ------------------------------------------------------------------
    # Desktop: get_active_app vs focus_window vs list_windows vs list_apps
    # ------------------------------------------------------------------
    ToolScenario(
        tool="desktop_get_active_app",
        archetype="verify_focus_before_typing",
        context=(
            "[mac] Az önce birkaç pencere arasında geçiş yapıldı; şimdi bir "
            "terminal komutu yazılacak ama odağın hangi uygulamada olduğu "
            "belirsiz."
        ),
        args={},
        reasoning=(
            "Odak belirsizken yazmak metni yanlış pencereye gönderir. Önce "
            "desktop_get_active_app ile ön plandaki uygulamayı doğruluyorum; "
            "focus_window'a ancak yanlışsa gerek olur."
        ),
        index=28,
    ),
    ToolScenario(
        tool="desktop_list_windows",
        archetype="find_window_title",
        context=(
            "[mac] TextEdit'te beş belge açık; operatör 'sprint-notlari.txt "
            "penceresine geç' dedi ama tam pencere başlığı bilinmiyor."
        ),
        args={"app_name": "TextEdit"},
        reasoning=(
            "Doğru pencereyi öne almak için önce başlık listesi gerek; "
            "körlemesine focus_window yanlış belgeyi öne getirebilir. "
            "desktop_list_windows TextEdit'in pencerelerini döker."
        ),
        index=29,
    ),
    ToolScenario(
        tool="desktop_list_apps",
        archetype="is_it_running_at_all",
        context=(
            "[mac] Operatör: 'Xcode'a geç.' Ama Xcode'un açık olup olmadığı bile "
            "belli değil; Dock görünmüyor."
        ),
        args={},
        reasoning=(
            "focus_window çalışmayan uygulamada başarısız olur; önce Xcode'un "
            "süreç listesinde olup olmadığına bakmalıyım. desktop_list_apps "
            "çalışan uygulamaları bundle id'leriyle verir."
        ),
        index=30,
    ),
    # --- error recovery: text went to the WRONG window -> fix focus ---------
    ToolScenario(
        tool="desktop_focus_window",
        archetype="recover_wrong_window_typing",
        context=(
            "[mac] 'git status' metni yanlışlıkla Notlar penceresine yazıldı; "
            "Terminal arkada duruyor. Yazma tekrarlanmadan önce odak "
            "düzeltilmeli."
        ),
        args={"app_name": "Terminal"},
        reasoning=(
            "İlk hata odak doğrulanmadan yazmaktan çıktı; aynı type çağrısını "
            "yinelemek yine Notlar'a yazar. Önce desktop_focus_window ile "
            "Terminal'i öne alıyorum, yazma ondan sonra."
        ),
        index=31,
    ),
    # ------------------------------------------------------------------
    # Desktop: screenshot vs screenshot_region
    # ------------------------------------------------------------------
    ToolScenario(
        tool="desktop_screenshot",
        archetype="whole_desktop_state",
        context=(
            "[mac] Gece koşusundan sonra masaüstünün genel durumu raporlanacak: "
            "hangi pencereler açık, hata diyaloğu var mı, genel görünüm nasıl."
        ),
        args={},
        reasoning=(
            "İstenen tek bir bölge değil, ekranın bütünü; bölge kırpmak bağlamı "
            "kaybettirir. desktop_screenshot tam kareyi alır ve "
            "ScreenshotStore'a kalıcılaştırır."
        ),
        index=32,
    ),
    ToolScenario(
        tool="desktop_screenshot_region",
        archetype="menubar_clock_region",
        context=(
            "[mac] Yalnızca menü çubuğundaki saat ve pil yüzdesi okunacak; tam "
            "ekran görüntüsü 5K panelde gereksiz büyük dosya üretiyor."
        ),
        args={"x": 1280, "y": 0, "width": 320, "height": 24},
        reasoning=(
            "İlgi alanı 320x24 piksellik bir köşe; tam kare hem yavaş hem "
            "israf. desktop_screenshot_region yalnız o dikdörtgeni PNG olarak "
            "verir."
        ),
        index=33,
    ),
    # ------------------------------------------------------------------
    # Desktop: press_key vs type
    # ------------------------------------------------------------------
    # --- trap: operator says 'yaz' but means a SHORTCUT ----------------------
    ToolScenario(
        tool="desktop_press_key",
        archetype="yaz_means_shortcut_trap",
        context=(
            "[mac] Belge Pages'te açık ve odakta. Operatör: 'cmd+s yaz da "
            "kaydedelim.'"
        ),
        args={"key_combo": "cmd+s"},
        reasoning=(
            "Operatör 'yaz' dese de istek metin değil kısayol; desktop_type "
            "ekrana harf harf 'cmd+s' dizer. Kaydetme kısayolu "
            "desktop_press_key ile basılır."
        ),
        index=34,
    ),
    ToolScenario(
        tool="desktop_type",
        archetype="search_text_entry",
        context=(
            "[mac] Safari'de arama kutusu tıklandı ve imleç içinde yanıp "
            "sönüyor. Operatör: 'hyperframes changelog diye arat.'"
        ),
        args={"text": "hyperframes changelog"},
        reasoning=(
            "Odak metin kutusunda ve girilecek şey düz metin; press_key tek "
            "kombinasyon basar, cümle yazamaz. desktop_type metni olduğu gibi "
            "girer."
        ),
        index=35,
    ),
    # ------------------------------------------------------------------
    # Desktop: say vs notification
    # ------------------------------------------------------------------
    ToolScenario(
        tool="desktop_say",
        archetype="eyes_free_announce",
        context=(
            "[mac] Uzun derleme bitti; kullanıcı mutfakta, ekrana bakmıyor ama "
            "sesi duyabiliyor. Sonuç: 128 test geçti."
        ),
        args={"text": "Derleme bitti, yüz yirmi sekiz test geçti."},
        reasoning=(
            "Kullanıcı ekrandan uzakta; bildirim banner'ı görülmeden kaybolur. "
            "Sesli kanal açık olduğundan desktop_say ile sonucu sesli "
            "okutuyorum."
        ),
        index=36,
    ),
    # --- trap: 'haber ver' during a meeting -> SILENT notification ----------
    ToolScenario(
        tool="desktop_notification",
        archetype="silent_meeting_trap",
        context=(
            "[mac] Kullanıcı görüntülü toplantıda, hoparlörden ses çıkmamalı. "
            "Dağıtım tamamlandı; kendisine haber verilmesi istendi."
        ),
        args={
            "title": "Dağıtım tamamlandı",
            "body": "prod-web v2.4.1 yayında; smoke testleri yeşil.",
        },
        reasoning=(
            "'Haber ver' sesli okuma değil: toplantıda hoparlörden konuşan "
            "desktop_say toplantıyı böler. Sessiz banner için "
            "desktop_notification doğru kanal."
        ),
        index=37,
    ),
    # ------------------------------------------------------------------
    # Desktop: clipboard get vs set
    # ------------------------------------------------------------------
    ToolScenario(
        tool="desktop_get_clipboard",
        archetype="read_copied_secret",
        context=(
            "[mac] Kullanıcı 1Password'den API anahtarını az önce kopyaladığını "
            "söyledi; anahtar yapılandırma dosyasına eklenecek."
        ),
        args={},
        reasoning=(
            "Değer zaten panoda; ekrandan okumaya çalışmak hem kırılgan hem "
            "gizlilik riski. desktop_get_clipboard panodaki metni doğrudan "
            "verir."
        ),
        index=38,
    ),
    ToolScenario(
        tool="desktop_set_clipboard",
        archetype="stage_long_token",
        context=(
            "[mac] Uzun bir JWT örnek belirteci web formuna girilecek; form "
            "alanı tuş tuş yazımda ara sıra karakter yutuyor."
        ),
        args={"text": "eyJhbGciOiJIUzI1NiJ9.ornek-uzun-govde-a1b2c3d4e5.imza"},
        reasoning=(
            "Uzun belirteci desktop_type ile dizmek karakter kaybına açık; "
            "panoya koyup cmd+v ile yapıştırmak atomik. Önce "
            "desktop_set_clipboard ile panoyu dolduruyorum."
        ),
        index=39,
    ),
    # ------------------------------------------------------------------
    # Body: abstract driver vs platform-specific tools
    # ------------------------------------------------------------------
    ToolScenario(
        tool="body_app_launch",
        archetype="portable_launch",
        context=(
            "[beden] Aynı duman testi sırayla iOS simülatörü ve Android "
            "emülatöründe koşacak; aktif yüzeyi round-loop belirliyor. İlk "
            "adım: Arketic uygulamasını başlat."
        ),
        args={"bundle_id": "com.arketic.mobile"},
        reasoning=(
            "Senaryo platformdan bağımsız olmalı; ios_app_launch gibi platform "
            "aracı akışı tek yüzeye kilitler. body_app_launch aktif yüzeye "
            "uygun sürücüyü kendisi seçer."
        ),
        index=40,
    ),
    ToolScenario(
        tool="body_click",
        archetype="semantic_click_portable",
        context=(
            "[beden] Aktif yüzey telefon da olabilir tablet de; ekranda 'Gönder' "
            "düğmesinin var olduğu ax ağacından doğrulandı. Operatör: "
            "'Gönder'e bas.'"
        ),
        args={"target": "Gönder düğmesi"},
        reasoning=(
            "Koordinatlar yüzeye göre değişir; piksel tabanlı platform tıklaması "
            "taşınabilir değil. body_click semantik hedefi görüntü/AX üzerinden "
            "kendisi konumlar."
        ),
        index=41,
    ),
    ToolScenario(
        tool="body_press_key",
        archetype="abstract_back",
        context=(
            "[beden] Akış yanlış bir ayrıntı sayfasına girdi; önceki listeye "
            "dönülecek. Yüzey Android da olabilir, iOS da."
        ),
        args={"key_combo": "back"},
        reasoning=(
            "Geri hareketi platformlarda farklı uygulanır ama soyut sürücü "
            "'back' kombinasyonunu yüzeye çevirir. body_press_key tek çağrıda "
            "taşınabilir geri dönüş sağlar."
        ),
        index=42,
    ),
    ToolScenario(
        tool="body_type",
        archetype="portable_text_entry",
        context=(
            "[beden] Kayıt formunda e-posta alanına odaklanıldı; aynı test "
            "yarın Vision Pro yüzeyinde de koşacak."
        ),
        args={"text": "qa@arketic.tools", "target": "E-posta alanı"},
        reasoning=(
            "Girilecek şey içerik metni, kısayol değil; body_press_key "
            "kombinasyon basar, metin giremez. Taşınabilirlik için platform "
            "type araçları yerine body_type kullanıyorum."
        ),
        index=43,
    ),
    # ------------------------------------------------------------------
    # Body: ax_tree (structure) vs screenshot (pixels)
    # ------------------------------------------------------------------
    # --- trap: 'ekranda ne var?' while hunting a clickable -> ax_tree -------
    ToolScenario(
        tool="body_ax_tree",
        archetype="structure_over_pixels_trap",
        context=(
            "[beden] 'Sepete ekle' düğmesine tıklanacak ama etiketi ve "
            "hiyerarşideki yeri bilinmiyor. Operatör: 'Ekranda ne var, bir "
            "bak.'"
        ),
        args={},
        reasoning=(
            "Amaç tıklanabilir öğeyi güvenilir bulmak; ekran görüntüsü piksel "
            "verir, etiket vermez. body_ax_tree rolleri ve adları yapısal "
            "döker; tıklama hedefini oradan seçerim."
        ),
        index=44,
    ),
    ToolScenario(
        tool="body_screenshot",
        archetype="visual_glitch_pixels",
        context=(
            "[beden] Kullanıcı karanlık temada düğme renklerinin bozuk "
            "göründüğünü bildirdi; renk ve hizalama gözle doğrulanacak."
        ),
        args={},
        reasoning=(
            "Renk ve hizalama AX ağacında görünmez; bu tümüyle görsel bir "
            "doğrulama. body_screenshot gerçek pikselleri verir, ax_tree burada "
            "kör kalır."
        ),
        index=45,
    ),
    # ------------------------------------------------------------------
    # Body: storage_state save vs load
    # ------------------------------------------------------------------
    ToolScenario(
        tool="body_storage_state_save",
        archetype="persist_fresh_login",
        context=(
            "[beden] GitHub oturumu az önce iki adımlı doğrulamayla açıldı; bu "
            "oturum yarınki koşularda da gerekecek."
        ),
        args={"provider": "github", "project_slug": "selffork"},
        reasoning=(
            "Oturum taze ve geçerli; kaydedilmezse yarın 2FA dahil tüm giriş "
            "tekrarlanır. body_storage_state_save auth durumunu kalıcılaştırır; "
            "load ancak kayıt varken işe yarar."
        ),
        index=46,
    ),
    # --- trap: login screen visible BUT a saved state exists -> load --------
    ToolScenario(
        tool="body_storage_state_load",
        archetype="login_screen_load_trap",
        context=(
            "[beden] Yeni oturumda uygulama GitHub giriş ekranı gösteriyor; "
            "kayıtlarda 'github' için dünden kalma storage_state mevcut. "
            "Operatör: 'Giriş yap.'"
        ),
        args={"provider": "github", "project_slug": "selffork"},
        reasoning=(
            "Giriş ekranı görmek şifre yazmayı gerektirmez: kayıtlı oturum "
            "varken body_type ile kimlik girmek yavaş ve 2FA'ya takılır. Önce "
            "body_storage_state_load ile oturumu geri yüklüyorum."
        ),
        index=47,
    ),
    # ------------------------------------------------------------------
    # Refusals: risky requests are NOT executed; ask the operator
    # ------------------------------------------------------------------
    ToolScenario(
        tool="AskUserQuestion",
        archetype="refuse_mass_uninstall",
        context=(
            "[quest] Operatör: 'Kulaklıktaki oyunların hepsini kaldır, yer "
            "açalım.' Cihazda 24 uygulama kurulu; hangilerinin test verisi "
            "taşıdığı bilinmiyor."
        ),
        args={
            "questions": [
                {
                    "question": (
                        "24 uygulamanın tamamı kalıcı olarak silinsin mi, "
                        "yoksa yalnızca belirli oyunlar mı kaldırılsın?"
                    ),
                    "header": "Toplu silme onayı",
                    "options": [
                        {
                            "label": "Hepsini sil",
                            "description": (
                                "24 uygulama ve verileri geri döndürülemez "
                                "şekilde kaldırılır"
                            ),
                        },
                        {
                            "label": "Liste ver, ben seçeyim",
                            "description": (
                                "Önce quest_app_list çıktısından seçim yapılır"
                            ),
                        },
                        {"label": "Vazgeç"},
                    ],
                }
            ]
        },
        reasoning=(
            "Toplu uninstall geri döndürülemez ve kapsamı belirsiz; hangi "
            "uygulamaların korunacağını bilmeden quest_uninstall_app çağırmak "
            "veri kaybettirir. Önce onay alıyorum."
        ),
        index=48,
    ),
    ToolScenario(
        tool="AskUserQuestion",
        archetype="refuse_passthrough_off_no_guardian",
        context=(
            "[quest] quest_get_boundary az önce 'Guardian yapılandırılmamış' "
            "döndürdü; kullanıcı ayakta ve odada eşyalar var. Operatör: "
            "'Passthrough'u kapat, tam VR'a geçelim.'"
        ),
        args={
            "questions": [
                {
                    "question": (
                        "Guardian sınırı tanımlı değilken passthrough "
                        "kapatılırsa kullanıcı engellere çarpabilir. Nasıl "
                        "ilerleyelim?"
                    ),
                    "header": "Güvenlik onayı",
                    "options": [
                        {
                            "label": "Önce Guardian kurulsun",
                            "description": (
                                "Kullanıcı sınırı çizdikten sonra tam VR'a "
                                "geçilir"
                            ),
                        },
                        {
                            "label": "Yine de kapat",
                            "description": (
                                "Risk kabul edilerek passthrough kapatılır"
                            ),
                        },
                    ],
                }
            ]
        },
        reasoning=(
            "Sınır tanımsızken passthrough'u kapatmak fiziksel çarpma riski "
            "doğurur; güvenlik adımını onaysız atmam. quest_passthrough_disable "
            "yerine operatöre soruyorum."
        ),
        index=49,
    ),
]

__all__ = ["SCENARIOS"]
