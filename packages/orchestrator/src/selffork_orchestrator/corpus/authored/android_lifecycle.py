"""Authored scenarios for the Android app-lifecycle tools (launch / activate /
terminate / force_stop).

These four tools are semantically close and a small model confuses them, so
every scenario here is reasoning-based: the target teaches the disambiguation
explicitly. The two hard pairs are covered head-on:

* ``launch`` vs ``activate`` -- cold start (process not running) vs bringing
  an already-running, backgrounded app to the foreground. Includes the trap
  where the operator says "bring it up" but the app is NOT running (-> launch).
* ``terminate`` vs ``force_stop`` -- graceful close of a RESPONSIVE app vs
  killing a FROZEN / unresponsive (ANR) one. Includes the trap where the app
  is slow-but-responsive (-> terminate, not force_stop).

Every scenario is gated against the real registry by the builder.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

_LAUNCH = "android_app_launch"
_ACTIVATE = "android_app_activate"
_TERMINATE = "android_app_terminate"
_FORCE_STOP = "android_app_force_stop"

SCENARIOS: list[ToolScenario] = [
    # ------------------------------------------------------------------
    # launch -- app is NOT running: cold start
    # ------------------------------------------------------------------
    ToolScenario(
        tool=_LAUNCH,
        archetype="cold_start",
        context=(
            "[cihaz] Ekran ana sayfada, çalışan uygulama listesi boş. "
            "Operatör: 'Chrome'u aç, bir adres arayacağız.'"
        ),
        args={"package": "com.android.chrome"},
        reasoning=(
            "Chrome şu an hiç çalışmıyor; öne getirilecek bir oturum yok. "
            "Soğuk başlatma gerektiği için launch kullanıyorum."
        ),
        index=0,
    ),
    ToolScenario(
        tool=_LAUNCH,
        archetype="post_reboot_launch",
        context=(
            "[cihaz] Telefon az önce yeniden başlatıldı; hiçbir uygulama "
            "açılmadı. Operatör WhatsApp mesajlarını kontrol etmemi istedi."
        ),
        args={"package": "com.whatsapp"},
        reasoning=(
            "Yeniden başlatma sonrası WhatsApp süreci yok; arka planda "
            "devam eden oturum olmadığından launch ile sıfırdan açıyorum."
        ),
        index=1,
    ),
    # --- hard pair: operator says 'öne getir' but app is NOT running --------
    ToolScenario(
        tool=_LAUNCH,
        archetype="foreground_but_not_running",
        context=(
            "[cihaz] Son uygulamalar ekranı kontrol edildi: Instagram "
            "listede yok, süreç çalışmıyor. Operatör: 'Instagram'ı öne getir.'"
        ),
        args={"package": "com.instagram.android"},
        reasoning=(
            "Operatör 'öne getir' dese de uygulama çalışmıyor; activate "
            "çalışan süreç ister. Ortada oturum yokken doğru araç launch."
        ),
        index=2,
    ),
    # ------------------------------------------------------------------
    # activate -- app IS running in background: bring to foreground
    # ------------------------------------------------------------------
    ToolScenario(
        tool=_ACTIVATE,
        archetype="background_resume",
        context=(
            "[cihaz] Spotify arka planda müzik çalmaya devam ediyor. "
            "Operatör: 'Spotify'ı ekrana getir, çalma listesini değiştireceğim.'"
        ),
        args={"package": "com.spotify.music"},
        reasoning=(
            "Uygulama zaten arka planda çalışıyor; yeniden başlatmak değil, "
            "mevcut oturumu öne almak gerekiyor. Bu yüzden activate."
        ),
        index=3,
    ),
    # --- hard pair: preserve in-app state -> activate, NOT launch -----------
    ToolScenario(
        tool=_ACTIVATE,
        archetype="resume_preserve_state",
        context=(
            "[cihaz] Gmail son uygulamalarda duruyor; yarım kalmış bir "
            "taslak e-posta açık. Operatör: 'Gmail'e geri dön, taslağı bitir.'"
        ),
        args={"package": "com.google.android.gm"},
        reasoning=(
            "Gmail arka planda ve taslak ekranı korunmalı; activate mevcut "
            "durumu bozmadan öne getirir, launch burada gereksiz riske girer."
        ),
        index=4,
    ),
    ToolScenario(
        tool=_ACTIVATE,
        archetype="task_switch_back",
        context=(
            "[cihaz] Az önce Chrome'dan bir adres kopyalandı; WhatsApp hâlâ "
            "arka planda, sohbet ekranında bekliyor. Operatör: 'WhatsApp'a "
            "dön, adresi yapıştır.'"
        ),
        args={"package": "com.whatsapp"},
        reasoning=(
            "WhatsApp açık ve sohbet bağlamı duruyor; sadece uygulamalar "
            "arası geçiş yapılacak, bu da activate'in tam işi."
        ),
        index=5,
    ),
    # ------------------------------------------------------------------
    # terminate -- responsive app, clean/normal close
    # ------------------------------------------------------------------
    ToolScenario(
        tool=_TERMINATE,
        archetype="clean_close",
        context=(
            "[cihaz] Spotify'da müzik durduruldu, dinleme bitti. Operatör: "
            "'Spotify'ı kapat, boşuna pil harcamasın.'"
        ),
        args={"package": "com.spotify.music"},
        reasoning=(
            "Uygulama sorunsuz ve yanıt veriyor; normal bir kapatma isteği "
            "bu. Nazik kapanış için terminate yeterli, force_stop aşırı olur."
        ),
        index=6,
    ),
    ToolScenario(
        tool=_TERMINATE,
        archetype="test_teardown",
        context=(
            "[cihaz] Test senaryosu tamamlandı; Chrome açık ve tepki "
            "veriyor. Sıradaki teste geçmeden uygulamanın kapatılması gerek."
        ),
        args={"package": "com.android.chrome"},
        reasoning=(
            "Chrome yanıt verdiği için temiz kapanış mümkün; terminate "
            "durumu düzgün kaydederek kapatır, zorla durdurmaya gerek yok."
        ),
        index=7,
    ),
    # --- hard pair: slow but responsive -> terminate, NOT force_stop --------
    ToolScenario(
        tool=_TERMINATE,
        archetype="slow_but_responsive",
        context=(
            "[cihaz] Gmail biraz yavaşladı ama dokunmalara hâlâ tepki "
            "veriyor. Operatör: 'Gmail'i kapat da temiz baştan açalım.'"
        ),
        args={"package": "com.google.android.gm"},
        reasoning=(
            "Yavaşlık var ama uygulama donmadı, yanıt veriyor; force_stop "
            "donmuş süreçler için. Normal kapanış terminate ile yapılır."
        ),
        index=8,
    ),
    # ------------------------------------------------------------------
    # force_stop -- frozen / unresponsive (ANR) app
    # ------------------------------------------------------------------
    ToolScenario(
        tool=_FORCE_STOP,
        archetype="anr_dialog",
        context=(
            "[cihaz] Instagram 'uygulama yanıt vermiyor' (ANR) penceresi "
            "gösterdi; ekran donmuş, dokunmalara tepki yok."
        ),
        args={"package": "com.instagram.android"},
        reasoning=(
            "Uygulama ANR durumunda; nazik kapatma isteğine yanıt veremez. "
            "Donmuş süreci ancak force_stop (am force-stop) kapatır."
        ),
        index=9,
    ),
    ToolScenario(
        tool=_FORCE_STOP,
        archetype="frozen_black_screen",
        context=(
            "[cihaz] WhatsApp 30 saniyedir siyah ekranda takılı; geri tuşu "
            "ve dokunmalar işlemiyor, uygulama tamamen kilitlenmiş."
        ),
        args={"package": "com.whatsapp"},
        reasoning=(
            "Uygulama girdilere hiç yanıt vermiyor; terminate cevap veren "
            "süreç gerektirir. Kilitli süreci sadece force_stop sonlandırır."
        ),
        index=10,
    ),
    ToolScenario(
        tool=_FORCE_STOP,
        archetype="background_stuck",
        context=(
            "[cihaz] Spotify arka planda takıldı: bildirimdeki durdurma "
            "düğmesi çalışmıyor, ses akışı kesilmiyor, komutlara yanıt yok."
        ),
        args={"package": "com.spotify.music"},
        reasoning=(
            "Kontroller işlemediğine göre süreç yanıt veremiyor; nazik "
            "terminate sonuç vermez, force_stop ile süreci öldürüyorum."
        ),
        index=11,
    ),
]

__all__ = ["SCENARIOS"]
