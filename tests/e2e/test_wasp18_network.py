"""M2 acceptance against the real services: MAST, NASA Exoplanet Archive and ExoFOP.

Run with `make test-network`. Excluded from `make test` and CI. The MCMC is short.
"""

from pathlib import Path

import pytest

from shared.contracts import CatalogFile, DecisionFile, SignalFile, VettingFile
from shared.toolkit.dossier import Dossier
from tests.e2e.wasp18 import build_dossier, reference

pytestmark = pytest.mark.network

REF = reference()
TIC = REF["tic_id"]


def test_wasp18_complete_dossier(tmp_path: Path) -> None:
    summary = build_dossier(TIC, tmp_path, "--mode", "eval")
    root = Dossier.for_target(tmp_path, "exoplanets", TIC).root
    signal = Dossier(root).read_envelope("signal.json", SignalFile).data
    assert signal.period_days == pytest.approx(REF["period_days"], rel=0.01)
    assert Dossier(root).read_envelope("vetting.json", VettingFile).data.verdict != (
        "false_positive"
    )
    assert summary["final"] == "candidate"
    assert Dossier(root).read_envelope("catalog.json", CatalogFile).data.status == "known_planet"

    explore = build_dossier(TIC, tmp_path, "--mode", "explore", "--skip", "acquisition")
    assert explore["final"] == "known"
    assert Dossier(root).read_envelope("decision.json", DecisionFile).data.mode == "explore"
