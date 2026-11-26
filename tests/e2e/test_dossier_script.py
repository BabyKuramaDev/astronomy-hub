"""The dossier script on a synthetic eclipsing binary: false_positive, and that verdict
stops the run before the MCMC and the review.

BLS may fold the binary at its period (the secondary eclipse then fails gate 6) or at
half of it (the eclipses alternate and fail gate 5); either hard gate must catch it."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contexts.acquisition.application.fetch_lightcurves import FetchLightcurves
from contexts.acquisition.infrastructure.spoc_fits import SpocFitsReader
from shared.contracts import DecisionFile, ModelFile, VettingFile
from shared.kernel.contexts import Context
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta
from tests.e2e.wasp18 import build_dossier
from tests.support.synthetic import Transit, box_transit, light_curve, write_spoc_fits

TIC = 777000777
HALF = 2.345  # half the binary's period


class SyntheticArchive:
    def __init__(self, files: dict[int, Path]) -> None:
        self.files = files

    def available_sectors(self, tic_id: int, author: str, exptime_s: float) -> list[int]:
        return sorted(self.files)

    def download(
        self, tic_id: int, sectors: Sequence[int], author: str, exptime_s: float, dest: Path
    ) -> dict[int, Path]:
        dest.mkdir(parents=True, exist_ok=True)
        out = {}
        for s in sectors:
            out[s] = dest / self.files[s].name
            out[s].write_bytes(self.files[s].read_bytes())
        return out


def eclipsing_binary(src: Path) -> dict[int, Path]:
    files = {}
    for k, sector in enumerate((10, 11)):
        time, flux, err = light_curve(start=1000.0 + 13.5 * k, days=13.0, noise_ppm=500.0,
                                      seed=20 + k)  # fmt: skip
        for offset, depth in ((0.0, 8000.0), (HALF, 3000.0)):
            flux = flux * box_transit(time, Transit(2 * HALF, 1000.6 + offset, 3.0, depth))
        files[sector] = write_spoc_fits(
            src / f"s{sector}.fits", tic_id=TIC, sector=sector, time=time, flux=flux,
            flux_err=err,
        )  # fmt: skip
    return files


@pytest.fixture(scope="module")
def eb(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    tmp = tmp_path_factory.mktemp("eb")
    workspace = tmp / "ws"
    dossier = Dossier.for_target(workspace, "exoplanets", TIC)
    meta = ToolMeta(Context.ACQUISITION, "fetch-lightcurves", TIC, "exoplanets", "0.1.0",
                    lambda: datetime.now(UTC))  # fmt: skip
    FetchLightcurves(
        SyntheticArchive(eclipsing_binary(tmp / "src")), SpocFitsReader(), dossier, meta,
        load_mission("exoplanets").acquisition,
    ).execute()  # fmt: skip
    return dossier.root, build_dossier(TIC, workspace, "--skip", "acquisition,catalog")


def test_eclipsing_binary_is_a_false_positive(eb: tuple[Path, dict]) -> None:
    root, summary = eb
    assert summary["final"] == "false_positive"
    vetting = Dossier(root).read_envelope("vetting.json", VettingFile).data
    failed = {g.id for g in vetting.gates if g.severity == "hard" and g.status == "fail"}
    assert failed & {"odd-even", "secondary"}
    assert Dossier(root).read_envelope("decision.json", DecisionFile).data.final == (
        "false_positive"
    )


def test_false_positive_skips_mcmc_and_review(eb: tuple[Path, dict]) -> None:
    root, summary = eb
    tools = [s["tool"] for s in summary["steps"]]
    assert "review reproduce" not in tools
    assert tools.count("modeling fit-transit") == 1
    assert Dossier(root).read_envelope("model.json", ModelFile).data.method == "quick"
    assert not (root / "review.json").exists()
    assert not (root / "ephemeris.json").exists()
    assert not (root / "report.md").exists()  # the eval profile ends at decide
