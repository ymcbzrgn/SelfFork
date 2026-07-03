"""Mobile DEEP — the less-common Android/iOS tools + arg-value judgment.

Complements ``phones.py`` (observation/input/lifecycle/install/sim/logs) with
the tools it did NOT cover: deeplink/intent/broadcast, shell/dumpsys/property,
push/pull, screenrecord, notification injection, iOS open_url/push/appearance/
status-bar/record. Authored by Claude (Opus) after the Fable mobile-deep agent
produced nothing; every scenario is gate-validated against the real registry.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

SCENARIOS: list[ToolScenario] = [
    # --- open a URL: deeplink vs intent vs launch+navigate ------------------
    ToolScenario(
        tool="android_deeplink",
        archetype="app_url_scheme_direct",
        context=(
            "[android] Arketic uygulaması kurulu. Operatör: 'Sipariş 42'yi aç' "
            "— uygulamanın derin bağlantı şeması var: arketic://orders/42."
        ),
        args={"url": "arketic://orders/42"},
        reasoning=(
            "Hedef doğrudan bir ekran; uygulamayı açıp elle gezinmek yerine "
            "deeplink am start VIEW ile tek adımda o ekrana gider."
        ),
        index=0,
    ),
    ToolScenario(
        tool="android_intent",
        archetype="system_action_no_scheme",
        context=(
            "[android] Bir dosya paylaşım akışı test edilecek; uygulamanın "
            "deeplink şeması yok, ama SEND intent'ini karşılıyor."
        ),
        args={
            "action": "android.intent.action.SEND",
            "component": "com.arketic.app/.ShareActivity",
        },
        reasoning=(
            "Derin bağlantı yok; hedef belirli bir Activity ve sistem "
            "action'ı. deeplink URL ister, doğru araç açık component'li intent."
        ),
        index=1,
    ),
    ToolScenario(
        tool="ios_open_url",
        archetype="ios_universal_link",
        context=(
            "[ios] Safari üzerinden gelen bir evrensel bağlantının uygulamayı "
            "doğru ekrana açtığı doğrulanacak: https://arketic.app/orders/42."
        ),
        args={"url": "https://arketic.app/orders/42"},
        reasoning=(
            "iOS'ta deeplink/universal link açmanın aracı ios_open_url; "
            "android_deeplink Android tarafıdır, burada geçmez."
        ),
        index=2,
    ),
    # --- inspect system state: shell vs dumpsys vs get_property -------------
    ToolScenario(
        tool="android_dumpsys",
        archetype="service_state_structured",
        context=(
            "[android] Uygulama arka planda konum alamıyor. Sorun izin mi, "
            "servis mi? Konum servisinin anlık durumu gerekiyor."
        ),
        args={"service": "location"},
        reasoning=(
            "Soru belirli bir sistem servisinin yapılandırılmış durumu; "
            "genel shell yerine dumpsys location tam o servisi döker."
        ),
        index=3,
    ),
    ToolScenario(
        tool="android_get_property",
        archetype="single_build_prop",
        context=(
            "[android] Testin ön koşulu cihazın API seviyesini bilmek. "
            "Tek bir sistem özelliği okunacak."
        ),
        args={"key": "ro.build.version.sdk"},
        reasoning=(
            "İhtiyaç tek bir build özelliği; dumpsys koca bir servis döker, "
            "shell fazladan yorum ister. Tek prop için get_property nettir."
        ),
        index=4,
    ),
    ToolScenario(
        tool="android_shell",
        archetype="arbitrary_no_dedicated_tool",
        context=(
            "[android] Uygulamanın yazdığı özel dosya sayısı sayılacak; bunu "
            "veren özel bir araç yok, ama tek satır kabuk komutu çözer."
        ),
        args={"command": "ls /sdcard/Android/data/com.arketic.app/files | wc -l"},
        reasoning=(
            "Bu iş için ayrılmış araç yok; dumpsys servis durumu, "
            "get_property tek prop verir. Serbest komut ancak android_shell'dir."
        ),
        index=5,
    ),
    ToolScenario(
        tool="android_set_property",
        archetype="toggle_debug_flag",
        context=(
            "[android] Ayrıntılı ağ günlüğünü açmak için uygulamanın okuduğu "
            "debug bayrağı set edilecek, sonra hata tekrar üretilecek."
        ),
        args={"key": "debug.arketic.netlog", "value": "1"},
        reasoning=(
            "Repro öncesi bayrağı YAZMAK gerek; get_property yalnız okur. "
            "Değer yazma işi set_property."
        ),
        index=6,
    ),
    # --- file transfer direction: pull vs push -----------------------------
    ToolScenario(
        tool="android_pull",
        archetype="fetch_generated_report",
        context=(
            "[android] Uygulama /sdcard/Download/rapor.csv üretti; bu dosya "
            "incelenmek üzere bilgisayara alınacak."
        ),
        args={"remote": "/sdcard/Download/rapor.csv", "local": "/work/rapor.csv"},
        reasoning=(
            "Dosya CİHAZDAN host'a gelecek; push ters yön (host->cihaz). "
            "Cihazdan çekmek pull'un işi."
        ),
        index=7,
    ),
    ToolScenario(
        tool="android_push",
        archetype="stage_test_fixture",
        context=(
            "[android] İçe aktarma testi için bir örnek CSV cihaza konacak: "
            "/work/fixture.csv -> /sdcard/Download/."
        ),
        args={"local": "/work/fixture.csv", "remote": "/sdcard/Download/fixture.csv"},
        reasoning=(
            "Dosya bilgisayardan CİHAZA gidecek; pull cihazdan çeker. "
            "Host'tan cihaza koymak push ile yapılır."
        ),
        index=8,
    ),
    # --- capture: screenrecord vs screenshot -------------------------------
    ToolScenario(
        tool="android_screenrecord_start",
        archetype="animation_glitch_motion",
        context=(
            "[android] Liste kaydırılırken kısa bir titreme oluşuyor; tek "
            "kare screenshot bunu yakalayamadı."
        ),
        args={"output_path": "/sdcard/glitch.mp4"},
        reasoning=(
            "Zamana yayılan hareketli bir hata; screenshot dondurulmuş kare "
            "verir. Sürekliliği yakalamak için ekran kaydı gerekir."
        ),
        index=9,
    ),
    # --- inject events: notification / broadcast ---------------------------
    ToolScenario(
        tool="android_notification_post",
        archetype="test_notification_handling",
        context=(
            "[android] Uygulamanın bir bildirime dokununca doğru ekrana "
            "gittiği test edilecek; önce test bildirimi düşürülmeli."
        ),
        args={"title": "Yeni sipariş", "body": "Sipariş #42 onay bekliyor"},
        reasoning=(
            "Akışın ilk adımı bir bildirim ÜRETMEK; tıklama sonrası "
            "davranışı ancak ortada bir bildirim varken test edilir."
        ),
        index=10,
    ),
    ToolScenario(
        tool="android_broadcast",
        archetype="simulate_app_event",
        context=(
            "[android] Uygulama, senkron tetikleyen özel bir yayın (broadcast) "
            "dinliyor; bu olayı simüle edip tepkisini görmek istiyoruz."
        ),
        args={"action": "com.arketic.app.ACTION_SYNC_NOW"},
        reasoning=(
            "Uygulama bir broadcast receiver ile tetikleniyor; deeplink ekran "
            "açar, intent Activity başlatır. Yayın olayını broadcast gönderir."
        ),
        index=11,
    ),
    # --- iOS deep tools -----------------------------------------------------
    ToolScenario(
        tool="ios_send_push_notification",
        archetype="ios_remote_push_test",
        context=(
            "[ios] Uzak bildirimle uygulamanın rozet sayısını güncellediği "
            "test edilecek; hazır bir payload dosyası var."
        ),
        args={
            "payload_path": "/work/push_payload.json",
            "bundle_id": "com.arketic.app",
        },
        reasoning=(
            "Test edilen APNs uzak bildirimi; android_notification_post yerel "
            "ve Android'dir. iOS simülatöründe uzak push ios_send_push ile."
        ),
        index=12,
    ),
    ToolScenario(
        tool="ios_set_appearance",
        archetype="ios_force_dark",
        context=(
            "[ios] Koyu temada bir kontrast sorunu bildirildi; simülatör koyu "
            "moda alınıp ekran doğrulanacak."
        ),
        args={"appearance": "dark"},
        reasoning=(
            "Tema sorununu görmek için cihaz koyu moda ALINMALI; set_appearance "
            "görünümü doğrudan değiştirir."
        ),
        index=13,
    ),
    ToolScenario(
        tool="ios_record_video_start",
        archetype="ios_flow_recording",
        context=(
            "[ios] Onboarding animasyonundaki takılma aralıklı; tek kare "
            "kanıtlamıyor, akışın videosu gerekiyor."
        ),
        args={"output_path": "/work/onboarding.mp4"},
        reasoning=(
            "Aralıklı hareketli hata için süreklilik gerek; ios_screenshot tek "
            "kare verir, ios_record_video akışı yakalar."
        ),
        index=14,
    ),
    ToolScenario(
        tool="ios_status_bar_override",
        archetype="clean_statusbar_for_screenshot",
        context=(
            "[ios] Mağaza görselleri için ekran görüntüleri alınacak; durum "
            "çubuğu tutarlı görünmeli (saat 9:41, tam sinyal)."
        ),
        args={"time": "9:41", "wifi_bars": 3, "cellular_bars": 4},
        reasoning=(
            "Pazarlama görsellerinde durum çubuğu sabitlenir; override saati "
            "ve sinyalleri deterministik yapar, screenshot öncesi doğru adım."
        ),
        index=15,
    ),
    # --- shell vs dedicated: don't reach for shell when a tool exists -------
    ToolScenario(
        tool="android_dumpsys",
        archetype="prefer_dumpsys_over_shell",
        context=(
            "[android] Pil sağlığı ve şarj durumu okunacak. Operatör 'shell'e "
            "gir' dedi ama pil için yapılandırılmış çıktı isteniyor."
        ),
        args={"service": "battery"},
        reasoning=(
            "'Shell' dese de istenen pil servisinin yapılandırılmış durumu; "
            "dumpsys battery bunu ayrıştırılabilir verir, ham shell'e gerek yok."
        ),
        index=16,
    ),
    ToolScenario(
        tool="android_intent",
        archetype="intent_with_data_uri",
        context=(
            "[android] Harita ekranının bir coğrafi konumu doğru açtığı test "
            "edilecek; geo: URI'siyle VIEW intent'i gönderilecek."
        ),
        args={
            "action": "android.intent.action.VIEW",
            "data": "geo:41.0082,28.9784?q=Ofis",
        },
        reasoning=(
            "Hedef bir veri URI'siyle görüntüleyiciyi tetiklemek; deeplink "
            "uygulama şeması ister. Genel VIEW + data intent doğru araç."
        ),
        index=17,
    ),
]

__all__ = ["SCENARIOS"]
