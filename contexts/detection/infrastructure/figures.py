"""Fold figure as PNG bytes (matplotlib, Agg backend, no timestamps in metadata)."""

import io

from contexts.detection.domain.fold import FoldResult


def render_fold(result: FoldResult, title: str) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4), dpi=110)
    try:
        ax.plot(
            result.phase_hours, (result.flux - 1.0) * 1e6, ".", ms=1.5, color="0.6", rasterized=True
        )
        centers = [b.phase_hours for b in result.bins if b.depth_ppm is not None]
        values = [-b.depth_ppm for b in result.bins if b.depth_ppm is not None]  # type: ignore[operator]
        ax.plot(centers, values, "o-", color="tab:blue", ms=4, label="binned")
        ax.set_xlabel("Hours from mid-transit")
        ax.set_ylabel("Relative flux (ppm)")
        ax.set_title(title)
        ax.legend(loc="lower right")
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", metadata={"Software": None})
        return buffer.getvalue()
    finally:
        plt.close(fig)
