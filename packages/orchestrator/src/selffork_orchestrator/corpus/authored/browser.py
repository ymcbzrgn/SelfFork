"""Authored reasoning scenarios for the 63 ``browser_*`` web-automation tools.

Every scenario carries a non-None ``reasoning``: the point of this bank is the
judgement, not the syntax. Coverage targets the clusters a small model mixes
up, and each cluster shows BOTH sides plus at least one trap (operator wording
suggests tool A, situation demands tool B):

* abstraction level -- act / agent / observe (intent) vs click / type / check /
  select_option / hover / upload_file (element). Traps: "tıkla" wording that
  really needs check / select_option / hover / upload_file / observe.
* navigation vs waiting -- navigate / back / forward / reload (do something)
  vs wait_for_load_state / wait_for_url / wait_for_response (wait for a
  condition). Trap: "git" wording that must become back or wait_for_url.
* extraction -- extract (structured, LLM) vs text_content / get_attribute /
  get_html / dom_snapshot (raw) vs screenshot (visual); console vs network log.
* locators -- query_selector vs query_selector_all vs smart_locator (no-LLM).
* tabs -- new_tab / switch_tab / close_tab / list_tabs / duplicate_tab /
  get_active_tab. Refusal: unknown tab order -> list_tabs first.
* storage -- cookies get/set/clear vs local_storage get/set/clear (which store
  actually holds the data decides, not the operator's word "çerez").
* network -- block_url_pattern vs mock_response vs intercept_request(log) vs
  set_extra_headers.
* emulation & stealth -- emulate_device vs set_viewport vs set_user_agent;
  set_geolocation vs set_proxy (GPS API vs IP); set_locale vs set_timezone;
  set_color_scheme; enable_stealth as error recovery.

Refusal cases (act was requested, observing/waiting is correct): #3 observe
before an ambiguous click, #15 wait_for_load_state before clicking a loading
SPA, #32 list_tabs before switching blindly. Error recovery: #6 retype with
clear_first, #22 dom_snapshot after a stale-selector failure, #54
enable_stealth after bot detection. Every scenario is gated against the real
registry by the builder.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

SCENARIOS: list[ToolScenario] = [
    # ==================================================================
    # A. Abstraction level: intent (act/agent/observe) vs element ops
    # ==================================================================
    ToolScenario(
        tool="browser_click",
        archetype="precise_click_known_selector",
        context=(
            "[tarayıcı] dom_snapshot az önce alındı: ödeme düğmesi "
            "'#btn-checkout' olarak haritalandı, görünür ve tıklanabilir. "
            "Operatör: 'Ödemeye geç.'"
        ),
        args={"target": "#btn-checkout"},
        reasoning=(
            "Hedef eleman selector düzeyinde kesin biliniyor; act'in LLM "
            "yorumuna gerek yok. Kesin selector varken element seviyesinde "
            "click en hızlı ve belirsizliksiz yol."
        ),
        index=0,
    ),
    ToolScenario(
        tool="browser_act",
        archetype="single_step_no_selector",
        context=(
            "[tarayıcı] Yeni açılan kampanya sayfası daha önce haritalanmadı; "
            "DOM incelenmedi. Operatör: 'Şu çerez bildirimini kabul edip "
            "kapat.'"
        ),
        args={
            "instruction": (
                "Çerez bildirimindeki kabul düğmesine tıkla ve bildirimi kapat"
            )
        },
        reasoning=(
            "Tek adımlık bir niyet var ama elimde selector yok; click hedef "
            "ister. Çok adımlı agent aşırı olur; tek doğal dil eylemi için "
            "act doğru soyutlama seviyesi."
        ),
        index=1,
    ),
    ToolScenario(
        tool="browser_agent",
        archetype="multi_step_goal",
        context=(
            "[tarayıcı] E-ticaret sitesinin ana sayfasındayız. Operatör: 'Şu "
            "kablosuz kulaklığı bul, sepete ekle, sepette adedi 2 yap.'"
        ),
        args={
            "goal": (
                "Kablosuz kulaklığı ara, ürünü sepete ekle ve sepette adedi "
                "2 yap"
            ),
            "max_steps": 8,
        },
        reasoning=(
            "Bu tek eylem değil, ara durumları belirsiz çok adımlı bir "
            "hedef; act tek adım çevirir. Gözlem-eylem döngüsü gerektiği "
            "için agent'ı adım sınırıyla başlatıyorum."
        ),
        index=2,
    ),
    # --- REFUSAL: operator says click, ambiguity demands observe first ---
    ToolScenario(
        tool="browser_observe",
        archetype="ambiguous_target_observe_first",
        context=(
            "[tarayıcı] Sayfada üç ayrı 'Gönder' düğmesi var: bülten formu, "
            "iletişim formu ve sipariş formu. Görev siparişi tamamlamak. "
            "Operatör: 'Gönder'e bas.'"
        ),
        args={"description": "sipariş formunun gönder düğmesi"},
        reasoning=(
            "Üç aday varken kör tıklamak yanlış formu gönderebilir; talebe "
            "rağmen önce observe ile doğru elemanı kesinleştiriyorum. Eylem "
            "ancak hedef netleşince güvenli."
        ),
        index=3,
    ),
    # --- TRAP: natural-language wording but selector already verified ---
    ToolScenario(
        tool="browser_click",
        archetype="act_wording_selector_known",
        context=(
            "[tarayıcı] query_selector '#accept-btn' az önce doğrulandı: "
            "görünür ve etkin. Operatör: 'Bir zahmet şu kabul et düğmesine "
            "basıver.'"
        ),
        args={"target": "#accept-btn"},
        reasoning=(
            "Söylem doğal dilde ama hedef zaten '#accept-btn' olarak "
            "doğrulanmış; act ile LLM'e yeniden yorumlatmak gereksiz gecikme "
            "ve risk. Bilinen selector'a doğrudan click."
        ),
        index=4,
    ),
    ToolScenario(
        tool="browser_type",
        archetype="type_into_known_field",
        context=(
            "[tarayıcı] Arama kutusu dom_snapshot'ta '#search-input' olarak "
            "görünüyor ve boş. Operatör: 'Aramaya gürültü önleyici kulaklık "
            "yaz.'"
        ),
        args={"text": "gürültü önleyici kulaklık", "target": "#search-input"},
        reasoning=(
            "Alanın selector'ı kesin ve işlem düz metin girişi; act'in "
            "yorum katmanına gerek yok. type hedefe doğrudan ve "
            "öngörülebilir şekilde yazar."
        ),
        index=5,
    ),
    # --- error recovery: stale text in field -> clear_first ---
    ToolScenario(
        tool="browser_type",
        archetype="retype_clear_first",
        context=(
            "[tarayıcı] Önceki deneme yarım kaldı: '#username' alanında eski "
            "değer 'test_user' duruyor. Operatör: 'Kullanıcı adını "
            "operator01 olarak gir.'"
        ),
        args={"text": "operator01", "target": "#username", "clear_first": True},
        reasoning=(
            "Alan boş değil; düz type eski metnin sonuna ekler ve "
            "'test_useroperator01' oluşur. clear_first=true ile önce "
            "temizleyip doğru değeri yazıyorum."
        ),
        index=6,
    ),
    # --- TRAP: 'tıkla' wording but goal is a checked state -> check ---
    ToolScenario(
        tool="browser_check",
        archetype="ensure_checked_not_click",
        context=(
            "[tarayıcı] Kayıt formundaki sözleşme onay kutusunun mevcut "
            "durumu bilinmiyor (işaretli olabilir). Operatör: 'Sözleşme "
            "kutusuna tıkla.'"
        ),
        args={"target": "#terms-checkbox"},
        reasoning=(
            "Asıl hedef kutunun tıklanması değil işaretli kalması; click "
            "zaten işaretliyse onayı kaldırır. check idempotenttir: durum "
            "ne olursa olsun işaretli bırakır."
        ),
        index=7,
    ),
    # --- TRAP: 'menüyü aç, tıkla' but element is a native <select> ---
    ToolScenario(
        tool="browser_select_option",
        archetype="native_select_not_click",
        context=(
            "[tarayıcı] Teslimat formundaki şehir alanı native bir <select> "
            "(select#city). Operatör: 'Şehir menüsünü aç, İstanbul'a tıkla.'"
        ),
        args={"target": "select#city", "label": "İstanbul"},
        reasoning=(
            "Native <select>'in açılır listesi tarayıcı DOM'u dışında "
            "çizilir; click ile seçenek tıklanamaz. Doğru araç label ile "
            "select_option."
        ),
        index=8,
    ),
    # --- TRAP: 'menüyü aç' but menu opens on hover, click navigates ---
    ToolScenario(
        tool="browser_hover",
        archetype="hover_reveals_menu",
        context=(
            "[tarayıcı] Üst menüdeki 'Hesabım' öğesi alt menüyü üzerine "
            "gelince açıyor; tıklanırsa profil sayfasına gidiyor. Operatör: "
            "'Hesabım menüsünü aç, seçenekleri göreceğiz.'"
        ),
        args={"target": "nav .account-menu"},
        reasoning=(
            "Amaç alt menüyü açık tutmak; click sayfadan ayrılır ve menüyü "
            "hiç göstermez. Alt menüyü tetikleyen doğru etkileşim hover."
        ),
        index=9,
    ),
    # --- TRAP: clicking a file input opens an OS dialog we cannot drive ---
    ToolScenario(
        tool="browser_upload_file",
        archetype="file_dialog_trap",
        context=(
            "[tarayıcı] Başvuru formunda 'Dosya Seç' düğmesi var "
            "(input[type=file]). Operatör: 'Dosya Seç'e tıkla, kimlik.png "
            "dosyasını yükle.'"
        ),
        args={
            "target": "input[type=file]",
            "file_path": "C:/Users/operator/belgeler/kimlik.png",
        },
        reasoning=(
            "Tıklamak işletim sisteminin dosya diyaloğunu açar ve otomasyon "
            "o diyaloğu süremez. upload_file dosya yolunu input'a doğrudan "
            "bağlar; click burada çıkmaz sokak."
        ),
        index=10,
    ),
    # ==================================================================
    # B. Navigation (do) vs waiting (condition)
    # ==================================================================
    ToolScenario(
        tool="browser_navigate",
        archetype="direct_url_fresh",
        context=(
            "[tarayıcı] Boş sekmedeyiz; hedef adres biliniyor. Operatör: "
            "'Kariyer sayfasına git: https://sirket.example.com/kariyer.'"
        ),
        args={"url": "https://sirket.example.com/kariyer"},
        reasoning=(
            "Adres açıkça verilmiş ve geçmişte dönülecek bir sayfa yok; "
            "back/forward geçmiş ister, beklenecek bir koşul da yok. "
            "Doğrudan navigate."
        ),
        index=11,
    ),
    # --- TRAP: 'git' wording but the page is one step back in history ---
    ToolScenario(
        tool="browser_back",
        archetype="history_back_not_navigate",
        context=(
            "[tarayıcı] Arama sonuçlarından bir ürün detayına girildi; sonuç "
            "sayfasında seçili filtreler ve kaydırma konumu vardı. Operatör: "
            "'Sonuç listesine git.'"
        ),
        args={},
        reasoning=(
            "'Git' dense de liste bir önceki geçmiş kaydı; navigate URL'i "
            "sıfırdan yükleyip filtre ve kaydırma durumunu bozar. back "
            "geçmişteki hali koruyarak döner."
        ),
        index=12,
    ),
    ToolScenario(
        tool="browser_forward",
        archetype="forward_after_back",
        context=(
            "[tarayıcı] Az önce ürün detayından listeye back ile dönüldü. "
            "Operatör: 'Fiyata bir daha bakacağım, ürün detayına geri dön.'"
        ),
        args={},
        reasoning=(
            "Hedef sayfa geçmişte bir adım ileride duruyor; yeniden arama "
            "ya da navigate dolambaçlı. forward aynı detaya tek adımda döner."
        ),
        index=13,
    ),
    ToolScenario(
        tool="browser_reload",
        archetype="refresh_same_page",
        context=(
            "[tarayıcı] Stok takip sayfası 10 dakikadır açık. Operatör: "
            "'Stok değişmiş olabilir, sayfayı yenile de bakalım.'"
        ),
        args={},
        reasoning=(
            "Aynı URL'de güncel içerik isteniyor; navigate ile aynı adresi "
            "yeniden yazmak dolaylı ve geçmişe kayıt ekler. reload aktif "
            "sekmeyi yerinde tazeler."
        ),
        index=14,
    ),
    # --- REFUSAL: operator says click now, page is still loading ---
    ToolScenario(
        tool="browser_wait_for_load_state",
        archetype="wait_before_click_refusal",
        context=(
            "[tarayıcı] 'Sepete ekle' tıklandı; SPA hâlâ spinner gösteriyor "
            "ve ağ istekleri sürüyor. Operatör: 'Hemen satın al düğmesine "
            "bas.'"
        ),
        args={"state": "networkidle"},
        reasoning=(
            "Yükleme bitmeden tıklamak boşa ya da yanlış elemana gider; "
            "talebe rağmen önce ağın durulmasını bekliyorum. Eylem ancak "
            "stabil DOM üzerinde güvenli."
        ),
        index=15,
    ),
    # --- TRAP: 'panele git' but a login redirect chain is in flight ---
    ToolScenario(
        tool="browser_wait_for_url",
        archetype="redirect_in_flight_trap",
        context=(
            "[tarayıcı] Giriş formu gönderildi; site birkaç yönlendirme "
            "adımıyla panele geçiyor. Operatör: 'Panele git: /dashboard.'"
        ),
        args={"url_pattern": "**/dashboard**"},
        reasoning=(
            "Yönlendirme zinciri sürerken navigate zinciri keser ve oturum "
            "kurulumu yarım kalabilir. Doğrusu URL'in /dashboard'a "
            "ulaşmasını wait_for_url ile beklemek."
        ),
        index=16,
    ),
    ToolScenario(
        tool="browser_wait_for_response",
        archetype="xhr_without_url_change",
        context=(
            "[tarayıcı] Arama kutusuna metin yazıldı; sonuçlar sayfa URL'i "
            "değişmeden /api/search XHR çağrısıyla geliyor. Sonuçlar "
            "gelince okunacak."
        ),
        args={"url_pattern": "**/api/search**"},
        reasoning=(
            "URL değişmediği için wait_for_url hiç sinyal vermez; "
            "load_state de tekil XHR'ı garanti etmez. Beklenen koşul "
            "belirli isteğin yanıtı: wait_for_response."
        ),
        index=17,
    ),
    # ==================================================================
    # C. Extraction: structured vs raw vs visual; console vs network
    # ==================================================================
    ToolScenario(
        tool="browser_extract",
        archetype="structured_multifield",
        context=(
            "[tarayıcı] Ürün listeleme sayfasında 20 kart var; operatör her "
            "ürünün adını, fiyatını ve stok bilgisini tablo halinde istiyor."
        ),
        args={
            "extraction_schema": {
                "urun_adi": "Ürün başlığı",
                "fiyat": "Satış fiyatı, TL",
                "stok": "Stok durumu",
            },
            "instruction": "Listedeki her ürün kartı için alanları çıkar",
        },
        reasoning=(
            "İstenen çıktı alan-değer yapısında ve birden çok kart "
            "kapsıyor; get_html ham döker, text_content tek eleman okur. "
            "Şemalı yapısal çıkarım extract'in işi."
        ),
        index=18,
    ),
    # --- TRAP: 'çıkar' wording but one element with a known selector ---
    ToolScenario(
        tool="browser_text_content",
        archetype="single_field_no_llm",
        context=(
            "[tarayıcı] Ürün detayında fiyat tek bir elemanda duruyor: "
            "'.price-tag'. Operatör: 'Fiyat bilgisini sayfadan çıkar.'"
        ),
        args={"target": ".price-tag"},
        reasoning=(
            "'Çıkar' dense de hedef tek elemanın metni ve selector belli; "
            "şemalı extract gereksiz LLM maliyeti ekler. text_content aynı "
            "bilgiyi doğrudan okur."
        ),
        index=19,
    ),
    ToolScenario(
        tool="browser_get_html",
        archetype="raw_markup_for_parser",
        context=(
            "[tarayıcı] Ekipteki ayrıştırıcı script sayfanın tam işlenmiş "
            "HTML kaynağını bekliyor; içerik yorumlanmayacak, olduğu gibi "
            "aktarılacak."
        ),
        args={},
        reasoning=(
            "İhtiyaç yorumlanmış veri değil ham işaretleme; extract şema "
            "ister, dom_snapshot sadeleştirip bilgi kaybeder. Kaynağı "
            "olduğu gibi veren get_html."
        ),
        index=20,
    ),
    ToolScenario(
        tool="browser_get_attribute",
        archetype="href_not_visible_text",
        context=(
            "[tarayıcı] 'İndir' bağlantısının görünen metni değil işaret "
            "ettiği adres gerekli; eleman 'a.download-link'."
        ),
        args={"target": "a.download-link", "name": "href"},
        reasoning=(
            "text_content görünen yazıyı verir; adres href niteliğinde "
            "durur. Tek elemanın tek niteliği için get_attribute en dar ve "
            "doğru araç."
        ),
        index=21,
    ),
    # --- error recovery: stale selectors -> re-ground with dom_snapshot ---
    ToolScenario(
        tool="browser_dom_snapshot",
        archetype="reground_after_stale_selector",
        context=(
            "[tarayıcı] click '#old-submit' 'element not found' hatası "
            "verdi; site güncellenmiş, eldeki harita geçersiz. Operatör "
            "forma devam etmemizi istiyor."
        ),
        args={},
        reasoning=(
            "Selector'larım bayat; körlemesine yenilerini denemek yeni "
            "hatalar üretir. dom_snapshot etkileşimli öğeleri yeniden "
            "haritalar; screenshot görsel verir ama selector üretmez."
        ),
        index=22,
    ),
    # --- TRAP: 'incele' but the question is visual, not DOM ---
    ToolScenario(
        tool="browser_screenshot",
        archetype="visual_layout_check",
        context=(
            "[tarayıcı] Operatör: 'Sayfayı incele, üst menünün tasarımı "
            "bozulmuş mu?' CSS taşması şüphesi var."
        ),
        args={},
        reasoning=(
            "Görsel bozulma DOM'da ya da HTML'de görünmez; get_html sayfanın "
            "doğru çizilip çizilmediğini söyleyemez. Yerleşimi ancak "
            "screenshot gösterir."
        ),
        index=23,
    ),
    ToolScenario(
        tool="browser_screenshot_element",
        archetype="single_component_visual",
        context=(
            "[tarayıcı] Rapora yalnızca satış grafiği bileşeninin görüntüsü "
            "eklenecek; grafik '.sales-chart' kapsayıcısında."
        ),
        args={"target": ".sales-chart"},
        reasoning=(
            "Tam sayfa screenshot alıp kırpmak gereksiz iş ve gürültü; "
            "hedef tek bileşen. screenshot_element yalnızca o elemanı verir."
        ),
        index=24,
    ),
    # --- TRAP: 'ağ hatalarına bak' but evidence points to a JS error ---
    ToolScenario(
        tool="browser_get_console_logs",
        archetype="js_error_not_network",
        context=(
            "[tarayıcı] Sayfa bembeyaz; ağ kaydında tüm istekler 200 dönmüş. "
            "Operatör: 'Ağ hatalarına bak.'"
        ),
        args={},
        reasoning=(
            "İstekler başarılıysa sorun ağda değil; beyaz sayfa tipik JS "
            "istisnası belirtisi. Ağ kaydı değil konsol kayıtları hatayı "
            "gösterir."
        ),
        index=25,
    ),
    # --- TRAP (reverse): 'konsola bak' but the failure is a bad XHR ---
    ToolScenario(
        tool="browser_get_network_log",
        archetype="failed_xhr_not_console",
        context=(
            "[tarayıcı] Konsolda hata yok ama ürün listesi boş geliyor; "
            "verinin API'den gelip gelmediği belirsiz. Operatör: 'Konsol "
            "hatalarına baksana.'"
        ),
        args={},
        reasoning=(
            "Konsol zaten temiz; boş liste büyük olasılıkla başarısız ya da "
            "boş dönen XHR. Yanıt kodlarını ve istekleri get_network_log "
            "gösterir."
        ),
        index=26,
    ),
    # ==================================================================
    # D. Locators: first match vs all matches vs no-LLM heuristic
    # ==================================================================
    ToolScenario(
        tool="browser_query_selector",
        archetype="existence_check_first_match",
        context=(
            "[tarayıcı] Ödeme düğmesinin bu sayfada olup olmadığı belirsiz; "
            "tıklamadan önce '#pay-btn' var mı ve görünür mü teyit edilecek."
        ),
        args={"target": "#pay-btn"},
        reasoning=(
            "Tek elemanın varlığını ve görünürlüğünü doğrulamak istiyorum; "
            "query_selector_all liste döker, gereksiz. İlk eşleşme yeterli: "
            "query_selector."
        ),
        index=27,
    ),
    ToolScenario(
        tool="browser_query_selector_all",
        archetype="count_all_matches",
        context=(
            "[tarayıcı] Operatör filtre uygulandıktan sonra kaç ürün kartı "
            "kaldığını soruyor; kartlar '.product-card' selector'ında."
        ),
        args={"target": ".product-card", "max_items": 50},
        reasoning=(
            "Soru tüm eşleşmelerin sayısı; query_selector yalnızca ilkini "
            "verir. query_selector_all'ı üst sınırla çalıştırıp tam listeyi "
            "alıyorum."
        ),
        index=28,
    ),
    # --- TRAP: observe would fit, but no LLM budget -> smart_locator ---
    ToolScenario(
        tool="browser_smart_locator",
        archetype="no_llm_budget_locator",
        context=(
            "[tarayıcı] LLM bütçesi bu oturum için tükendi; 'sepete ekle' "
            "düğmesinin yerini betimlemeyle bulmak gerekiyor."
        ),
        args={"description": "sepete ekle düğmesi"},
        reasoning=(
            "observe LLM çağrısı gerektirir ve bütçe yok; smart_locator "
            "LLM'siz sezgisel DOM taramasıyla aynı işi görür. Kısıt altında "
            "doğru arayıcı bu."
        ),
        index=29,
    ),
    # ==================================================================
    # E. Tabs
    # ==================================================================
    # --- TRAP: navigate would destroy in-progress form -> new_tab ---
    ToolScenario(
        tool="browser_new_tab",
        archetype="open_aside_preserve_form",
        context=(
            "[tarayıcı] Aktif sekmede yarısı doldurulmuş uzun bir başvuru "
            "formu var. Operatör: 'Yardım dokümanını aç: "
            "https://docs.example.com/form.'"
        ),
        args={"url": "https://docs.example.com/form"},
        reasoning=(
            "Aktif sekmede navigate formdaki girilmiş veriyi kaybettirir. "
            "Dokümanı new_tab ile yan sekmede açıp formu olduğu gibi "
            "koruyorum."
        ),
        index=30,
    ),
    # --- TRAP: 'aç' wording but the tab is already open -> switch ---
    ToolScenario(
        tool="browser_switch_tab",
        archetype="tab_already_open",
        context=(
            "[tarayıcı] list_tabs çıktısı: 0 mağaza, 1 sepet, 2 webmail. "
            "Operatör: 'Maili aç, onay kodu gelmiş mi bakalım.'"
        ),
        args={"index": 2},
        reasoning=(
            "'Aç' dense de webmail zaten 2. sekmede açık; new_tab kopya "
            "oturum ve karışıklık yaratır. Var olan sekmeye switch_tab ile "
            "geçmek yeterli."
        ),
        index=31,
    ),
    # --- REFUSAL: unknown tab order, don't switch blindly ---
    ToolScenario(
        tool="browser_list_tabs",
        archetype="inventory_before_switch",
        context=(
            "[tarayıcı] Az önce siteden art arda iki popup sekmesi açıldı; "
            "sekme dizilimi artık bilinmiyor. Operatör: 'Üçüncü sekmeye geç.'"
        ),
        args={},
        reasoning=(
            "Dizilim popuplarla değişti; körlemesine switch_tab yanlış "
            "sekmeyi aktive edebilir. Önce list_tabs ile envanter alıp "
            "doğru index'i saptamak gerek."
        ),
        index=32,
    ),
    ToolScenario(
        tool="browser_close_tab",
        archetype="close_known_popup",
        context=(
            "[tarayıcı] list_tabs teyit etti: index 3 istenmeyen bir reklam "
            "popup'ı. Operatör: 'Şu reklamı kapat.'"
        ),
        args={"index": 3},
        reasoning=(
            "Kapatılacak sekmenin index'i az önce doğrulandı; index'i açık "
            "vermek aktif sekmeyi yanlışlıkla kapatma riskini sıfırlar. "
            "Önce switch etmek fazladan adım."
        ),
        index=33,
    ),
    ToolScenario(
        tool="browser_duplicate_tab",
        archetype="clone_for_comparison",
        context=(
            "[tarayıcı] Ürün sayfasında karşılaştırma yapılacak: kopyada "
            "kupon denenecek, orijinal sekme referans olarak kalacak."
        ),
        args={},
        reasoning=(
            "Aynı URL'i new_tab'a elle taşımak yerine duplicate_tab aktif "
            "sekmeyi tek adımda klonlar; orijinal referans sekme dokunulmadan "
            "kalır."
        ),
        index=34,
    ),
    ToolScenario(
        tool="browser_get_active_tab",
        archetype="focus_uncertain",
        context=(
            "[tarayıcı] Bir bağlantı yeni sekme açtı ve odak değişmiş "
            "olabilir; bir sonraki tıklamanın hangi sekmeye gideceği "
            "belirsiz."
        ),
        args={},
        reasoning=(
            "Eylemler her zaman aktif sekmeye gider ve odağın yeri şüpheli. "
            "list_tabs tüm listeyi döker; soru yalnızca aktif olan, onu "
            "get_active_tab söyler."
        ),
        index=35,
    ),
    # ==================================================================
    # F. Storage: cookies vs localStorage (the store decides, not wording)
    # ==================================================================
    ToolScenario(
        tool="browser_cookies_get",
        archetype="inspect_session_cookie",
        context=(
            "[tarayıcı] Oturum beklenmedik şekilde düştü; session çerezinin "
            "süresinin dolup dolmadığı kontrol edilecek. Site: "
            "https://portal.example.com."
        ),
        args={"url": "https://portal.example.com"},
        reasoning=(
            "Soru çerezin mevcut değeri ve ömrü; localStorage değil çerez "
            "deposu ilgili. cookies_get'i URL ile daraltıp yalnızca portalın "
            "çerezlerini okuyorum."
        ),
        index=36,
    ),
    ToolScenario(
        tool="browser_cookies_set",
        archetype="restore_saved_session",
        context=(
            "[tarayıcı] Önceki oturumdan kaydedilmiş session çerezi elimizde; "
            "tekrar giriş yapmadan oturumu geri yüklemek istiyoruz."
        ),
        args={
            "cookies": [
                {
                    "name": "session_id",
                    "value": "9f3a1c77",
                    "domain": ".portal.example.com",
                    "path": "/",
                }
            ]
        },
        reasoning=(
            "Oturum kimliği çerezde taşınıyor; local_storage_set çerez "
            "deposuna yazamaz. Kayıtlı çerezi cookies_set ile bağlama geri "
            "koyuyorum."
        ),
        index=37,
    ),
    # --- TRAP pair 1: auth is cookie-based -> cookies_clear ---
    ToolScenario(
        tool="browser_cookies_clear",
        archetype="fresh_user_cookie_auth",
        context=(
            "[tarayıcı] Ağ kaydında oturumun Set-Cookie başlığıyla kurulduğu "
            "görüldü. Operatör: 'Oturum verisini temizle, temiz kullanıcıyla "
            "test edeceğiz.'"
        ),
        args={},
        reasoning=(
            "Kimlik bu sitede çerez tabanlı; local_storage_clear oturumu "
            "düşürmez. Temiz kullanıcı için çerez deposunu cookies_clear "
            "ile boşaltmak gerekir."
        ),
        index=38,
    ),
    # --- TRAP pair 2: operator says 'çerez' but token lives in LS ---
    ToolScenario(
        tool="browser_local_storage_get",
        archetype="token_in_localstorage",
        context=(
            "[tarayıcı] Operatör: 'Auth çerezini oku.' Ancak ağ kaydında "
            "Set-Cookie yok; uygulama JWT'yi localStorage'daki 'auth_token' "
            "anahtarında tutuyor."
        ),
        args={"key": "auth_token"},
        reasoning=(
            "Operatör 'çerez' dese de kanıt token'ın localStorage'da "
            "olduğunu gösteriyor; cookies_get boş döner. Doğru depo "
            "local_storage_get ile okunur."
        ),
        index=39,
    ),
    ToolScenario(
        tool="browser_local_storage_set",
        archetype="enable_feature_flag",
        context=(
            "[tarayıcı] QA için 'beta_features' bayrağının açılması "
            "gerekiyor; uygulama bu bayrağı localStorage'dan okuyor."
        ),
        args={"key": "beta_features", "value": "true"},
        reasoning=(
            "Bayrak çerez değil localStorage anahtarı; cookies_set "
            "uygulamanın okuduğu yere yazmaz. local_storage_set doğru "
            "depoya yazar."
        ),
        index=40,
    ),
    # --- TRAP: keep the session alive, clear only localStorage ---
    ToolScenario(
        tool="browser_local_storage_clear",
        archetype="reset_tour_keep_session",
        context=(
            "[tarayıcı] Karşılama turu localStorage'daki 'tour_done' kaydı "
            "yüzünden bir daha çıkmıyor; operatör turu yeniden test etmek "
            "istiyor ama oturum açık kalmalı."
        ),
        args={},
        reasoning=(
            "cookies_clear oturumu da düşürür, bu istenmiyor; tur durumu "
            "yalnızca localStorage'da. local_storage_clear hedefi daraltıp "
            "oturumu korur."
        ),
        index=41,
    ),
    # ==================================================================
    # G. Network: block vs mock vs log vs headers
    # ==================================================================
    ToolScenario(
        tool="browser_block_url_pattern",
        archetype="cut_ad_requests",
        context=(
            "[tarayıcı] Sayfa üçüncü taraf reklam istekleri yüzünden yavaş; "
            "test sırasında ads.example.net alan adına hiçbir istek "
            "çıkmamalı."
        ),
        args={"url_pattern": "**ads.example.net**"},
        reasoning=(
            "İstekler tamamen kesilecek, sahte yanıt gerekmiyor; "
            "mock_response gövde uydurur, intercept log içindir. Düz kesme "
            "işi block_url_pattern."
        ),
        index=42,
    ),
    # --- TRAP: 'engelle' wording but UI needs a controlled body ---
    ToolScenario(
        tool="browser_mock_response",
        archetype="mock_not_block",
        context=(
            "[tarayıcı] Backend'in /api/products ucu henüz hazır değil. "
            "Operatör: 'Şu isteği engelle de UI'ı test edelim.' Test edilecek "
            "şey boş-liste görünümü; UI kontrollü bir JSON bekliyor."
        ),
        args={
            "url_pattern": "**/api/products**",
            "body": '{"items": [], "total": 0}',
            "status": 200,
        },
        reasoning=(
            "Block isteği koparır ve UI ağ hatası durumuna düşer; test "
            "edilmek istenen boş-durum görünümü. Kontrollü gövdeyi ancak "
            "mock_response verir."
        ),
        index=43,
    ),
    ToolScenario(
        tool="browser_intercept_request",
        archetype="log_without_breaking",
        context=(
            "[tarayıcı] KVKK denetimi: sayfanın hangi üçüncü taraf analitik "
            "uçlarına istek attığı kayıt altına alınacak; istekler "
            "kesilmeyecek."
        ),
        args={"url_pattern": "**analytics**", "mode": "log"},
        reasoning=(
            "Amaç trafiği bozmadan gözlemlemek; block_url_pattern keser, "
            "mock sahte yanıt döner. intercept_request mode=log istekleri "
            "akıtırken kaydeder."
        ),
        index=44,
    ),
    # --- TRAP: 'çerez ekle' but the API wants an Authorization header ---
    ToolScenario(
        tool="browser_set_extra_headers",
        archetype="bearer_not_cookie",
        context=(
            "[tarayıcı] Test API'si her istekte 'Authorization: Bearer' "
            "başlığı bekliyor. Operatör: 'Kimlik çerezini ekle de erişelim.'"
        ),
        args={"headers": {"Authorization": "Bearer test-token-123"}},
        reasoning=(
            "Sunucu kimliği çerezde değil Authorization başlığında arıyor; "
            "cookies_set işe yaramaz. Başlığı tüm isteklere "
            "set_extra_headers ekler."
        ),
        index=45,
    ),
    # ==================================================================
    # H. Emulation, identity, stealth
    # ==================================================================
    # --- TRAP: 'pencereyi küçült' but the real need is a device profile ---
    ToolScenario(
        tool="browser_emulate_device",
        archetype="true_mobile_profile",
        context=(
            "[tarayıcı] Site mobil sürümünü UA ve dokunmatik desteğe göre "
            "sunuyor. Operatör: 'Pencereyi telefon boyutuna küçült, mobil "
            "siteyi test edelim.'"
        ),
        args={"device_name": "iPhone 13"},
        reasoning=(
            "set_viewport yalnız pencereyi küçültür; UA ve dokunmatik "
            "masaüstü kalır, site mobil sürümü hiç sunmaz. Tam profil için "
            "emulate_device gerekir."
        ),
        index=46,
    ),
    # --- TRAP (reverse): only the CSS breakpoint, not a device ---
    ToolScenario(
        tool="browser_set_viewport",
        archetype="breakpoint_only",
        context=(
            "[tarayıcı] Masaüstü sitesinin 768px CSS kırılımı test edilecek; "
            "sitenin mobil sürümüne düşmesi istenmiyor."
        ),
        args={"width": 768, "height": 1024},
        reasoning=(
            "emulate_device UA'yı da değiştirir ve site mobil sürüme geçer; "
            "test masaüstü CSS'i üzerinde. Yalnızca boyutu değiştiren "
            "set_viewport doğru."
        ),
        index=47,
    ),
    ToolScenario(
        tool="browser_set_user_agent",
        archetype="ua_string_only",
        context=(
            "[tarayıcı] Sitenin 'tarayıcınız eski' uyarısı yalnızca UA "
            "dizesine bakıyor; görünüm ve pencere boyutu aynı kalmalı."
        ),
        args={
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/91.0.4472.124 Safari/537.36"
            )
        },
        reasoning=(
            "Kontrol yalnız UA dizesinde; emulate_device viewport ve "
            "dokunmatiği de değiştirip testi bulandırır. En dar müdahale "
            "set_user_agent."
        ),
        index=48,
    ),
    ToolScenario(
        tool="browser_set_geolocation",
        archetype="gps_api_location",
        context=(
            "[tarayıcı] Harita sayfası navigator.geolocation ile konum izni "
            "istiyor; İstanbul'daki şubelerin listelenmesi bekleniyor."
        ),
        args={"latitude": 41.0082, "longitude": 28.9784, "accuracy": 50},
        reasoning=(
            "Site konumu tarayıcının GPS API'sinden okuyor; proxy IP'yi "
            "değiştirir ama GPS'i değil. set_geolocation tam bu API'nin "
            "döndürdüğü değeri ayarlar."
        ),
        index=49,
    ),
    # --- TRAP: 'konumu değiştir' but the block is IP-based -> proxy ---
    ToolScenario(
        tool="browser_set_proxy",
        archetype="ip_block_not_gps",
        context=(
            "[tarayıcı] Video 'bu içerik ülkenizde kullanılamıyor' diyor; "
            "kısıt IP adresine göre uygulanıyor. Operatör: 'Konumu Almanya "
            "yap.'"
        ),
        args={"server": "http://de-proxy.example.com:8080"},
        reasoning=(
            "set_geolocation yalnız GPS API'sini değiştirir; IP tabanlı "
            "kısıt aynen kalır. Çıkış IP'sini değiştirebilen tek araç "
            "set_proxy."
        ),
        index=50,
    ),
    # --- TRAP pair: language vs clock ---
    ToolScenario(
        tool="browser_set_locale",
        archetype="language_via_locale",
        context=(
            "[tarayıcı] Site arayüz dilini tarayıcının locale / "
            "Accept-Language değerine göre seçiyor; Almanca arayüz test "
            "edilecek."
        ),
        args={"locale": "de-DE"},
        reasoning=(
            "Dil seçimi locale'e bağlı; set_timezone yalnız saati etkiler, "
            "geolocation dil değiştirmez. set_locale Accept-Language'i "
            "Almancaya çeker."
        ),
        index=51,
    ),
    ToolScenario(
        tool="browser_set_timezone",
        archetype="clock_skew_not_language",
        context=(
            "[tarayıcı] Takvim uygulamasında dil doğru ama etkinlik saatleri "
            "3 saat kaymış görünüyor. Operatör: 'Dili Türkçe yap da "
            "düzelsin.'"
        ),
        args={"timezone_id": "Europe/Istanbul"},
        reasoning=(
            "Sorun dil değil saat: kayma saat dilimi farkından geliyor; "
            "set_locale saatleri düzeltmez. Doğru müdahale set_timezone ile "
            "Europe/Istanbul."
        ),
        index=52,
    ),
    ToolScenario(
        tool="browser_set_color_scheme",
        archetype="dark_theme_media_query",
        context=(
            "[tarayıcı] Tasarım ekibi karanlık tema stillerini doğrulamak "
            "istiyor; site temayı prefers-color-scheme medya sorgusuna göre "
            "seçiyor."
        ),
        args={"scheme": "dark"},
        reasoning=(
            "evaluate ile CSS zorlamak sitenin gerçek tema mantığını atlar; "
            "test edilen şey medya sorgusunun kendisi. set_color_scheme "
            "tercihi tarayıcı düzeyinde emüle eder."
        ),
        index=53,
    ),
    # --- error recovery: bot detection -> stealth before retry ---
    ToolScenario(
        tool="browser_enable_stealth",
        archetype="bot_detected_stealth_first",
        context=(
            "[tarayıcı] Site otomasyonu algılayıp 'robot doğrulaması' "
            "sayfasına yönlendirdi; navigator.webdriver sızıntısı olası. "
            "İşlem yeniden denenecek."
        ),
        args={},
        reasoning=(
            "Aynı parmak iziyle reload sonucu değiştirmez; tespit "
            "webdriver/plugins sızıntısından geliyor. Önce enable_stealth "
            "ile izleri kapatıp sonra denemek doğru sıra."
        ),
        index=54,
    ),
]

__all__ = ["SCENARIOS"]
