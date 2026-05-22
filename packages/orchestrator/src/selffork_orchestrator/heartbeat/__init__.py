"""Self Jr Heartbeat — autonomous outer-loop scheduler (S-Auto, ADR-008).

The :mod:`heartbeat` package implements ADR-008's outer ``perceive →
decide → act → record`` daemon that sits above the existing round-loop
in :mod:`selffork_orchestrator.lifecycle.session`. The outer loop picks
which project/task/CLI to run (or waits) — the inner loop runs the
selected task to ``[SELFFORK:DONE]``.

Faz A scope (current): scheduler scaffold — start/stop lifecycle, tick
loop, pause + active-hours gates, event queue. Faz B/C/D fill in the
legal-action filter, deliberative selector, and action vocabulary.
"""
