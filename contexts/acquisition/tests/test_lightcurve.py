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
        centroid_col=np.full(6, np.nan),
        centroid_row=np.full(6, np.nan),
    )
    np.testing.assert_array_equal(valid_mask(lc), [True, False, False, False, False, True])


def test_missing_centroid_does_not_invalidate_a_cadence() -> None:
    lc = SectorLightcurveRaw(
        sector=2,
        tic_id=1,
        time_btjd=np.array([1.0, 2.0]),
        flux=np.ones(2),
        flux_err=np.full(2, 0.1),
        quality=np.zeros(2, dtype=int),
        centroid_col=np.array([np.nan, 100.0]),
        centroid_row=np.array([np.nan, 200.0]),
    )
    assert valid_mask(lc).all()
