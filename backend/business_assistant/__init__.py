"""Business assistant package."""

import logging

from business_assistant.models import BusinessAssistantSetting  # noqa: F401


def register(app):
    from business_assistant.blueprint import assistant_bp

    app.register_blueprint(assistant_bp)
    logging.getLogger(__name__).info(
        'business assistant enabled=%s model_enabled=%s base_url=%s',
        app.config.get('ASSISTANT_ENABLED'),
        app.config.get('ASSISTANT_MODEL_ENABLED'),
        app.config.get('ASSISTANT_MODEL_BASE_URL') or '(empty)',
    )
