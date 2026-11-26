"""M1 acceptance: WASP-18 b from MAST through every signal tool (network).

Run with `make test-network`. Excluded from `make test` and CI.
"""

from pathlib import Path

import pytest

from shared.contracts import SignalFile, StarFile
from shared.toolkit.dossier import Dossier
from tests.e2e.wasp18 import detection_chain, reference, tool

pytestmark = pytest.mark.network

REF = reference()
TIC = REF["tic_id"]


def test_wasp18_period_from_mast(tmp_path: Path) -> None:
    fetched = tool("acquisition", "fetch-lightcurves", TIC, tmp_path)
    assert fetched["sectors"]
    star = tool("acquisition", "fetch-star", TIC, tmp_path)
    assert star["radius_rsun"] is not None
    out = detection_chain(TIC, tmp_path)

    root = Dossier.for_target(tmp_path, "exoplanets", TIC).root
    signal = Dossier(root).read_envelope("signal.json", SignalFile).data
    assert signal.detected
    assert signal.period_days == pytest.approx(REF["period_days"], rel=0.01)
    assert Dossier(root).read_envelope("star.json", StarFile).data.neighbors is not None
    assert out["fit"]["planet_radius_rearth"] is not None
