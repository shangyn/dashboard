import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db
from seed import seed_database
from users import users_bp
from roles import roles_bp


def create_app():
    app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')
    app.config.from_object(Config)

    # 确保上传目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)

    # 扩展初始化
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)
    jwt = JWTManager(app)

    # 注册 user_loader
    from models import User

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        user_id = jwt_data.get('sub')
        if user_id:
            return db.session.get(User, int(user_id))
        return None

    # 注册蓝图
    from auth import auth_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(roles_bp)

    # 生产环境：托管前端静态文件
    @app.route('/')
    def serve_frontend():
        if not os.path.isdir(app.static_folder):
            return 'Frontend not built. Run: cd frontend && npm run build', 503
        return send_from_directory(app.static_folder, 'index.html')

    @app.route('/<path:path>')
    def serve_frontend_fallback(path):
        if not os.path.isdir(app.static_folder):
            return 'Frontend not built', 503
        full_path = os.path.join(app.static_folder, path)
        if os.path.isfile(full_path):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, 'index.html')

    # 初始化数据库和种子数据
    with app.app_context():
        seed_database(app)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
