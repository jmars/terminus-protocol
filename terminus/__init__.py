"""terminus: runnable scaffold for the Paper 1 discriminator protocol (Section 5).

The protocol is specified in Sections 4 and 5 of the manuscript. This package
implements its components as runnable structure: Phase 0 representation honesty,
Phase 1 the derivation probe, Phase 2 pressure and the per-drive offers, the copy
status probe, the O1 to O4 outcome rubric with blind reason typing, the four
controls, and preregistration checking. No subject was run; the agent-under-test is
an interface, and the scripted adapter exercises the scoring path.

Implementation status, stated honestly as the paper states it: scaffolded as
runnable structure with no subjects run, and the O1 to O4 outcomes are PREDICTION
until a run lands.
"""
from __future__ import annotations

__version__ = "0.1.0-scaffold"

__all__ = [
    "adapters",
    "controls",
    "driver",
    "falsifiers",
    "fixtures",
    "offers",
    "outcomes",
    "phase0",
    "phase1",
    "phase2",
    "prereg",
    "records",
    "selftest",
    "vocabulary",
]
