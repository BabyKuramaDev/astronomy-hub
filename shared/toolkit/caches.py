"""Redirect astropy, astroquery, matplotlib and numba caches away from global locations.

astropy and astroquery cache inside the dossier. matplotlib only keeps a font
cache, and numba (used by wotan and transitleastsquares) keeps compiled kernels;
both are shared by every star of the workspace so they are built once. Nothing
lands in a global cache such as ~/.astropy, ~/.matplotlib or site-packages.
"""

import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path


def _set_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _reload_numba() -> None:
    """numba reads NUMBA_CACHE_DIR when it is imported; re-read it if it already was."""
    if "numba" in sys.modules:
        from numba.core import config

        config.reload_config()


@contextlib.contextmanager
def isolated_caches(cache_dir: Path, font_cache_dir: Path | None = None) -> Iterator[None]:
    from astropy.config import set_temp_cache, set_temp_config
    from astropy.utils import iers

    cache_dir.mkdir(parents=True, exist_ok=True)
    mpl_dir = font_cache_dir or cache_dir / "matplotlib"
    numba_dir = mpl_dir.parent / "numba"
    mpl_dir.mkdir(parents=True, exist_ok=True)
    numba_dir.mkdir(parents=True, exist_ok=True)
    previous_mpl = os.environ.get("MPLCONFIGDIR")
    previous_numba = os.environ.get("NUMBA_CACHE_DIR")
    os.environ["MPLCONFIGDIR"] = str(mpl_dir)
    os.environ["NUMBA_CACHE_DIR"] = str(numba_dir)
    _reload_numba()
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
        _set_env("MPLCONFIGDIR", previous_mpl)
        _set_env("NUMBA_CACHE_DIR", previous_numba)
        _reload_numba()
