import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_assistant_env():
    # gunicorn does not read dotenv files; load it before Config is built.
    candidates = (
        os.path.join(BASE_DIR, '.assistant.env'),
        os.path.join(os.path.dirname(BASE_DIR), '.assistant.env'),
    )
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key:
                        os.environ[key] = value
        except OSError:
            continue
        break


_load_assistant_env()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{os.path.join(BASE_DIR, "instance", "system.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_QUERY_STRING_NAME = 'token'
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    DASHBOARD_OUTPUT_DIR = os.path.join(BASE_DIR, 'var', 'dashboards')

    # 经营助手：默认开启入口，默认不启用外部模型；关闭总开关不影响现有模块。
    ASSISTANT_ENABLED = os.environ.get('ASSISTANT_ENABLED', '1') == '1'
    ASSISTANT_MODEL_ENABLED = os.environ.get('ASSISTANT_MODEL_ENABLED', '0') == '1'
    ASSISTANT_MODEL_BASE_URL = os.environ.get('ASSISTANT_MODEL_BASE_URL', '')
    ASSISTANT_MODEL_API_KEY = os.environ.get('ASSISTANT_MODEL_API_KEY', '')
    ASSISTANT_MODEL_NAME = os.environ.get('ASSISTANT_MODEL_NAME', 'deepseek-chat')
    ASSISTANT_MODEL_TIMEOUT = int(os.environ.get('ASSISTANT_MODEL_TIMEOUT', '25'))
    ASSISTANT_EXPORT_MAX_AGE = int(os.environ.get('ASSISTANT_EXPORT_MAX_AGE', '900'))
