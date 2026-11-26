"""Redirect astropy, astroquery and matplotlib caches away from global locations.

astropy and astroquery cache inside the dossier. matplotlib only keeps a font
cache, which is shared by every star of the workspace so it is built once.
Nothing lands in a global cache such as ~/.astropy or ~/.matplotlib.
"""

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def isolated_caches(cache_dir: Path, font_cache_dir: Path | None = None) -> Iterator[None]:
    from astropy.config import set_temp_cache, set_temp_config
    from astropy.utils import iers

    cache_dir.mkdir(parents=True, exist_ok=True)
    mpl_dir = font_cache_dir or cache_dir / "matplotlib"
    mpl_dir.mkdir(parents=True, exist_ok=True)
    previous_mpl = os.environ.get("MPLCONFIGDIR")
    os.environ["MPLCONFIGDIR"] = str(mpl_dir)
    try:
        with (
            set_temp_cache(cache_dir),
            set_temp_config(cache_dir),
            iers.conf.set_temp("auto_download", False),
        ):
            try:
                from astroquery import cache_conf
            except ImportError:  # pragma: no cover - astroquery is a runtime dependency
                yield
            else:
                with cache_conf.set_temp("cache_active", False):
                    yield
    finally:
        if previous_mpl is None:
            os.environ.pop("MPLCONFIGDIR", None)
        else:
            os.environ["MPLCONFIGDIR"] = previous_mpl
