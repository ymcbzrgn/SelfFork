"""Authored scenarios + trajectories for LOW-CONTEXT SURVIVAL: managing a
small context window with the Mind tools (mind_note_add / mind_recall /
compact_context / session_state).

A 2B model with a small window drowns if it keeps everything in-context. This
corpus teaches the four survival judgments explicitly:

* **offload** (``mind_note_add``) -- a locked operator DECISION, a hard-won
  root cause, a dead end, or a distilled reflex must live OUTSIDE the window
  (kind=decision for operator rulings; pinned + high importance for
  load-bearing constraints; kind=pattern + tier=procedural for reflexes).
  Trap: idle chatter is NOT note-worthy; the one decision inside it IS.
* **recall** (``mind_recall``) -- "daha önce buna karar vermiş miydik?" means
  recall, never guess and never re-ask the operator; recall before re-deriving
  a known fix. Low-window discipline: small top_k / threshold so the recall
  itself does not flood the window.
* **compact** (``compact_context``) -- summary preserves meaning (decisions
  live in the OLDEST turns -> truncate is the trap), truncate is only safe
  when the head is worthless AND everything important is already in Mind,
  handoff is for crossing a session boundary (even when the operator says
  "özetle" but means a transfer).
* **orient** (``session_state``) -- unknown project slug, post-handoff, or
  stale context: read the session before acting; verify mind is wired before
  writing an important note.

Every target is gated against the real registry by the builder.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import (
    AgenticStep,
    AgenticTrajectory,
    ToolScenario,
)

_NOTE = "mind_note_add"
_RECALL = "mind_recall"
_COMPACT = "compact_context"
_STATE = "session_state"

SCENARIOS: list[ToolScenario] = [
    # ------------------------------------------------------------------
    # mind_note_add -- OFFLOAD: what deserves to outlive the window
    # ------------------------------------------------------------------
    ToolScenario(
        tool=_NOTE,
        archetype="locked_constraint_pinned",
        context=(
            "[oturum] Uzun bir yeniden düzenleme görevi başlıyor. Operatör: "
            "'Kural net: public API imzaları bu görevde ASLA değişmeyecek. "
            "Saatler sürecek, unutma.'"
        ),
        args={
            "content": (
                "Operatör kuralı: yeniden düzenleme boyunca public API "
                "imzaları değiştirilmeyecek."
            ),
            "kind": "decision",
            "intent": "görev boyu geçerli taşıyıcı kısıt",
            "importance": 9.5,
            "pinned": True,
        },
        reasoning=(
            "Görev pencereden uzun yaşayacak; bağlam dolunca bu cümle düşer. "
            "Taşıyıcı kısıt pinned karar olarak Mind'a yazılır, pencereye "
            "emanet edilmez."
        ),
        index=0,
    ),
    # --- trap: chatter is NOT note-worthy; the decision inside it IS --------
    ToolScenario(
        tool=_NOTE,
        archetype="chatter_vs_decision_trap",
        context=(
            "[oturum] Operatör beş dakikadır maç sonucu ve öğle yemeğinden "
            "bahsediyor; araya tek iş cümlesi sıkıştı: 'Bu arada karar "
            "verdim, tarih alanlarının hepsi UTC olacak.'"
        ),
        args={
            "content": "Operatör kararı: tüm tarih alanları UTC tutulacak.",
            "kind": "decision",
            "importance": 8,
            "pinned": True,
        },
        reasoning=(
            "Sohbetin not değeri yok; maç ve yemek geleceğe taşınmaz. "
            "Kalıcı olan tek şey UTC kararı — yalnız onu yazıyorum."
        ),
        index=1,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="hard_won_root_cause",
        context=(
            "[oturum] İki saatlik hata ayıklama sonunda kök neden bulundu: "
            "bildirim gecikmesi, cihaz saat dilimi UTC+3 dışındayken cron "
            "ifadesinin yanlış üretilmesinden kaynaklanıyor."
        ),
        args={
            "content": (
                "Kök neden: bildirim gecikmesi, UTC+3 dışındaki cihazlarda "
                "cron ifadesinin yanlış üretilmesinden. İki saatlik analizle "
                "doğrulandı."
            ),
            "kind": "observation",
            "importance": 8,
            "tag_pairs": [["konu", "bildirim"], ["tur", "kok-neden"]],
        },
        reasoning=(
            "İki saatlik kazanım pencereyle birlikte buharlaşırsa bedeli "
            "yeniden ödenir. Zor kazanılmış gerçek Mind'a yazılır."
        ),
        index=2,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="dead_end_marker",
        context=(
            "[oturum] WebSocket kopmalarını çözmek için ping aralığını 5 "
            "sn'ye düşürme yolu denendi; sorun geçmedi, üstelik pil "
            "tüketimi arttı. Bu yol çıkmaz."
        ),
        args={
            "content": (
                "Çıkmaz yol: WebSocket kopmaları için ping aralığını 5 "
                "sn'ye düşürmek işe yaramadı, pil tüketimini artırdı. "
                "Tekrar denenmesin."
            ),
            "kind": "observation",
            "importance": 7,
        },
        reasoning=(
            "Başarısız deneme de bilgidir; not düşülmezse gelecekteki "
            "oturum aynı çıkmaza aynı saatleri harcar."
        ),
        index=3,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="distilled_retry_pattern",
        context=(
            "[oturum] Harita servisi bugün üçüncü kez 429 döndürdü; her "
            "seferinde 30 sn bekleyip tek tekrarla düzeldi. Bu artık "
            "tesadüf değil, davranış."
        ),
        args={
            "content": (
                "Refleks: harita servisi 429 döndürürse 30 sn bekle ve tek "
                "kez tekrar dene; üç kez doğrulandı."
            ),
            "tier": "procedural",
            "kind": "pattern",
            "importance": 7,
        },
        reasoning=(
            "Üç kez tekrarlayan çözüm anı olmaktan çıktı; kind=pattern ile "
            "prosedürel refleks olarak damıtıyorum ki her seferinde "
            "yeniden keşfedilmesin."
        ),
        index=4,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="config_fact_tags",
        context=(
            "[oturum] Operatör staging ortamının adresini ilk kez verdi: "
            "'staging API https://stg.acme.io:8443, anahtar rotasyonu her "
            "pazartesi.' Bu bilgi başka hiçbir yerde yazmıyor."
        ),
        args={
            "content": (
                "Staging API adresi https://stg.acme.io:8443; anahtar "
                "rotasyonu her pazartesi."
            ),
            "kind": "observation",
            "importance": 7,
            "tag_pairs": [["ortam", "staging"], ["konu", "endpoint"]],
        },
        reasoning=(
            "Tek kaynağı operatörün bu cümlesi; pencere dolunca kaybolursa "
            "yeniden sormak gerekir. Etiketlerle aranabilir kalıcı nota "
            "çeviriyorum."
        ),
        index=5,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="decision_rationale_intent",
        context=(
            "[oturum] Uzun tartışma sonrası cihaz içi depolama için SQLite "
            "seçildi; Realm, lisans belirsizliği yüzünden elendi. Operatör "
            "onayladı."
        ),
        args={
            "content": (
                "Depolama kararı: SQLite seçildi; Realm lisans belirsizliği "
                "nedeniyle elendi. Operatör onaylı."
            ),
            "kind": "decision",
            "intent": "ileride 'neden SQLite' sorusunun cevabı",
            "importance": 8,
        },
        reasoning=(
            "Karar kadar gerekçesi de kıymetli; gerekçe kaybolursa "
            "tartışma ileride sıfırdan yaşanır. intent alanı notun ne için "
            "geri çağrılacağını söylüyor."
        ),
        index=6,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="offload_before_window_loss",
        context=(
            "[oturum] Pencere %82 doldu ve ilk turlardaki kabul kriterleri "
            "('üç cihazda test, çevrimdışı mod şart') henüz hiçbir yere "
            "yazılmadı; bir sonraki büyük çıktıda düşecekler."
        ),
        args={
            "content": (
                "Kabul kriterleri: üç cihazda test edilecek; çevrimdışı mod "
                "şart. Operatörün açılış mesajından."
            ),
            "kind": "observation",
            "intent": "pencereden düşmeden güvenceye al",
            "importance": 8,
        },
        reasoning=(
            "Kriterler yalnız pencerede yaşıyor ve pencere taşmak üzere; "
            "önce Mind'a yaz, sonra sıkıştır. Sıra tersine dönerse bilgi "
            "geri gelmez."
        ),
        index=7,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="decision_reversal_note",
        context=(
            "[oturum] Operatör önceki kararı bozdu: 'Push bildirim "
            "sağlayıcısını değiştiriyoruz; OneSignal iptal, Firebase'e "
            "geçiyoruz. Bugünden itibaren geçerli.'"
        ),
        args={
            "content": (
                "Karar güncellendi: push bildirim sağlayıcısı artık "
                "Firebase; OneSignal kararı iptal (operatör, bugün)."
            ),
            "kind": "decision",
            "importance": 9,
            "pinned": True,
        },
        reasoning=(
            "Eski karar Mind'da duruyor; yenisi yazılmazsa gelecekteki "
            "recall eski hükmü getirir. Güncel hükmü ayrı ve baskın bir "
            "kararla kaydediyorum."
        ),
        index=8,
    ),
    ToolScenario(
        tool=_NOTE,
        archetype="conclusion_not_dump",
        context=(
            "[oturum] Kırk dosyalık tarama bitti; tek önemli bulgu şu: "
            "yetki kontrolü yalnız middleware/auth.py içinde yapılıyor, "
            "başka hiçbir katmanda yok. Ham tarama çıktısı pencereyi "
            "dolduruyor."
        ),
        args={
            "content": (
                "Bulgu: yetki kontrolü yalnız middleware/auth.py'de; başka "
                "katmanda yok (40 dosyalık tarama sonucu)."
            ),
            "kind": "observation",
            "importance": 7,
        },
        reasoning=(
            "Küçük pencereye 40 dosyalık döküm değil tek cümlelik sonuç "
            "saklanır. Sonuç Mind'a yazılınca ham dökümün pencereden "
            "düşmesi zararsızlaşır."
        ),
        index=9,
    ),
    # ------------------------------------------------------------------
    # mind_recall -- RECALL instead of guessing / re-asking / re-deriving
    # ------------------------------------------------------------------
    # --- trap: "karar vermiş miydik?" -> recall, don't re-ask ---------------
    ToolScenario(
        tool=_RECALL,
        archetype="reask_trap",
        context=(
            "[oturum] Kimlik doğrulama ekranını yazarken soru doğdu: "
            "'Oturum süresi 30 dk mıydı, 7 gün müydü? Buna daha önce karar "
            "vermiş miydik?' Operatör şu an çevrimdışı."
        ),
        args={"query": "oturum süresi kararı token geçerlilik", "top_k": 3},
        reasoning=(
            "'Karar vermiş miydik?' sorusunun cevabı tahmin ya da yeni "
            "soru değil; kararlar Mind'da. Önce recall — operatörü yeniden "
            "meşgul etmek son çare."
        ),
        index=10,
    ),
    ToolScenario(
        tool=_RECALL,
        archetype="rederive_avoidance",
        context=(
            "[oturum] CI imzalama hatası için keystore yapılandırmasını "
            "sıfırdan çözmeye başlamak üzereyim; oysa aynı hata geçen ay "
            "çözülmüştü, adımları hatırlamıyorum."
        ),
        args={"query": "keystore imzalama hatası çözüm adımları", "top_k": 3},
        reasoning=(
            "Çözüm bir kez bulundu ve bedeli ödendi; yeniden türetmek hem "
            "saatleri hem pencereyi yakar. Önce geçmiş çözümü çağırıyorum."
        ),
        index=11,
    ),
    ToolScenario(
        tool=_RECALL,
        archetype="familiar_error_lookup",
        context=(
            "[oturum] Konsolda 'ECONNRESET after 60s idle' hatası belirdi. "
            "Bu metin tanıdık; sanki önceki bir oturumda aynı hatayla "
            "uğraşılmıştı."
        ),
        args={
            "query": "ECONNRESET 60 saniye idle bağlantı kopması çözümü",
            "top_k": 5,
        },
        reasoning=(
            "Tanıdıklık hissi bir işaret: hata muhtemelen kayıtlı. "
            "Sıfırdan hata ayıklamadan önce Mind'daki geçmiş düzeltmeye "
            "bakıyorum."
        ),
        index=12,
    ),
    ToolScenario(
        tool=_RECALL,
        archetype="post_truncate_recovery",
        context=(
            "[oturum] Önceki sıkıştırmada en eski turlar atılmıştı; şimdi "
            "teslim öncesi kontrol için operatörün başta saydığı kabul "
            "kriterleri gerekiyor ama pencerede yoklar."
        ),
        args={"query": "kabul kriterleri operatör açılış şartları", "top_k": 3},
        reasoning=(
            "Kriterleri pencereden okuyamam, tahmin etmek teslimi riske "
            "atar. Pencereden düşen bilgi Mind'dan geri gelir — recall tam "
            "bunun için."
        ),
        index=13,
    ),
    ToolScenario(
        tool=_RECALL,
        archetype="rationale_retrieval",
        context=(
            "[oturum] Operatör: 'Hatırlat bakayım, ses sentezinde neden "
            "Kokoro'da karar kılmıştık?' Bu oturumda o tartışma hiç "
            "geçmedi."
        ),
        args={"query": "Kokoro ses sentezi seçim gerekçesi karar", "top_k": 3},
        reasoning=(
            "Gerekçeyi uydurmak güveni bozar; karar notu gerekçesiyle "
            "birlikte Mind'da. Cevap üretmeden önce kaydı çağırıyorum."
        ),
        index=14,
    ),
    ToolScenario(
        tool=_RECALL,
        archetype="procedural_tier_recall",
        context=(
            "[oturum] Derleme yine bilinen belirtilerle yavaşladı. Bu "
            "durum için daha önce damıtılmış bir refleks (adım adım "
            "prosedür) kaydedilmişti; anılar değil prosedür lazım."
        ),
        args={
            "query": "derleme yavaşlama refleks prosedür",
            "top_k": 3,
            "tier": "procedural",
        },
        reasoning=(
            "Aranan şey anı değil damıtılmış prosedür; tier=procedural "
            "aramayı doğru rafa daraltır, alakasız anıların pencereyi "
            "doldurmasını önler."
        ),
        index=15,
    ),
    # --- low-window discipline: the recall itself must stay lean ------------
    ToolScenario(
        tool=_RECALL,
        archetype="lean_topk_low_window",
        context=(
            "[oturum] Pencere %88 dolu; tek bir şey lazım: veritabanı "
            "migrasyon kuralının tam metni. Geniş bir arama sonucu "
            "pencereyi taşırabilir."
        ),
        args={"query": "migrasyon yazma kuralı read-replica", "top_k": 1},
        reasoning=(
            "Pencere doluyken recall bile bütçeyle yapılır: tek kayıt "
            "yeter. top_k=1 doğru cevabı getirirken pencereye en küçük "
            "yükü bindirir."
        ),
        index=16,
    ),
    ToolScenario(
        tool=_RECALL,
        archetype="threshold_precision",
        context=(
            "[oturum] 'bildirim' kelimesi geçen onlarca not birikti; şu an "
            "yalnız güçlü eşleşen kök-neden kaydı gerekiyor, gevşek "
            "eşleşmeler pencereyi çöple doldurur."
        ),
        args={
            "query": "bildirim gecikmesi kök neden cron saat dilimi",
            "top_k": 3,
            "threshold": 0.6,
        },
        reasoning=(
            "Kalabalık hafızada gevşek eşleşme gürültüdür; threshold ile "
            "yalnız güçlü skorlar pencereye girer. Küçük pencerede süzgeç "
            "şarttır."
        ),
        index=17,
    ),
    # ------------------------------------------------------------------
    # compact_context -- pick the RIGHT strategy for a filling window
    # ------------------------------------------------------------------
    ToolScenario(
        tool=_COMPACT,
        archetype="summary_keeps_decisions",
        context=(
            "[oturum] Dört saatlik oturumda üç operatör kararı alındı ve "
            "pencere %85'e dayandı. Görev sürüyor; kararların anlamı bir "
            "sonraki adımlar için şart."
        ),
        args={
            "strategy": "summary",
            "reason": "pencere %85; kararların anlamı korunarak küçültülecek",
        },
        reasoning=(
            "truncate en eski turları atar — kararlar tam orada. Anlamı "
            "koruyup hacmi düşüren tek strateji summary."
        ),
        index=18,
    ),
    # --- trap: truncate is cheap but drops the OLDEST turns -----------------
    ToolScenario(
        tool=_COMPACT,
        archetype="truncate_head_trap",
        context=(
            "[oturum] Pencere dolmak üzere; en ucuz yol en eski turları "
            "atmak gibi görünüyor. Ama görevin kilit kısıtı ('imzalar "
            "değişmeyecek') tam o en eski turlarda duruyor ve Mind'a "
            "yazılmadı."
        ),
        args={
            "strategy": "summary",
            "reason": "kilit kısıt en eski turlarda; truncate onu düşürür",
        },
        reasoning=(
            "truncate ucuz ama kör: en eskiyi atar, kısıt da en eskide. "
            "Kısıt henüz Mind'da olmadığından tek güvenli sıkıştırma "
            "summary."
        ),
        index=19,
    ),
    # --- the one case where truncate IS the right call -----------------------
    ToolScenario(
        tool=_COMPACT,
        archetype="safe_truncate_stale_logs",
        context=(
            "[oturum] Pencerenin en eski kısmı selamlaşma ve artık bayat, "
            "üç kez yinelenmiş ham log dökümlerinden ibaret. O günden beri "
            "her karar ve bulgu Mind'a not edildi."
        ),
        args={
            "strategy": "truncate",
            "reason": "en eski turlar bayat log dökümü; kararlar zaten Mind'da",
        },
        reasoning=(
            "truncate ancak en eski turların değeri sıfırsa güvenlidir; "
            "burada öyle — kararlar Mind'da, loglar bayat. En ucuz "
            "strateji bilinçli seçilebilir."
        ),
        index=20,
    ),
    ToolScenario(
        tool=_COMPACT,
        archetype="handoff_session_transfer",
        context=(
            "[oturum] Görev bu oturumda bitmeyecek; operatör işin yarın "
            "başka bir CLI oturumunda kaldığı yerden sürmesini istiyor. "
            "Yerinde küçültme bunu sağlamaz."
        ),
        args={
            "strategy": "handoff",
            "reason": "görev yarın taze oturumda sürecek; devir paketi gerekli",
        },
        reasoning=(
            "summary aynı pencereyi küçültür, oturum sınırını aşamaz. "
            "Başka oturuma taşınan iş için devir paketini handoff üretir."
        ),
        index=21,
    ),
    ToolScenario(
        tool=_COMPACT,
        archetype="preemptive_compact",
        context=(
            "[oturum] Sıradaki adım 500 satırlık test çıktısı dökecek ve "
            "pencere şimdiden %75. Çıktı geldikten sonra sıkıştırmak için "
            "geç olabilir; taşma ortasında kesilir."
        ),
        args={
            "strategy": "summary",
            "reason": "500 satırlık çıktı öncesi yer açılıyor; pencere %75",
        },
        reasoning=(
            "Sıkıştırma taşmadan ÖNCE yapılırsa ucuzdur; taşma anında hem "
            "çıktı hem bağlam zarar görür. Büyük adımdan önce proaktif "
            "summary."
        ),
        index=22,
    ),
    # --- trap: operator says 'özetle' but the intent is a session transfer --
    ToolScenario(
        tool=_COMPACT,
        archetype="summary_word_handoff_trap",
        context=(
            "[oturum] Operatör: 'Bunu güzelce özetle de işi yarın yeni "
            "pencerede kaldığı yerden alalım.' İstenen şey mevcut pencereyi "
            "küçültmek değil, işi yeni oturuma taşımak."
        ),
        args={
            "strategy": "handoff",
            "reason": "operatör işin yeni oturumda sürmesini istiyor; devir",
        },
        reasoning=(
            "'Özetle' kelimesine kanma: niyet oturum devri. summary "
            "yerinde küçültür ve yeni pencereye hiçbir şey taşımaz; devri "
            "handoff yapar."
        ),
        index=23,
    ),
    ToolScenario(
        tool=_COMPACT,
        archetype="overflow_imminent_summary",
        context=(
            "[oturum] Uyarı geldi: pencere %93. İş kritik aşamada, "
            "atılacak adımların gerekçeleri son turlarda; hiçbir anlam "
            "kaybına tahammül yok ama hacim düşmek zorunda."
        ),
        args={
            "strategy": "summary",
            "reason": "pencere %93; anlam kaybı olmadan acil hacim düşürme",
        },
        reasoning=(
            "Eşik aşılmadan davranmak gerek; truncate anlam kaybettirir, "
            "handoff görevi böler. Anlamı koruyarak hacmi düşüren acil "
            "hamle summary."
        ),
        index=24,
    ),
    # ------------------------------------------------------------------
    # session_state -- ORIENT before acting
    # ------------------------------------------------------------------
    ToolScenario(
        tool=_STATE,
        archetype="fresh_session_blind_start",
        context=(
            "[oturum] Yeni oturum, boş geçmiş. Operatör tek cümle yazdı: "
            "'Devam et.' Hangi proje, hangi CLI, mind bağlı mı — hiçbiri "
            "bilinmiyor."
        ),
        args={},
        reasoning=(
            "Neye devam edeceğini bilmeden atılan her adım kör. Önce "
            "session_state: proje slug'ı, aktif CLI ve mind bağlantısı "
            "okunmadan iş başlamaz."
        ),
        index=25,
    ),
    ToolScenario(
        tool=_STATE,
        archetype="post_handoff_ground_check",
        context=(
            "[oturum] Bu oturum bir devir (handoff) paketiyle açıldı. "
            "Devrin hangi oturum kimliğine, hangi projeye bağlandığını "
            "doğrulamadan kaldığı yerden devam etmek riskli."
        ),
        args={},
        reasoning=(
            "Devir sonrası ilk iş zemini doğrulamak: session_state oturum "
            "kimliğini ve bağlı alt sistemleri gösterir. Yanlış projede "
            "'devam etmek' zarar verir."
        ),
        index=26,
    ),
    ToolScenario(
        tool=_STATE,
        archetype="mind_wired_check",
        context=(
            "[oturum] Az önce alınan kritik operatör kararını not "
            "edeceğim; ama bu ortamda mind alt sisteminin bağlı olup "
            "olmadığından emin değilim. Bağlı değilse not sessizce boşa "
            "gider."
        ),
        args={},
        reasoning=(
            "Bağlı olmayan mind'a yazılan not kaybolur ve kayıp sessizdir. "
            "session_state alt sistem kablolamasını gösterir; kritik yazma "
            "ondan sonra."
        ),
        index=27,
    ),
    ToolScenario(
        tool=_STATE,
        archetype="active_cli_question",
        context=(
            "[oturum] Operatör: 'Şu an hangi CLI üstünde koşuyoruz, claude "
            "mı codex mi?' Ezbere cevap vermek yanıltıcı olabilir; oturum "
            "bilgisi orkestratörde."
        ),
        args={},
        reasoning=(
            "Aktif CLI oturumun gerçeğidir, tahminin değil. session_state "
            "bu bilgiyi kaynağından okur; ezber cevap yanlışsa operatör "
            "yanlış yönlenir."
        ),
        index=28,
    ),
    ToolScenario(
        tool=_STATE,
        archetype="stale_context_suspicion",
        context=(
            "[oturum] Uzun bir duraklamadan sonra görev kaldığı yerden "
            "sürecek; ama aradan geçen sürede oturumun sıfırlanıp "
            "sıfırlanmadığı, hangi oturumda olunduğu belirsiz."
        ),
        args={},
        reasoning=(
            "Bayat bağlam varsayımla sürdürülmez; oturum değiştiyse "
            "penceredeki 'hatıralar' geçersizdir. session_state hangi "
            "zeminde durulduğunu netleştirir."
        ),
        index=29,
    ),
]


TRAJECTORIES: list[AgenticTrajectory] = [
    # ------------------------------------------------------------------
    # Long task: pin the constraint -> compact with summary -> recall it
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="uzun_gorev_kilitli_kural",
        goal=(
            "[görev] Sipariş veritabanı migrasyonu yapılacak; saatler "
            "sürecek ve bağlam penceresi görev bitmeden dolacak. Operatörün "
            "açılışta koyduğu kural: 'Yazma işlemleri yalnız read-replica "
            "doğrulaması SONRASI; bu kural görev boyunca geçerli.'"
        ),
        steps=[
            AgenticStep(
                tool=_NOTE,
                args={
                    "content": (
                        "Migrasyon kuralı: yazma işlemleri yalnız "
                        "read-replica doğrulaması sonrası yapılacak; "
                        "operatör kararı, görev boyunca geçerli."
                    ),
                    "kind": "decision",
                    "intent": "pencere dolsa da kuralı canlı tut",
                    "importance": 9.5,
                    "pinned": True,
                },
                result=(
                    "[sonuç] Not kaydedildi (id=n-482, pinned). İlerleme: 3 "
                    "tablo taşındı; pencere %86 doldu, en eski turlar "
                    "düşmek üzere."
                ),
                reasoning=(
                    "Kural görevden kısa ömürlü pencereye sığmaz; kaybolmasın "
                    "diye işe başlamadan pinned karar olarak Mind'a yazıyorum."
                ),
            ),
            AgenticStep(
                tool=_COMPACT,
                args={
                    "strategy": "summary",
                    "reason": (
                        "pencere %86; migrasyon kararlarının anlamı "
                        "korunarak küçültülecek"
                    ),
                },
                result=(
                    "[sonuç] Özet üretildi; pencere %31'e indi. Erken "
                    "turların ham metni (kural cümlesi dahil) artık "
                    "pencerede değil."
                ),
                reasoning=(
                    "Pencere taşmadan sıkıştırıyorum; truncate en eski "
                    "turları (kuralın geçtiği yeri) körce atar, summary "
                    "anlamı korur."
                ),
            ),
            AgenticStep(
                tool=_RECALL,
                args={
                    "query": (
                        "migrasyon yazma kuralı read-replica operatör kararı"
                    ),
                    "top_k": 3,
                },
                result=(
                    "[sonuç] 1 kayıt (skor 0.91, pinned, importance 9.5): "
                    "'Migrasyon kuralı: yazma işlemleri yalnız read-replica "
                    "doğrulaması sonrası yapılacak...'"
                ),
                reasoning=(
                    "Sıradaki adım yazma içeriyor ve kuralın tam metni "
                    "pencereden çıktı; ezberden değil Mind'dan doğruluyorum."
                ),
            ),
            AgenticStep(
                tool=_NOTE,
                args={
                    "content": (
                        "Migrasyon ara durum: orders, order_items, payments "
                        "taşındı; sırada refunds. Kural ihlali yok."
                    ),
                    "kind": "observation",
                    "importance": 6,
                },
                result=(
                    "[sonuç] Not kaydedildi. Refunds taşıması kurala uygun "
                    "şekilde tamamlandı; görev bitti."
                ),
                reasoning=(
                    "Ara durumu da pencere dışına yazıyorum; bir sonraki "
                    "sıkıştırma ya da oturum kesintisi ilerlemeyi silememeli."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # Past decision: recall it instead of re-asking, then act on it
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="gecmis_karar_webhook",
        goal=(
            "[görev] Operatör: 'Webhook uçlarını yazmaya başla — hangi "
            "ödeme sağlayıcısına karar vermiştik, ona göre.' Bu oturumda "
            "ödeme sağlayıcısı hiç konuşulmadı."
        ),
        steps=[
            AgenticStep(
                tool=_RECALL,
                args={"query": "ödeme sağlayıcısı seçimi karar", "top_k": 3},
                result=(
                    "[sonuç] 1 kayıt (skor 0.88, kind=decision): 'Ödeme "
                    "sağlayıcısı iyzico seçildi; Stripe TR desteği "
                    "eksikliği yüzünden elendi. 12 Haziran, operatör "
                    "onaylı.'"
                ),
                reasoning=(
                    "Karar bu pencerede yok; operatöre yeniden sormak ya da "
                    "tahmin etmek yerine kayıtlı kararı çağırıyorum."
                ),
            ),
            AgenticStep(
                tool=_NOTE,
                args={
                    "content": (
                        "Webhook uçları iyzico sözleşmesine göre yazılıyor "
                        "(12 Haziran iyzico kararına dayanarak)."
                    ),
                    "kind": "observation",
                    "intent": "kararın uygulandığının izi",
                    "importance": 5,
                },
                result=(
                    "[sonuç] Not kaydedildi; iyzico imza doğrulaması ve "
                    "callback ucu iskeleti oluşturuldu."
                ),
                reasoning=(
                    "Kararı uyguladığımı iz olarak düşüyorum; ileride "
                    "'webhooklar neden iyzico formatında' sorusunun cevabı "
                    "hazır olur."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # Fresh session: orient with session_state, recall project context
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="taze_oturum_oryantasyon",
        goal=(
            "[görev] Yepyeni bir oturum açıldı; önceki konuşma yok. "
            "Operatör tek satır yazdı: 'Kaldığımız yerden devam.' Hangi "
            "proje, ne durumda — bilinmiyor."
        ),
        steps=[
            AgenticStep(
                tool=_STATE,
                args={},
                result=(
                    "[sonuç] session_id=s-77, project_slug=selffork, aktif "
                    "CLI=claude, mind=wired, proactive_quota=ok."
                ),
                reasoning=(
                    "Neye devam edeceğimi bilmiyorum; körce iş yapmadan "
                    "önce oturumun kimliğini ve mind'ın bağlı olduğunu "
                    "okuyorum."
                ),
            ),
            AgenticStep(
                tool=_RECALL,
                args={
                    "query": "selffork son durum bekleyen iş kararlar",
                    "top_k": 5,
                },
                result=(
                    "[sonuç] 3 kayıt: (1) pinned karar: 'UI asla web'e "
                    "yayınlanmaz; yerel sunucudan servis edilir.' (2) "
                    "'S-ToolFleet bitti; sırada S-Train.' (3) 'Testler "
                    "yalnız hedefli pytest ile koşulur.'"
                ),
                reasoning=(
                    "Mind bağlı; 'kaldığımız yer' pencerede değil Mind'da. "
                    "Proje bağlamını çağırıp plana oradan başlıyorum."
                ),
            ),
            AgenticStep(
                tool=_NOTE,
                args={
                    "content": (
                        "Yeni oturum s-77: S-Train'e başlanıyor; pinned "
                        "kısıtlar (UI web'e yayınlanmaz, hedefli pytest) "
                        "geçerli."
                    ),
                    "kind": "observation",
                    "importance": 5,
                },
                result=(
                    "[sonuç] Not kaydedildi; S-Train ilk adımı planlandı."
                ),
                reasoning=(
                    "Devralma noktasını işaretliyorum: bir sonraki taze "
                    "oturum da aynı iki adımla buradan toparlanabilir."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # Window exhausted mid-task: persist state, then hand off
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="tasma_oncesi_devir",
        goal=(
            "[görev] Kod tabanı denetimi 6 saattir sürüyor; pencere iki "
            "kez özetlenmesine rağmen %90'da ve kalan iş en az bu kadar "
            "daha çıktı üretecek. Görev yarım bırakılamaz."
        ),
        steps=[
            AgenticStep(
                tool=_NOTE,
                args={
                    "content": (
                        "Denetim ara durumu: 34/60 modül bitti; kritik "
                        "bulgu: auth.py'de token süresi kontrol edilmiyor "
                        "(S1). Kalan: payments/, api/. Yöntem: modül "
                        "başına checklist v2."
                    ),
                    "kind": "observation",
                    "intent": "devir sonrası kaldığı yerden devam",
                    "importance": 8,
                },
                result="[sonuç] Not kaydedildi (id=n-903). Pencere %91.",
                reasoning=(
                    "Devirden önce durum pencerede değil Mind'da olmalı; "
                    "taze oturum bu nottan toparlanacak."
                ),
            ),
            AgenticStep(
                tool=_COMPACT,
                args={
                    "strategy": "handoff",
                    "reason": (
                        "pencere %91 ve kalan iş pencereye sığmıyor; taze "
                        "oturuma devir paketi"
                    ),
                },
                result=(
                    "[sonuç] Devir paketi üretildi; yeni oturum kaldığı "
                    "yerden başlatılabilir."
                ),
                reasoning=(
                    "Bir özet daha kazandırmaz; kalan iş bu pencereye "
                    "sığmıyor. summary yerinde küçültür, handoff işi taze "
                    "pencereye taşır."
                ),
            ),
        ],
    ),
    # ------------------------------------------------------------------
    # Recurring fix: recall it, then promote it to a procedural pattern
    # ------------------------------------------------------------------
    AgenticTrajectory(
        name="tekrar_eden_hata_refleks",
        goal=(
            "[görev] Android derlemesi 'Java heap space' hatasıyla düştü. "
            "Bu hata tanıdık geliyor; sıfırdan hata ayıklamak en az bir "
            "saat sürer."
        ),
        steps=[
            AgenticStep(
                tool=_RECALL,
                args={
                    "query": "gradle java heap space derleme hatası çözüm",
                    "top_k": 3,
                },
                result=(
                    "[sonuç] 1 kayıt (skor 0.93): '14 Haziran: "
                    "gradle.properties dosyasına "
                    "org.gradle.jvmargs=-Xmx4g eklendi, heap hatası "
                    "çözüldü.'"
                ),
                reasoning=(
                    "Tanıdık hatayı sıfırdan çözmek pencere ve zaman yakar; "
                    "önce geçmişteki çözümü arıyorum."
                ),
            ),
            AgenticStep(
                tool=_NOTE,
                args={
                    "content": (
                        "Refleks: gradle 'Java heap space' görürsen "
                        "gradle.properties içinde "
                        "org.gradle.jvmargs=-Xmx4g olduğunu doğrula; iki "
                        "kez işe yaradı."
                    ),
                    "tier": "procedural",
                    "kind": "pattern",
                    "importance": 7,
                },
                result=(
                    "[sonuç] Not kaydedildi. Ayar uygulandı, derleme geçti."
                ),
                reasoning=(
                    "Aynı çözüm ikinci kez lazım oldu; tek seferlik anı "
                    "olmaktan çıkıp prosedürel refleks olarak damıtılmayı "
                    "hak etti."
                ),
            ),
        ],
    ),
]

__all__ = ["SCENARIOS", "TRAJECTORIES"]
