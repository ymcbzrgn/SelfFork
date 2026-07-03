"""Browser + workflow DEEP — advanced web + dev/control tools.

Complements ``browser.py`` and ``workflow_control.py`` with tools they did not
cover: browser drag/pdf/evaluate/uncheck/screenshot_element/mock/intercept/
smart_locator/proxy, and workflow repo_clone/fork/view/workflow_run/eas_submit/
export/state_restore/skill validate-export-sync/ui_verify_color/set_cli_effort.
Authored by Claude (Opus) after the Fable browser/workflow-deep agent failed on
auth; every scenario is gate-validated against the real registry.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

SCENARIOS: list[ToolScenario] = [
    # --- browser advanced ---------------------------------------------------
    ToolScenario(
        tool="browser_drag_and_drop",
        archetype="reorder_by_drag",
        context=(
            "[tarayıcı] Kanban benzeri listede 3. kart en üste taşınacak "
            "(sürükle-bırak arayüzü). Tek tık kartı taşımaz."
        ),
        args={"source": "#card-3", "target": "#column-top"},
        reasoning=(
            "İşlem bir öğeyi bir noktadan diğerine sürüklemek; click yalnız "
            "seçer, taşımaz. Kaynak ve hedefi olan jest drag_and_drop'tur."
        ),
        index=0,
    ),
    ToolScenario(
        tool="browser_get_pdf",
        archetype="export_page_pdf",
        context=(
            "[tarayıcı] Fatura sayfasının birebir çıktısı arşive PDF olarak "
            "alınacak; görsel değil, yazdırılabilir belge isteniyor."
        ),
        args={"output_path": "/work/fatura.pdf"},
        reasoning=(
            "İstenen yazdırılabilir belge; screenshot piksel görüntü verir, "
            "metni seçilemez. Sayfayı PDF'e dökmek get_pdf ile olur."
        ),
        index=1,
    ),
    ToolScenario(
        tool="browser_evaluate",
        archetype="read_computed_js_value",
        context=(
            "[tarayıcı] Sepet toplamı DOM'da değil, JS değişkeninde "
            "(window.cart.total) tutuluyor; bu değer doğrulanacak."
        ),
        args={"js_code": "return window.cart.total"},
        reasoning=(
            "Değer görünür bir düğümde değil çalışma-zamanı JS durumunda; "
            "extract/text_content DOM okur. JS bağlamını evaluate çalıştırır."
        ),
        index=2,
    ),
    ToolScenario(
        tool="browser_uncheck",
        archetype="ensure_unchecked",
        context=(
            "[tarayıcı] Bülten onayı kutusu işaretli geliyor; testte KAPALI "
            "olması gerekiyor."
        ),
        args={"target": "#newsletter-optin"},
        reasoning=(
            "Amaç kutunun işaretsiz KALMASI; click işaretliyse kaldırır ama "
            "işaretsizse işaretler (belirsiz). uncheck durumu kesinler."
        ),
        index=3,
    ),
    ToolScenario(
        tool="browser_screenshot_element",
        archetype="single_widget_capture",
        context=(
            "[tarayıcı] Yalnız fiyat rozetinin görseli bir hata kaydına "
            "eklenecek; tüm sayfa değil o bileşen isteniyor."
        ),
        args={"target": ".price-badge"},
        reasoning=(
            "Hedef tek bileşen; tam sayfa screenshot alıp kırpmak gürültü ve "
            "fazla iş. Doğrudan o öğeyi screenshot_element yakalar."
        ),
        index=4,
    ),
    ToolScenario(
        tool="browser_mock_response",
        archetype="force_empty_state",
        context=(
            "[tarayıcı] 'Sipariş yok' boş-durum ekranı test edilecek; gerçek "
            "API dolu dönüyor. İstek engellenirse UI ağ hatası gösterir."
        ),
        args={"url_pattern": "**/api/orders", "body": "[]"},
        reasoning=(
            "İstenen kontrollü boş yanıt; block isteği koparır ve hata "
            "durumu doğurur. Sahte boş gövdeyi mock_response döndürür."
        ),
        index=5,
    ),
    ToolScenario(
        tool="browser_intercept_request",
        archetype="observe_traffic_only",
        context=(
            "[tarayıcı] Analitik isteklerinin hangi olayları gönderdiği "
            "kaydedilecek; trafiği BOZMADAN gözlemlemek gerek."
        ),
        args={"url_pattern": "**/analytics/**"},
        reasoning=(
            "Amaç trafiği kesmeden izlemek; block keser, mock sahte yanıt "
            "verir. Gözlem için intercept_request loglar, akış sürer."
        ),
        index=6,
    ),
    ToolScenario(
        tool="browser_smart_locator",
        archetype="semantic_locator_no_selector",
        context=(
            "[tarayıcı] 'Sepete ekle' butonunun kararlı bir CSS seçicisi yok; "
            "sınıflar derlemede değişiyor. Eleman anlamıyla bulunacak."
        ),
        args={"description": "ürün kartındaki 'Sepete ekle' butonu"},
        reasoning=(
            "Sabit seçici yok ve observe LLM turu pahalı; smart_locator "
            "elemanı doğal-dil tarifinden sezgisel DOM'da bulur."
        ),
        index=7,
    ),
    ToolScenario(
        tool="browser_set_proxy",
        archetype="route_through_exit_ip",
        context=(
            "[tarayıcı] İçerik IP tabanlı coğrafi kısıtlı; çıkış IP'si "
            "Almanya'ya taşınacak."
        ),
        args={"server": "http://de-proxy.example.com:8080"},
        reasoning=(
            "Kısıt IP'ye göre; set_geolocation yalnız GPS API'sini değiştirir. "
            "Çıkış IP'sini değiştiren tek araç set_proxy."
        ),
        index=8,
    ),
    # --- workflow / dev advanced -------------------------------------------
    ToolScenario(
        tool="github_repo_clone",
        archetype="clone_own_repo",
        context=(
            "[git] Üzerinde yazma yetkin olan arketic/fieldnote-app yerelde "
            "yok; branch açıp çalışmak için indirilecek."
        ),
        args={"repo": "arketic/fieldnote-app"},
        reasoning=(
            "Depoya push yetkin var; fork gereksiz bir kopya çıkarır. Kendi "
            "deponu doğrudan clone edip branch açarsın."
        ),
        index=9,
    ),
    ToolScenario(
        tool="github_repo_fork",
        archetype="fork_no_push_rights",
        context=(
            "[git] Bir üst-akım kütüphanesine (vendor/upstream-lib) düzeltme "
            "yollanacak ama push yetkin yok."
        ),
        args={"repo": "vendor/upstream-lib"},
        reasoning=(
            "Yazma yetkisi yokken dalı push edemezsin; clone salt yerel kopya "
            "verir, PR tabanı olmaz. Katkı için önce fork gerekir."
        ),
        index=10,
    ),
    ToolScenario(
        tool="github_workflow_run",
        archetype="dispatch_known_workflow",
        context=(
            "[git] Sürüm iş akışının adı listeden doğrulandı (release.yml); "
            "artık elle tetiklenecek."
        ),
        args={"repo": "arketic/fieldnote-app", "workflow": "release.yml"},
        reasoning=(
            "İş akışının adı biliniyor ve dispatch destekli; keşif bitti. "
            "Tetikleme workflow_run ile yapılır."
        ),
        index=11,
    ),
    ToolScenario(
        tool="expo_export",
        archetype="static_bundle_not_build",
        context=(
            "[expo] JS paketinin statik bir kopyası CDN'e konacak; mağaza "
            "ikili derlemesi ya da OTA yayını istenmiyor."
        ),
        args={},
        reasoning=(
            "İstenen statik bundle; eas_build ikili üretir, publish OTA "
            "yayınlar. Yerel statik çıktıyı expo_export verir."
        ),
        index=12,
    ),
    ToolScenario(
        tool="crash_state_restore",
        archetype="rollback_to_label",
        context=(
            "[crash] Riskli bir denemeden sonra ekran bozuldu; daha önce "
            "'deney-oncesi' etiketiyle alınan anlık duruma dönülecek."
        ),
        args={"label": "deney-oncesi"},
        reasoning=(
            "Var olan bir kayda dönülecek; snapshot yeni kayıt alır, diff "
            "karşılaştırır. Eski duruma dönüş restore ile olur."
        ),
        index=13,
    ),
    ToolScenario(
        tool="skill_validate",
        archetype="validate_before_sync",
        context=(
            "[skill] 'kanban-mover' becerisi elle düzenlendi; diğer CLI'lara "
            "dağıtmadan önce SKILL.md'nin geçerliliği doğrulanacak."
        ),
        args={"name": "kanban-mover"},
        reasoning=(
            "Dağıtımdan önce beceri tanımı sağlam mı bakılmalı; sync bozuk "
            "beceriyi de yayar. Önce validate ile şema/dosya kontrolü."
        ),
        index=14,
    ),
    ToolScenario(
        tool="skill_export",
        archetype="export_share_bundle",
        context=(
            "[skill] 'kanban-mover' bir meslektaşa gönderilecek; kanonik "
            "dizini değiştirmeden tek dosyalık paket üretilecek."
        ),
        args={"name": "kanban-mover", "output_path": "/work/kanban-mover.skill"},
        reasoning=(
            "Amaç paylaşılabilir bir paket; sync yerel CLI dizinlerine yayar, "
            "kanonik kopyayı oynatır. Taşınabilir dosyayı export üretir."
        ),
        index=15,
    ),
    ToolScenario(
        tool="ui_verify_color_at",
        archetype="brand_color_pixel",
        context=(
            "[ui] Birincil butonun marka rengi (belirli bir koordinatta) "
            "doğrulanacak; metin ya da öğe varlığı değil, renk sorusu."
        ),
        args={"x": 160, "y": 640},
        reasoning=(
            "Soru bir noktadaki renk; element_exists varlık, text_visible "
            "metin bakar. Pikseli örnekleyen ui_verify_color_at doğru araç."
        ),
        index=16,
    ),
    ToolScenario(
        tool="set_cli_effort",
        archetype="low_effort_for_chore",
        context=(
            "[meta] Sıradaki iş mekanik bir yeniden-adlandırma; claude-code "
            "gereksiz derin düşünüp yavaşlıyor. Sadece düşünme derinliği "
            "azaltılacak."
        ),
        args={"cli": "claude-code", "effort": "low"},
        reasoning=(
            "Sorun hangi CLI değil ne kadar düşündüğü; rotate_to CLI değiştirir, "
            "set_cli_models modeli. Düşünme derinliğini set_cli_effort ayarlar."
        ),
        index=17,
    ),
]

__all__ = ["SCENARIOS"]
