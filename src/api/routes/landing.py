"""
Landing Page Route.

Serves the LocalPulse marketing landing page at the root URL.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

_templates = Environment(
    loader=FileSystemLoader("src/templates"),
    autoescape=select_autoescape(["html"]),
)

router = APIRouter(tags=["Landing"])


@router.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def landing_page() -> HTMLResponse:
    """Render the LocalPulse landing page."""
    template = _templates.get_template("landing.html")
    html = template.render()
    return HTMLResponse(content=html)
