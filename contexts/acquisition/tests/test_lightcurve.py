import numpy as np

from contexts.acquisition.domain.lightcurve import SectorLightcurveRaw, valid_mask


def test_valid_mask_drops_nan_and_flagged_cadences() -> None:
    lc = SectorLightcurveRaw(
        sector=2,
        tic_id=1,
        time_btjd=np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0]),
        flux=np.array([1.0, np.nan, 1.0, 1.0, 1.0, 1.0]),
        flux_err=np.array([0.1, 0.1, 0.1, np.nan, 0.1, 0.1]),
        quality=np.array([0, 0, 0, 0, 128, 0]),
    )
    np.testing.assert_array_equal(valid_mask(lc), [True, False, False, False, False, True])
