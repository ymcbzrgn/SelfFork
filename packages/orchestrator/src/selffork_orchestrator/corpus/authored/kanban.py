"""Authored scenarios for ``kanban_card_move`` (to_column enum: backlog |
in_progress | review | done).

First vertical slice: one tool, rich scenarios, the hybrid target mix -- lean
targets for simple/unambiguous moves, short reasoning for judgement cases
(disambiguation, error recovery, review regression). All four enum columns are
covered. Every scenario is gated against the real registry by the builder.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

_TOOL = "kanban_card_move"

SCENARIOS: list[ToolScenario] = [
    # --- lean: simple, unambiguous move (review passed -> done) -------------
    ToolScenario(
        tool=_TOOL,
        archetype="happy_done",
        context=(
            "[pano] 'login refactor' kartı (card-8f2a) review sütununda; "
            "kod incelemesi onaylandı, testler yeşil."
        ),
        args={"card_id": "card-8f2a", "to_column": "done"},
        reasoning=None,
        index=0,
    ),
    # --- lean: PR opened -> move to review ---------------------------------
    ToolScenario(
        tool=_TOOL,
        archetype="ready_for_review",
        context=(
            "[pano] 'payment webhook' kartı (card-6f2b) in_progress'te; "
            "iş bitti ve PR açıldı, incelemeye hazır."
        ),
        args={"card_id": "card-6f2b", "to_column": "review"},
        reasoning=None,
        index=1,
    ),
    # --- reasoning: start work on a chosen backlog card --------------------
    ToolScenario(
        tool=_TOOL,
        archetype="start_work",
        context=(
            "[pano] 'oauth callback' kartı (card-1b7c) backlog'da. "
            "Operatör bu görevle başlamamı istedi."
        ),
        args={"card_id": "card-1b7c", "to_column": "in_progress"},
        reasoning=(
            "Görev seçildi ve üzerinde çalışılmaya başlanacak, "
            "o yüzden in_progress'e alıyorum."
        ),
        index=2,
    ),
    # --- reasoning: disambiguation between two review cards -----------------
    ToolScenario(
        tool=_TOOL,
        archetype="disambiguation",
        context=(
            "[pano] review'da iki kart var: 'login refactor' (card-8f2a, "
            "testler geçti) ve 'signup form' (card-3d9e, testler kırık). "
            "Operatör: 'geçeni kapat'."
        ),
        args={"card_id": "card-8f2a", "to_column": "done"},
        reasoning=(
            "Sadece login refactor'ın testleri geçti; signup form kırık olduğu "
            "için ona dokunmam. Geçen kartı done'a taşıyorum."
        ),
        index=3,
    ),
    # --- reasoning: error recovery, pull a blocked card back ---------------
    ToolScenario(
        tool=_TOOL,
        archetype="error_recovery",
        context=(
            "[pano] 'db migration' kartı (card-9a1d) in_progress'te ama "
            "bağımlılığı (şema onayı) beklemede; şu an ilerletilemez."
        ),
        args={"card_id": "card-9a1d", "to_column": "backlog"},
        reasoning=(
            "Bağımlılık çözülene kadar aktif çalışmadan çıkarılmalı, "
            "backlog'a geri alıyorum."
        ),
        index=4,
    ),
    # --- reasoning: review regression, bug found -> back to in_progress -----
    ToolScenario(
        tool=_TOOL,
        archetype="review_regression",
        context=(
            "[pano] 'search index' kartı (card-4c8f) review'da ama incelemede "
            "bir bug bulundu; düzeltme gerekiyor."
        ),
        args={"card_id": "card-4c8f", "to_column": "in_progress"},
        reasoning="Review'da bug çıktı, tekrar geliştirmeye alınmalı; in_progress.",
        index=5,
    ),
]

__all__ = ["SCENARIOS"]
