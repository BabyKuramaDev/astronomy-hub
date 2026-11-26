"""Next transits from a fitted ephemeris, with their timing uncertainty.

sigma_T(n) = sqrt(sigma_t0^2 + (n sigma_P)^2), with each sigma the larger of the two
sides of the fitted interval. BTJD is BJD_TDB - 2457000; times are converted to UTC
without correcting for the observer's position (barycentric, up to about 8 minutes).
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from astropy.time import Time

BTJD_OFFSET = 2457000.0


@dataclass(frozen=True)
class Transit:
    n: int
    mid_btjd: float
    mid_utc: datetime
    ingress_utc: datetime
    egress_utc: datetime
    err_minutes: float


def btjd_to_utc(btjd: float) -> datetime:
    """UTC time, rounded to the second."""
    moment = Time(btjd + BTJD_OFFSET, format="jd", scale="tdb").utc.to_datetime(timezone=UTC)
    return (moment + timedelta(microseconds=500_000)).replace(microsecond=0)


def utc_to_btjd(moment: datetime) -> float:
    return float(Time(moment, scale="utc").tdb.jd) - BTJD_OFFSET


def next_transits(
    *,
    epoch: float,
    epoch_err: float,
    period: float,
    period_err: float,
    duration_hours: float,
    start: datetime,
    horizon_days: float,
    max_transits: int,
) -> list[Transit]:
    start_btjd = utc_to_btjd(start)
    first = max(0, math.ceil((start_btjd - epoch) / period))
    half = duration_hours / 48.0
    out = []
    n = first
    while len(out) < max_transits:
        mid = epoch + n * period
        if mid > start_btjd + horizon_days:
            break
        err_days = math.hypot(epoch_err, n * period_err)
        out.append(
            Transit(
                n=n,
                mid_btjd=mid,
                mid_utc=btjd_to_utc(mid),
                ingress_utc=btjd_to_utc(mid - half),
                egress_utc=btjd_to_utc(mid + half),
                err_minutes=err_days * 1440.0,
            )
        )
        n += 1
    return out
