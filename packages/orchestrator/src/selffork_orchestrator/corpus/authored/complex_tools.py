"""Authored scenarios for complex-schema tools the mechanical backbone + the
Fable domain banks did not cover (nested object/array args).

Currently just ``browser_fill_form`` (a ``{selector: value}`` object) — the one
tool left uncovered after the Fable fan-out, so the corpus reaches 289/289. Add
future complex-schema stragglers here.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario

SCENARIOS: list[ToolScenario] = [
    # browser_fill_form: multiple {selector: value} at once vs N browser_type.
    ToolScenario(
        tool="browser_fill_form",
        archetype="multi_field_form_fill",
        context=(
            "[tarayıcı] Kayıt formunda dört alan var: #email, #password, "
            "#first-name, #last-name. Operatör: 'Formu test verisiyle doldur.'"
        ),
        args={
            "fields": {
                "#email": "test@arketic.dev",
                "#password": "Test1234!",
                "#first-name": "Yamaç",
                "#last-name": "Test",
            }
        },
        reasoning=(
            "Birden çok alan tek seferde doldurulacak; her alan için ayrı "
            "browser_type dört tur ve daha kırılgan olur. fill_form "
            "selector->değer eşlemesini tek çağrıda uygular."
        ),
        index=0,
    ),
]

__all__ = ["SCENARIOS"]
