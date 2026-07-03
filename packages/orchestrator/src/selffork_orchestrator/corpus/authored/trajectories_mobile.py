"""Agentic multi-tool trajectories (mobile) — act -> observe -> act -> ... done.

Each trajectory emits one training sample per step over a growing prefix, so the
small model learns to CHAIN tools: pick the next action given the goal, the
prior actions, and their observed results. This is the "önce X, sonucu gör,
sonra Y" agentic behaviour that single-call scenarios can't teach.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import AgenticStep, AgenticTrajectory

TRAJECTORIES: list[AgenticTrajectory] = [
    AgenticTrajectory(
        name="android_login",
        goal=(
            "[görev] Android'de Instagram'a 'test_user' hesabıyla giriş "
            "yapılacak. Uygulama şu an kapalı."
        ),
        steps=[
            AgenticStep(
                tool="android_app_launch",
                args={"package": "com.instagram.android"},
                result=(
                    "[sonuç] Instagram açıldı; kullanıcı adı + şifre alanları "
                    "olan giriş ekranı görünüyor."
                ),
                reasoning="Uygulama kapalı; akışa soğuk başlatmayla başlıyorum.",
            ),
            AgenticStep(
                tool="android_a11y_tree",
                args={},
                result=(
                    "[sonuç] a11y ağacı: EditText#username bounds=[40,300,680,360], "
                    "EditText#password bounds=[40,380,680,440], Button 'Giriş yap' "
                    "bounds=[40,480,680,540]."
                ),
                reasoning=(
                    "Alanlara dokunmak için koordinat lazım; ekran görüntüsü piksel "
                    "verir, a11y ağacı bounds değerlerini verir."
                ),
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 330},
                result="[sonuç] Kullanıcı adı alanı odakta, klavye açıldı.",
                reasoning="username alanının bounds ortasına dokunup odaklanıyorum.",
            ),
            AgenticStep(
                tool="android_type",
                args={"text": "test_user"},
                result="[sonuç] Alanda 'test_user' yazıyor.",
                reasoning="Odaktaki alan boştu; kullanıcı adını düz type ile yazıyorum.",
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 410},
                result="[sonuç] Şifre alanı odakta.",
                reasoning="Sıradaki alan şifre; onun bounds ortasına dokunuyorum.",
            ),
            AgenticStep(
                tool="android_type",
                args={"text": "S3cret!"},
                result="[sonuç] Şifre girildi (maskeli görünüyor).",
                reasoning="Odaktaki şifre alanına parolayı yazıyorum.",
            ),
            AgenticStep(
                tool="android_click",
                args={"x": 360, "y": 510},
                result="[sonuç] Giriş başarılı; ana akış (feed) yüklendi.",
                reasoning="İki alan da dolu; 'Giriş yap' butonunun ortasına basıyorum.",
            ),
        ],
    ),
]

__all__ = ["TRAJECTORIES"]
