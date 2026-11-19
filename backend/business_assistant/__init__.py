"""Business assistant package."""


def register(app):
    from business_assistant.blueprint import assistant_bp

    app.register_blueprint(assistant_bp)
