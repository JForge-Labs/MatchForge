"""Jinja2 templates with automatic UI context injection."""
from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.utils.ui_context import ui_context

templates = Jinja2Templates(directory="templates")


def render(
    request: Request,
    name: str,
    context: dict | None = None,
    **kwargs,
):
    """Render a template with shared branding/env context merged in."""
    merged = ui_context(**(context or {}))
    return templates.TemplateResponse(request, name, merged, **kwargs)