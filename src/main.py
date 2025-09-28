"""Meetinity Event Service application entrypoint."""
from __future__ import annotations

from flask import Flask

from src.database import init_engine
from src.routes import register_blueprints
from src.routes.dependencies import cleanup_services
from src.routes.utils import error_response

app = Flask(__name__)


def create_app() -> Flask:
    init_engine()
    register_blueprints(app)
    app.teardown_appcontext(cleanup_services)
    register_error_handlers(app)
    return app


@app.get("/health")
def health():
    return {"status": "ok", "service": "event-service"}


def register_error_handlers(flask_app: Flask) -> None:
    @flask_app.errorhandler(404)
    def handle_404(e):
        return error_response(404, "Ressource introuvable.")

    @flask_app.errorhandler(405)
    def handle_405(e):
        return error_response(405, "Méthode non autorisée pour cette ressource.")

    @flask_app.errorhandler(500)
    def handle_500(e):
        return error_response(500, "Erreur interne. On respire, on relance.")


create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5003)
