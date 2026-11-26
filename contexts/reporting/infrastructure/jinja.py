"""Render report.md with jinja2 (StrictUndefined: a missing field is an error)."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from contexts.reporting.domain.view import compact, measurement, num

TEMPLATES = Path(__file__).resolve().parent / "templates"


def _cell(text: str) -> str:
    """Keep a note inside one Markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")


class JinjaRenderer:
    def __init__(self, template: str = "report.md.j2") -> None:
        env = Environment(
            loader=FileSystemLoader(TEMPLATES),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            autoescape=False,  # Markdown, not HTML
        )
        env.filters["num"] = num
        env.filters["meas"] = measurement
        env.filters["cell"] = _cell
        env.filters["g"] = compact
        self.template = env.get_template(template)

    def __call__(self, context: dict[str, Any]) -> str:
        return self.template.render(**context)
