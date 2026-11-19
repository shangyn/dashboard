"""Business assistant package."""

from business_assistant.models import BusinessAssistantSetting  # noqa: F401


def register(app):
    from business_assistant.blueprint import assistant_bp

    app.register_blueprint(assistant_bp)
