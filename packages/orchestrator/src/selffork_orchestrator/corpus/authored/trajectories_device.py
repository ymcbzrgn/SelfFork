"""Agentic multi-tool trajectories (device) — act -> observe -> act -> ... done.

Android + iOS + browser + desktop uçtan uca akışlar. Her adımın reasoning'i,
bir önceki adımın gözlenen sonucuna dayanarak SIRADAKİ eylemi gerekçelendirir;
koordinatlar önceki adımın a11y bounds değerleriyle tutarlıdır. Küçük model bu
örneklerden "önce X, sonucu gör, sonra Y" zincirleme davranışını öğrenir.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import AgenticStep, AgenticTrajectory

TRAJECTORIES: list[AgenticTrajectory] = [
    AgenticTrajectory(
        name="android_signup_scroll_form",
        goal=(
            "[görev] Android'de FitTrack uygulamasında 'Ayşe Demir' / "
            "'ayse.demir@example.com' ile yeni hesap oluşturulacak. Form uzun; "
            "gönder butonu ekranın altında kalabilir."
        ),
        steps=[
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.fittrack"},
                result=(
                    "[sonuç] FitTrack açıldı; kayıt formu görünüyor: Ad ve "
                    "E-posta alanları ekranda, gönder butonu görünmüyor."
                ),
                reasoning="Uygulama kapalı; akışa uygulamayı başlatarak giriyorum.",
            ),
            AgenticStep(
                tool="android_a11y_tree",
                args={},
                result=(
                    "[sonuç] a11y ağacı: EditText#name bounds=[40,260,680,320], "
                    "EditText#email bounds=[40,360,680,420]. 'Hesap oluştur' "
                    "butonu ağaçta yok (ekran dışında)."
                ),
                reasoning=(
                    "Form görünüyor ama dokunmak için koordinat lazım; a11y "
                    "ağacı alanların bounds değerlerini verir."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 290},
                result="[sonuç] Ad alanı odakta, klavye açıldı.",
                reasoning=(
                    "name bounds=[40,260,680,320]; ortası (360,290). Önce ad "
                    "alanına odaklanıyorum."
                ),
            ),
            AgenticStep(
                tool="android_type",
                args={"text": "Ayşe Demir"},
                result="[sonuç] Alanda 'Ayşe Demir' yazıyor.",
                reasoning="Ad alanı odakta ve boş; adı düz type ile yazıyorum.",
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 390},
                result="[sonuç] E-posta alanı odakta.",
                reasoning=(
                    "Ad tamam; sıradaki alan e-posta, bounds ortası (360,390)."
                ),
            ),
            AgenticStep(
                tool="android_type",
                args={"text": "ayse.demir@example.com"},
                result="[sonuç] E-posta alanına adres girildi.",
                reasoning="Odaktaki e-posta alanına adresi yazıyorum.",
            ),
            AgenticStep(
                tool="android_scroll",
                args={"direction": "down", "amount": 400},
                result=(
                    "[sonuç] Sayfa kaydı; 'Hesap oluştur' butonu göründü, "
                    "bounds=[40,840,680,900]."
                ),
                reasoning=(
                    "İki alan da dolu ama gönder butonu a11y ağacında yoktu; "
                    "ekran dışındaki butonu görünür kılmak için aşağı "
                    "kaydırıyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 870},
                result="[sonuç] Form gönderildi; 'Hesabınız oluşturuldu' ekranı.",
                reasoning=(
                    "Kaydırma sonrası buton bounds=[40,840,680,900]; ortası "
                    "(360,870). Formu gönderiyorum."
                ),
            ),
            AgenticStep(
                tool="android_screen_text",
                args={},
                result="[sonuç] Ekran metni: 'Hesabınız oluşturuldu. Hoş geldin Ayşe!'",
                reasoning=(
                    "Başarı ekranı göründü; görevi kapatmadan önce metni okuyup "
                    "kaydın gerçekleştiğini doğruluyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="android_install_and_verify",
        goal=(
            "[görev] /sdcard/Download/fittrack-2.4.1.apk kurulacak, uygulama "
            "açılıp ilk açılışın sorunsuz olduğu doğrulanacak."
        ),
        steps=[
            AgenticStep(
                tool="android_install_app",
                args={"apk_path": "/sdcard/Download/fittrack-2.4.1.apk"},
                result="[sonuç] Kurulum başarılı (Success).",
                reasoning="Görev kurulumla başlıyor; önce APK'yı kuruyorum.",
            ),
            AgenticStep(
                tool="android_list_apps",
                args={},
                result=(
                    "[sonuç] Paket listesinde com.example.fittrack var "
                    "(versionName=2.4.1)."
                ),
                reasoning=(
                    "Kurulum 'Success' dedi; başlatmadan önce paketin gerçekten "
                    "listede olduğunu ve sürümü teyit ediyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.fittrack"},
                result=(
                    "[sonuç] Uygulama açıldı; bildirim izni diyaloğu çıktı: "
                    "'FitTrack bildirim göndermek istiyor'."
                ),
                reasoning="Paket doğrulandı; ilk açılışı test etmek için başlatıyorum.",
            ),
            AgenticStep(
                tool="android_a11y_tree",
                args={},
                result=(
                    "[sonuç] Diyalog: Button 'İzin ver' bounds=[90,820,350,880], "
                    "Button 'İzin verme' bounds=[370,820,630,880]."
                ),
                reasoning=(
                    "İzin diyaloğu akışı blokluyor; butonlara basmak için "
                    "bounds değerlerini alıyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 220, "y": 850},
                result="[sonuç] İzin verildi; diyalog kapandı, ana ekran yüklendi.",
                reasoning=(
                    "'İzin ver' bounds=[90,820,350,880]; ortası (220,850). "
                    "Bildirimlere izin verip devam ediyorum."
                ),
            ),
            AgenticStep(
                tool="android_screen_text",
                args={},
                result=(
                    "[sonuç] Ekran metni: 'Hoş geldin! Bugün 0 adım' — ana "
                    "ekran çökme olmadan yüklendi."
                ),
                reasoning=(
                    "Ana ekran göründü; ilk açılışın sorunsuz olduğunu ekran "
                    "metniyle doğrulayıp görevi bitiriyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="android_crash_recovery_clear_data",
        goal=(
            "[görev] BankApp açılışta çöküyor. Nedeni logdan teşhis edilecek, "
            "uygulama verisi temizlenip stabil açılış doğrulanacak."
        ),
        steps=[
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.bankapp"},
                result=(
                    "[sonuç] Uygulama açıldı ve ~1 sn içinde kapandı "
                    "('BankApp durduruldu' bildirimi)."
                ),
                reasoning=(
                    "Önce şikayeti kendim gözlemliyorum: çöküş gerçekten "
                    "açılışta mı oluyor?"
                ),
            ),
            AgenticStep(
                tool="android_logcat",
                args={"tag_filter": "AndroidRuntime", "max_lines": 50},
                result=(
                    "[sonuç] FATAL EXCEPTION: main — "
                    "SQLiteDatabaseCorruptException: file is not a database "
                    "(app_data/cache.db)."
                ),
                reasoning=(
                    "Çöküş doğrulandı; körlemesine müdahale etmek yerine "
                    "crash stack'ini logcat'ten okuyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_force_stop",
                args={"package": "com.example.bankapp"},
                result="[sonuç] Uygulama süreçleri durduruldu.",
                reasoning=(
                    "Log bozuk yerel veritabanını gösteriyor; veriyi "
                    "temizlemeden önce süreci tamamen durduruyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_clear_data",
                args={"package": "com.example.bankapp"},
                result="[sonuç] Uygulama verileri ve önbellek temizlendi.",
                reasoning=(
                    "Bozuk cache.db uygulama verisinde; force-stop sonrası "
                    "veriyi temizlemek çöküşün kökünü kaldırır."
                ),
            ),
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.bankapp"},
                result=(
                    "[sonuç] Uygulama açıldı; giriş ekranı geldi, 10 sn "
                    "boyunca stabil."
                ),
                reasoning=(
                    "Veri temiz; düzeltmenin işe yaradığını görmek için "
                    "uygulamayı yeniden başlatıyorum."
                ),
            ),
            AgenticStep(
                tool="android_screen_text",
                args={},
                result=(
                    "[sonuç] Ekran metni: 'BankApp — Giriş yap'. Çökme yok."
                ),
                reasoning=(
                    "Açılış stabil görünüyor; ekran metniyle giriş ekranının "
                    "geldiğini doğrulayıp görevi kapatıyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="android_invite_code_via_clipboard",
        goal=(
            "[görev] TeamChat'e 'INV-7K2M-99QX-B4TR' davet koduyla katılınacak. "
            "Kod uzun; elle yazmak hataya açık, pano üzerinden yapıştırılmalı."
        ),
        steps=[
            AgenticStep(
                tool="android_set_clipboard",
                args={"text": "INV-7K2M-99QX-B4TR"},
                result="[sonuç] Pano içeriği ayarlandı.",
                reasoning=(
                    "Kod uzun ve karışık; type ile yazım hatası riskine karşı "
                    "önce panoya koyuyorum."
                ),
            ),
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.example.teamchat"},
                result=(
                    "[sonuç] TeamChat açıldı; 'Davet kodu ile katıl' ekranı "
                    "görünüyor."
                ),
                reasoning="Kod panoda hazır; şimdi hedef uygulamayı açıyorum.",
            ),
            AgenticStep(
                tool="android_a11y_tree",
                args={},
                result=(
                    "[sonuç] a11y ağacı: EditText#invite_code "
                    "bounds=[60,400,660,460], Button 'Katıl' "
                    "bounds=[60,520,660,580]."
                ),
                reasoning=(
                    "Yapıştırma menüsünü alan üstünde açacağım; önce alanın "
                    "bounds değerini öğreniyorum."
                ),
            ),
            AgenticStep(
                tool="android_long_press",
                args={"x": 360, "y": 430},
                result=(
                    "[sonuç] Alan odaklandı; üstünde 'Yapıştır' balonu çıktı, "
                    "bounds=[300,340,420,390]."
                ),
                reasoning=(
                    "invite_code bounds=[60,400,660,460]; ortası (360,430). "
                    "Uzun basış, pano menüsünü açar."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 365},
                result=(
                    "[sonuç] Panodaki kod alana yapıştırıldı: "
                    "'INV-7K2M-99QX-B4TR'."
                ),
                reasoning=(
                    "'Yapıştır' balonu bounds=[300,340,420,390]; ortası "
                    "(360,365). Balona dokunup yapıştırıyorum."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 550},
                result="[sonuç] 'Takıma katıldın: Ürün Ekibi' ekranı açıldı.",
                reasoning=(
                    "Kod alanda doğru duruyor; 'Katıl' butonunun ortasına "
                    "(360,550) basıyorum."
                ),
            ),
            AgenticStep(
                tool="android_screen_text",
                args={},
                result="[sonuç] Ekran metni: 'Takıma katıldın: Ürün Ekibi'.",
                reasoning=(
                    "Katılım ekranı geldi; sonucu ekran metniyle doğrulayıp "
                    "akışı bitiriyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="ios_bank_biometric_login",
        goal=(
            "[görev] iOS simülatöründe BankApp kurulup Face ID ile giriş "
            "doğrulanacak. Simülatör şu an kapalı."
        ),
        steps=[
            AgenticStep(
                tool="ios_simulator_list",
                args={},
                result=(
                    "[sonuç] iPhone 15 — udid "
                    "A1B2C3D4-5E6F-7890-ABCD-EF1234567890, durum: Shutdown."
                ),
                reasoning=(
                    "Simülatör kapalı deniyor; boot için doğru udid'i "
                    "listeden alıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_simulator_boot",
                args={"udid": "A1B2C3D4-5E6F-7890-ABCD-EF1234567890"},
                result="[sonuç] Simülatör açıldı (Booted).",
                reasoning=(
                    "Listede tek uygun cihaz iPhone 15 ve Shutdown durumunda; "
                    "udid'iyle boot ediyorum."
                ),
            ),
            AgenticStep(
                tool="ios_install_app",
                args={"app_path": "/Users/dev/builds/BankApp.app"},
                result="[sonuç] Kuruldu: bundle id com.example.bank.",
                reasoning=(
                    "Cihaz Booted; uygulama henüz yok, derlenen .app paketini "
                    "kuruyorum."
                ),
            ),
            AgenticStep(
                tool="ios_app_launch",
                args={"bundle_id": "com.example.bank"},
                result=(
                    "[sonuç] BankApp açıldı; 'Face ID ile giriş yap' istemi "
                    "görünüyor."
                ),
                reasoning=(
                    "Kurulum bundle id'yi com.example.bank olarak verdi; onu "
                    "başlatıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_biometric_match",
                args={},
                result=(
                    "[sonuç] Biyometri eşleşmesi simüle edildi; istem kapandı, "
                    "hesap özeti yükleniyor."
                ),
                reasoning=(
                    "Ekranda Face ID istemi aktif; simülatörde başarılı "
                    "eşleşmeyi biometric_match tetikler."
                ),
            ),
            AgenticStep(
                tool="ios_screen_text",
                args={},
                result=(
                    "[sonuç] Ekran metni: 'Hesap Özeti — Bakiye ₺12.450,00'."
                ),
                reasoning=(
                    "Giriş sonrası ekranın gerçekten hesap özeti olduğunu "
                    "metinden doğrulayıp görevi kapatıyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="ios_dark_mode_visual_check",
        goal=(
            "[görev] Reader uygulamasının karanlık modu düzgün desteklediği "
            "görsel olarak doğrulanacak; test sonunda sistem light'a dönmeli."
        ),
        steps=[
            AgenticStep(
                tool="ios_app_launch",
                args={"bundle_id": "com.example.reader"},
                result=(
                    "[sonuç] Reader açıldı; makale listesi light temada "
                    "görünüyor."
                ),
                reasoning=(
                    "Karşılaştırma için önce uygulamayı mevcut (light) "
                    "durumda açıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_screenshot",
                args={},
                result="[sonuç] Light tema referans ekran görüntüsü alındı.",
                reasoning=(
                    "Dark'a geçmeden önce light referansını kaydediyorum; "
                    "kıyas ancak böyle yapılır."
                ),
            ),
            AgenticStep(
                tool="ios_set_appearance",
                args={"appearance": "dark"},
                result="[sonuç] Sistem görünümü dark oldu.",
                reasoning=(
                    "Referans hazır; şimdi sistemi dark'a alıp uygulamanın "
                    "tepkisine bakacağım."
                ),
            ),
            AgenticStep(
                tool="ios_screenshot",
                args={},
                result=(
                    "[sonuç] Ekran koyu arka plan + açık metinle render oldu; "
                    "beyaz kalan blok yok. Dark tema uygulanmış."
                ),
                reasoning=(
                    "Sistem dark'a geçti; uygulamanın temayı gerçekten "
                    "uyguladığını ekran görüntüsüyle doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="ios_set_appearance",
                args={"appearance": "light"},
                result="[sonuç] Sistem görünümü light'a geri alındı.",
                reasoning=(
                    "Doğrulama tamam; görev sistemin light'a dönmesini de "
                    "istiyor, ortamı eski haline getiriyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="ios_push_notification_deeplink",
        goal=(
            "[görev] Shop uygulamasına 'kargoya verildi' push'u gönderilecek; "
            "bildirime dokununca sipariş takibi ekranının açıldığı "
            "doğrulanacak."
        ),
        steps=[
            AgenticStep(
                tool="ios_app_state",
                args={"bundle_id": "com.example.shop"},
                result="[sonuç] Durum: Not running.",
                reasoning=(
                    "Push'un soğuk başlatma senaryosunu test etmesi için önce "
                    "uygulamanın kapalı olduğunu teyit ediyorum."
                ),
            ),
            AgenticStep(
                tool="ios_send_push_notification",
                args={
                    "payload_path": "/Users/dev/payloads/order_shipped.json",
                    "bundle_id": "com.example.shop",
                },
                result=(
                    "[sonuç] Bildirim teslim edildi; ekranın üstünde banner "
                    "belirdi."
                ),
                reasoning=(
                    "Uygulama kapalı; simülatöre hazır payload dosyasıyla "
                    "push gönderiyorum."
                ),
            ),
            AgenticStep(
                tool="ios_a11y_tree",
                args={},
                result=(
                    "[sonuç] a11y ağacı: NotificationBanner 'Siparişin kargoya "
                    "verildi #TR-4821' bounds=[0,60,390,140]."
                ),
                reasoning=(
                    "Banner göründü; dokunabilmek için bounds değerini a11y "
                    "ağacından alıyorum."
                ),
            ),
            AgenticStep(
                tool="ios_click",
                args={"x": 195, "y": 100},
                result=(
                    "[sonuç] Uygulama açıldı ve deep-link ile 'Sipariş "
                    "Takibi' ekranına gitti."
                ),
                reasoning=(
                    "Banner bounds=[0,60,390,140]; ortası (195,100). Banner'a "
                    "dokunup deep-link'i tetikliyorum."
                ),
            ),
            AgenticStep(
                tool="ios_screen_text",
                args={},
                result=(
                    "[sonuç] Ekran metni: 'Sipariş TR-4821 — Kargoya verildi'."
                ),
                reasoning=(
                    "Doğru ekrana inildiğini, payload'daki sipariş numarasının "
                    "ekranda olmasından doğruluyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="browser_login_to_account",
        goal=(
            "[görev] shop.example.com'a 'ayse@example.com' ile giriş yapılıp "
            "hesap sayfasına ulaşıldığı doğrulanacak."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={"url": "https://shop.example.com/login"},
                result="[sonuç] Navigasyon başladı; login sayfası isteniyor.",
                reasoning="Akış giriş sayfasında başlıyor; doğrudan URL'e gidiyorum.",
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "networkidle"},
                result="[sonuç] Sayfa yüklendi; ağ istekleri durdu.",
                reasoning=(
                    "Form alanları JS ile geliyor olabilir; etkileşimden önce "
                    "ağın sakinleşmesini bekliyorum."
                ),
            ),
            AgenticStep(
                tool="browser_query_selector",
                args={"target": "#email"},
                result=(
                    "[sonuç] #email bulundu: input[type=email], visible, "
                    "enabled."
                ),
                reasoning=(
                    "Yazmadan önce alanın DOM'da var, görünür ve etkin "
                    "olduğunu doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="browser_fill_form",
                args={
                    "fields": {
                        "#email": "ayse@example.com",
                        "#password": "S3cret!",
                    }
                },
                result="[sonuç] İki alan da dolduruldu.",
                reasoning=(
                    "Alan hazır; e-posta ve şifreyi tek seferde fill_form ile "
                    "dolduruyorum — iki ayrı type'tan daha az kırılgan."
                ),
            ),
            AgenticStep(
                tool="browser_click",
                args={"target": "button[type=submit]"},
                result="[sonuç] Tıklandı; sayfa yönlendirmeye başladı.",
                reasoning="Form dolu; submit butonuna tıklayıp girişi gönderiyorum.",
            ),
            AgenticStep(
                tool="browser_wait_for_url",
                args={"url_pattern": "**/account"},
                result="[sonuç] URL şimdi https://shop.example.com/account.",
                reasoning=(
                    "Tıklama yönlendirme başlattı; başarı sinyali /account "
                    "URL'ine varmak, onu bekliyorum."
                ),
            ),
            AgenticStep(
                tool="browser_get_title",
                args={},
                result="[sonuç] Başlık: 'Hesabım — Shop'.",
                reasoning=(
                    "URL doğru; sayfanın gerçekten hesap sayfası olduğunu "
                    "başlıktan da doğrulayıp bitiriyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="browser_catalog_lazy_load_extract",
        goal=(
            "[görev] books.example.com/catalog sayfasındaki kitap adları ve "
            "fiyatları JSON olarak çıkarılacak. Katalog lazy-load ile geç "
            "yükleniyor olabilir."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={"url": "https://books.example.com/catalog"},
                result="[sonuç] Navigasyon başladı.",
                reasoning="Veri katalog sayfasında; önce oraya gidiyorum.",
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "domcontentloaded"},
                result=(
                    "[sonuç] DOM hazır; ancak ürün ızgarası boş bir "
                    "yükleniyor-iskeleti gösteriyor."
                ),
                reasoning=(
                    "Önce hızlı sinyal olan DOM hazırlığını bekliyorum; "
                    "içerik durumunu buradan okuyacağım."
                ),
            ),
            AgenticStep(
                tool="browser_query_selector_all",
                args={"target": ".product-card", "max_items": 5},
                result="[sonuç] 0 eşleşme — kartlar henüz render edilmemiş.",
                reasoning=(
                    "İskelet görünüyordu; kartların gelip gelmediğini "
                    "seçiciyle sayarak kontrol ediyorum."
                ),
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "networkidle"},
                result="[sonuç] Ağ istekleri durdu; lazy-load tamamlandı.",
                reasoning=(
                    "0 eşleşme lazy-load'un sürdüğünü gösteriyor; DOM yerine "
                    "bu kez ağın boşalmasını bekliyorum."
                ),
            ),
            AgenticStep(
                tool="browser_query_selector_all",
                args={"target": ".product-card", "max_items": 5},
                result="[sonuç] 5 kart bulundu: .product-card x5, görünür.",
                reasoning=(
                    "Ağ sakinleşti; aynı seçiciyi tekrar deneyip içeriğin "
                    "artık geldiğini doğruluyorum."
                ),
            ),
            AgenticStep(
                tool="browser_extract",
                args={
                    "extraction_schema": {
                        "titles": "kitap adları listesi",
                        "prices": "fiyat listesi (₺)",
                    },
                    "instruction": (
                        "Katalog sayfasındaki her kitabın adını ve fiyatını "
                        "çıkar."
                    ),
                },
                result=(
                    "[sonuç] JSON: {'titles': ['Körlük', ...5 kayıt], "
                    "'prices': ['₺189,00', ...5 kayıt]}."
                ),
                reasoning=(
                    "Kartlar render oldu; artık şemalı extract ile adları ve "
                    "fiyatları yapılandırılmış çıkarabilirim."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="browser_event_registration_form",
        goal=(
            "[görev] event.example.com/register formu doldurulacak: ad, "
            "e-posta, şehir seçimi, şartlar onayı; kayıt sonrası teşekkür "
            "sayfası doğrulanacak."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={"url": "https://event.example.com/register"},
                result="[sonuç] Navigasyon başladı.",
                reasoning="Form kayıt sayfasında; ilk adım oraya gitmek.",
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "networkidle"},
                result=(
                    "[sonuç] Sayfa yüklendi; formda #name, #email, #city "
                    "select'i ve #terms kutusu görünüyor."
                ),
                reasoning=(
                    "Alanlara dokunmadan önce sayfanın tamamen oturmasını "
                    "bekliyorum."
                ),
            ),
            AgenticStep(
                tool="browser_fill_form",
                args={
                    "fields": {
                        "#name": "Ayşe Demir",
                        "#email": "ayse@example.com",
                    }
                },
                result="[sonuç] Ad ve e-posta alanları dolduruldu.",
                reasoning=(
                    "Yükleme tamam; metin alanlarını tek fill_form çağrısıyla "
                    "dolduruyorum."
                ),
            ),
            AgenticStep(
                tool="browser_select_option",
                args={"target": "#city", "label": "İstanbul"},
                result="[sonuç] #city için 'İstanbul' seçildi.",
                reasoning=(
                    "Şehir bir <select>; metin yazılamaz, select_option ile "
                    "etikete göre seçiyorum."
                ),
            ),
            AgenticStep(
                tool="browser_check",
                args={"target": "#terms"},
                result="[sonuç] #terms işaretlendi (checked=true).",
                reasoning=(
                    "Şartlar onayı zorunlu bir checkbox; click yerine "
                    "idempotent olan check'i kullanıyorum."
                ),
            ),
            AgenticStep(
                tool="browser_click",
                args={"target": "#submit"},
                result="[sonuç] Form gönderildi; sayfa yönleniyor.",
                reasoning=(
                    "Tüm alanlar dolu ve kutu işaretli; formu gönderiyorum."
                ),
            ),
            AgenticStep(
                tool="browser_wait_for_url",
                args={"url_pattern": "**/thanks"},
                result="[sonuç] URL: https://event.example.com/thanks.",
                reasoning=(
                    "Gönderim yönlendirme başlattı; başarının işareti /thanks "
                    "sayfası, onu bekliyorum."
                ),
            ),
            AgenticStep(
                tool="browser_text_content",
                args={"target": "h1"},
                result="[sonuç] h1 metni: 'Kaydınız alındı!'.",
                reasoning=(
                    "URL doğru; sayfa içeriğinin de teşekkür mesajı olduğunu "
                    "başlık metninden doğruluyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="desktop_meeting_note_append",
        goal=(
            "[görev] Masaüstünde Notes uygulamasındaki 'Toplantı Notları' "
            "penceresine bugünün notu eklenip kaydedilecek."
        ),
        steps=[
            AgenticStep(
                tool="desktop_list_apps",
                args={},
                result=(
                    "[sonuç] Çalışan uygulamalar: Notes, Safari, Terminal."
                ),
                reasoning=(
                    "Önce Notes'un açık olup olmadığını görmem lazım; açık "
                    "değilse ayrıca başlatmam gerekirdi."
                ),
            ),
            AgenticStep(
                tool="desktop_list_windows",
                args={"app_name": "Notes"},
                result=(
                    "[sonuç] Notes pencereleri: 'Toplantı Notları', "
                    "'Alışveriş listesi'."
                ),
                reasoning=(
                    "Notes çalışıyor; doğru pencereyi seçmek için pencere "
                    "başlıklarını listeliyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={"app_name": "Notes", "window_title": "Toplantı Notları"},
                result=(
                    "[sonuç] 'Toplantı Notları' penceresi öne geldi ve odakta."
                ),
                reasoning=(
                    "İki pencere var; yazı yanlış pencereye gitmesin diye "
                    "başlıkla hedef pencereyi odaklıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_type",
                args={
                    "text": "3 Temmuz — sprint planlama: S-Train başlıyor.\n"
                },
                result="[sonuç] Metin pencereye yazıldı.",
                reasoning=(
                    "Odak doğru pencerede; notu klavye girdisi olarak "
                    "yazıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "cmd+s"},
                result="[sonuç] Kaydet kısayolu gönderildi; not kaydedildi.",
                reasoning=(
                    "Yazı eklendi ama kalıcı değil; cmd+s ile dosyayı "
                    "kaydediyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_screenshot",
                args={},
                result=(
                    "[sonuç] Ekran görüntüsünde 'Toplantı Notları' penceresi "
                    "ve eklenen '3 Temmuz — sprint planlama' satırı görünüyor."
                ),
                reasoning=(
                    "Son adım doğrulama: notun gerçekten pencerede durduğunu "
                    "ekran görüntüsüyle teyit ediyorum."
                ),
            ),
        ],
    ),
    AgenticTrajectory(
        name="browser_to_terminal_api_key",
        goal=(
            "[görev] docs.example.com'daki örnek API anahtarı sayfadan alınıp "
            "masaüstündeki Terminal penceresine yapıştırılacak."
        ),
        steps=[
            AgenticStep(
                tool="browser_navigate",
                args={"url": "https://docs.example.com/api/auth"},
                result="[sonuç] Navigasyon başladı.",
                reasoning="Anahtar dokümantasyon sayfasında; önce oraya gidiyorum.",
            ),
            AgenticStep(
                tool="browser_wait_for_load_state",
                args={"state": "load"},
                result="[sonuç] Sayfa yüklendi.",
                reasoning=(
                    "Statik doküman sayfası; load olayını beklemek okuma için "
                    "yeterli."
                ),
            ),
            AgenticStep(
                tool="browser_text_content",
                args={"target": "#api-key-example code"},
                result="[sonuç] Metin: 'sk-demo-4f9a2b7c'.",
                reasoning=(
                    "Sayfa hazır; anahtarı ekran görüntüsünden değil, doğrudan "
                    "code elementinin metninden okuyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_set_clipboard",
                args={"text": "sk-demo-4f9a2b7c"},
                result="[sonuç] Pano içeriği ayarlandı.",
                reasoning=(
                    "Okunan değeri tarayıcıdan terminale taşımanın güvenli "
                    "yolu sistem panosu; anahtarı panoya koyuyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_focus_window",
                args={"app_name": "Terminal"},
                result="[sonuç] Terminal penceresi öne geldi ve odakta.",
                reasoning=(
                    "Yapıştırma odaklı pencereye gider; önce Terminal'i öne "
                    "alıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_press_key",
                args={"key_combo": "cmd+v"},
                result=(
                    "[sonuç] Yapıştırıldı; komut satırında 'sk-demo-4f9a2b7c' "
                    "duruyor."
                ),
                reasoning=(
                    "Terminal odakta ve pano dolu; cmd+v ile anahtarı "
                    "yapıştırıyorum."
                ),
            ),
            AgenticStep(
                tool="desktop_screenshot",
                args={},
                result=(
                    "[sonuç] Ekran görüntüsünde Terminal'de anahtar metni "
                    "görünüyor."
                ),
                reasoning=(
                    "Aktarımın gerçekleştiğini ekran görüntüsüyle doğrulayıp "
                    "görevi kapatıyorum."
                ),
            ),
        ],
    ),
]

__all__ = ["TRAJECTORIES"]
