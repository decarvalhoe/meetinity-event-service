"""Blueprint registration helpers."""
from __future__ import annotations

from flask import Flask

from .event_categories import categories_bp
from .event_series import series_bp
from .event_tags import tags_bp
from .event_templates import templates_bp
from .events import events_bp
from .recommendations import recommendations_bp
from .search import search_bp

__all__ = ["register_blueprints"]


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(events_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(recommendations_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(series_bp)
    app.register_blueprint(templates_bp)
