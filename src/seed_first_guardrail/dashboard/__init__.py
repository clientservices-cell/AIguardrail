"""Public dashboard: a single self-contained HTML page rendered from a KPI snapshot.

``render(snapshot)`` embeds the snapshot JSON into ``template.html``. The page also tries
``snapshot.json`` next to itself first, so a static host can refresh the data without
regenerating the HTML.

🧒 This turns the scoreboard numbers into the poster on the classroom wall, with a
grown-up side and a kid side.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

PLACEHOLDER = "/*__SNAPSHOT__*/null"


def template() -> str:
    return resources.files(__package__).joinpath("template.html").read_text(encoding="utf-8")


def render(snapshot: dict[str, Any]) -> str:
    """Return the dashboard HTML with ``snapshot`` embedded (safe inside a script tag)."""
    data = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    # No "</script>" or "<!--" can survive inside the JSON block.
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = template()
    if PLACEHOLDER not in page:  # pragma: no cover - guards template edits
        raise RuntimeError("dashboard template is missing the snapshot placeholder")
    return page.replace(PLACEHOLDER, data, 1)


__all__ = ["render", "template"]
