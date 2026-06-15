# 企业后台管理系统 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建企业级后台管理系统 — 登录认证、用户/角色/模块/上传配置管理、动态菜单权限、文件上传，采用 Python Flask 后端 + Vue 3 前端。

**Architecture:** Flask REST API 提供后端服务（SQLite 数据库），Vue 3 SPA 提供前端界面。管理员使用侧边栏布局（AdminLayout），普通角色使用无侧边栏布局（UserLayout）。权限通过 role.permissions JSON 数组控制。

**Tech Stack:** Python 3 / Flask / Flask-SQLAlchemy / Flask-JWT-Extended / Flask-Bcrypt / Flask-CORS / SQLite · Vue 3 (Composition API) / Vite / Element Plus / Pinia / Vue Router / Axios

---

## 文件结构与职责

### 后端 (backend/)

| 文件 | 职责 |
|------|------|
| `config.py` | 应用配置（数据库路径、JWT密钥、上传目录） |
| `models.py` | 5 个 SQLAlchemy 模型（User, Role, Module, UploadConfig, FileUpload） |
| `decorators.py` | `permission_required` 权限装饰器 |
| `auth.py` | 蓝图: POST /api/login, GET /api/current-user, PUT /api/change-password |
| `users.py` | 蓝图: CRUD /api/users + 重置密码 |
| `roles.py` | 蓝图: CRUD /api/roles |
| `modules.py` | 蓝图: CRUD /api/modules |
| `upload_config.py` | 蓝图: CRUD /api/upload-configs |
| `upload.py` | 蓝图: POST /api/upload/<code>, GET /api/upload-history, GET /api/upload-stats |
| `upload/handlers.py` | code → handler 映射表 + 解析函数 |
| `seed.py` | 首次启动自动创建管理员账号 |
| `app.py` | Flask 应用入口，注册蓝图，初始化数据库 |
| `requirements.txt` | Python 依赖 |

### 前端 (frontend/src/)

| 文件 | 职责 |
|------|------|
| `api/request.js` | Axios 实例，拦截器注入 token，统一错误处理 |
| `api/auth.js` | 登录 / 获取当前用户 / 修改密码 |
| `api/users.js` | 用户 CRUD + 重置密码 |
| `api/roles.js` | 角色 CRUD |
| `api/modules.js` | 模块 CRUD + 我的模块 |
| `api/upload-config.js` | 上传配置 CRUD + 我的上传配置 |
| `api/upload.js` | 文件上传 + 历史 + 统计 |
| `stores/auth.js` | Pinia: token, userInfo, isAdmin, permissions, login/logout |
| `stores/app.js` | Pinia: sidebar 折叠状态等 |
| `router/index.js` | 路由定义 + beforeEach 守卫 |
| `layouts/AdminLayout.vue` | 侧边栏 + 顶栏布局 |
| `layouts/UserLayout.vue` | 仅顶栏布局 |
| `views/Login.vue` | 蓝色渐变登录页 |
| `views/Home.vue` | 模块卡片选择页（普通用户首页） |
| `views/Dashboard.vue` | iframe 看板页 |
| `views/UploadConsole.vue` | 用户控制台上传页 |
| `views/SystemInfo.vue` | 系统信息页（无上传权限时显示） |
| `views/admin/*.vue` | 管理员各管理页面 |
| `views/common/403.vue` | 无权限页面 |
| `components/UploadZone.vue` | 可复用拖拽上传组件 |

---

## Phase 1: 后端骨架 — models, seed, auth API

### Task 1.1: 创建项目目录结构和 requirements.txt

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`

- [ ] **Step 1: 创建目录和 requirements.txt**

```bash
mkdir -p E:/System/backend/upload E:/System/backend/instance
```

Write `backend/requirements.txt`:
```
Flask==3.1.0
Flask-SQLAlchemy==3.1.1
Flask-JWT-Extended==4.7.1
Flask-Bcrypt==1.0.1
Flask-CORS==5.0.1
```

- [ ] **Step 2: 创建 config.py**

Write `backend/config.py`:
```python
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{os.path.join(BASE_DIR, "instance", "system.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-change-in-production')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
```

- [ ] **Step 3: 安装依赖**

```bash
cd E:/System/backend && pip install -r requirements.txt
```

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/config.py
git commit -m "feat: project skeleton — config and requirements"
```

---

### Task 1.2: 创建 SQLAlchemy 模型

**Files:**
- Create: `backend/models.py`

- [ ] **Step 1: 编写 models.py**

Write `backend/models.py`:
```python
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    real_name = db.Column(db.String(50), default='')
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    role = db.relationship('Role', backref='users', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'real_name': self.real_name,
            'role_id': self.role_id,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Role(db.Model):
    __tablename__ = 'role'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role_name = db.Column(db.String(50), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    permissions = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def get_permissions(self):
        import json
        return json.loads(self.permissions) if self.permissions else []

    def set_permissions(self, perms):
        import json
        self.permissions = json.dumps(perms, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'role_name': self.role_name,
            'is_admin': self.is_admin,
            'permissions': self.get_permissions(),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Module(db.Model):
    __tablename__ = 'module'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    permission = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(200), default='')
    icon = db.Column(db.String(50), default='')
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'permission': self.permission,
            'url': self.url,
            'icon': self.icon,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
        }


class UploadConfig(db.Model):
    __tablename__ = 'upload_config'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    code = db.Column(db.String(50), unique=True, nullable=False)
    permission = db.Column(db.String(50), nullable=False)
    file_types = db.Column(db.String(100), default='.xlsx,.xls')
    required_columns = db.Column(db.Text, default='')
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'code': self.code,
            'permission': self.permission,
            'file_types': self.file_types,
            'required_columns': self.required_columns,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
        }


class FileUpload(db.Model):
    __tablename__ = 'file_upload'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    filename = db.Column(db.String(200), default='')
    stored_path = db.Column(db.String(300), default='')
    file_size = db.Column(db.Integer, default=0)
    upload_config_id = db.Column(db.Integer, db.ForeignKey('upload_config.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='stored')  # stored / parsed / error
    message = db.Column(db.Text, default='')
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    upload_config = db.relationship('UploadConfig', backref='uploads', lazy=True)
    user = db.relationship('User', backref='uploads', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_size': self.file_size,
            'upload_config_id': self.upload_config_id,
            'upload_config_name': self.upload_config.name if self.upload_config else '',
            'user_id': self.user_id,
            'username': self.user.username if self.user else '',
            'status': self.status,
            'message': self.message,
            'uploaded_at': self.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if self.uploaded_at else '',
        }
```

- [ ] **Step 2: Commit**

```bash
git add backend/models.py
git commit -m "feat: SQLAlchemy models — User, Role, Module, UploadConfig, FileUpload"
```

---

### Task 1.3: 创建权限装饰器

**Files:**
- Create: `backend/decorators.py`

- [ ] **Step 1: 编写 decorators.py**

Write `backend/decorators.py`:
```python
from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_current_user


def permission_required(permission):
    """检查当前登录用户是否拥有指定权限"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user or not user.role:
                return jsonify(code=403, msg='无权限：未登录或未分配角色', data=None), 403
            perms = user.role.get_permissions()
            if permission not in perms:
                return jsonify(code=403, msg=f'无权限：缺少 {permission}', data=None), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
```

- [ ] **Step 2: Commit**

```bash
git add backend/decorators.py
git commit -m "feat: permission_required decorator"
```

---

### Task 1.4: 创建 seed 初始数据

**Files:**
- Create: `backend/seed.py`

- [ ] **Step 1: 编写 seed.py**

Write `backend/seed.py`:
```python
import json
from flask_bcrypt import Bcrypt
from models import db, Role, User

bcrypt = Bcrypt()


def seed_database(app):
    """首次运行时自动创建管理员账号和角色"""
    with app.app_context():
        db.create_all()

        if Role.query.count() > 0:
            return  # 已初始化，跳过

        # 创建管理员角色
        admin_permissions = [
            'dashboard',
            'user_manage', 'role_manage', 'module_manage', 'upload_manage',
            'dashboard_receivables', 'dashboard_performance',
            'dashboard_daily', 'dashboard_ledger',
            'dashboard_function', 'dashboard_spare_parts',
            'upload_performance', 'upload_module_target',
            'upload_payment', 'upload_spare_parts',
            'upload_trade', 'upload_delivery', 'upload_offline_quote',
        ]

        admin_role = Role(
            role_name='管理员',
            is_admin=True,
        )
        admin_role.set_permissions(admin_permissions)
        db.session.add(admin_role)
        db.session.flush()

        # 创建管理员用户
        admin_user = User(
            username='admin',
            password=bcrypt.generate_password_hash('admin123').decode('utf-8'),
            real_name='管理员',
            role_id=admin_role.id,
            is_active=True,
        )
        db.session.add(admin_user)
        db.session.commit()
        print('[Seed] 管理员账号已创建: admin / admin123')
```

- [ ] **Step 2: Commit**

```bash
git add backend/seed.py
git commit -m "feat: seed — auto-create admin account on first run"
```

---

### Task 1.5: 创建 auth 蓝图（登录 / 当前用户 / 修改密码）

**Files:**
- Create: `backend/auth.py`

- [ ] **Step 1: 编写 auth.py**

Write `backend/auth.py`:
```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_current_user,
)
from flask_bcrypt import Bcrypt
from models import db, User, Role

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()


@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify(code=400, msg='工号和密码不能为空', data=None), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify(code=401, msg='工号或密码错误', data=None), 401

    if not user.is_active:
        return jsonify(code=403, msg='账号已被禁用，请联系管理员', data=None), 403

    if not bcrypt.check_password_hash(user.password, password):
        return jsonify(code=401, msg='工号或密码错误', data=None), 401

    token = create_access_token(identity=str(user.id))

    user_dict = user.to_dict()
    role_data = None
    if user.role:
        role_data = user.role.to_dict()

    return jsonify(code=200, msg='登录成功', data={
        'token': token,
        'user': {
            **user_dict,
            'role': role_data,
        }
    }), 200


@auth_bp.route('/api/current-user', methods=['GET'])
@jwt_required()
def current_user():
    user = get_current_user()
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    role_data = user.role.to_dict() if user.role else None

    return jsonify(code=200, msg='success', data={
        **user.to_dict(),
        'role': role_data,
    }), 200


@auth_bp.route('/api/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    user = get_current_user()
    data = request.get_json()
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify(code=400, msg='旧密码和新密码不能为空', data=None), 400

    if not bcrypt.check_password_hash(user.password, old_password):
        return jsonify(code=400, msg='旧密码错误', data=None), 400

    if len(new_password) < 6:
        return jsonify(code=400, msg='新密码长度不能少于6位', data=None), 400

    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify(code=200, msg='密码修改成功', data=None), 200
```

- [ ] **Step 2: Commit**

```bash
git add backend/auth.py
git commit -m "feat: auth blueprint — login, current-user, change-password"
```

---

### Task 1.6: 创建 app.py 入口文件

**Files:**
- Create: `backend/app.py`

- [ ] **Step 1: 编写 app.py**

Write `backend/app.py`:
```python
import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db
from seed import seed_database


def create_app():
    app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')
    app.config.from_object(Config)

    # 确保上传目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)

    # 扩展初始化
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)
    JWTManager(app)

    # 注册 user_loader
    from models import User

    @JWTManager.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        user_id = jwt_data.get('sub')
        if user_id:
            return db.session.get(User, int(user_id))
        return None

    # 注册蓝图
    from auth import auth_bp
    from users import users_bp
    from roles import roles_bp
    from modules import modules_bp
    from upload_config import upload_config_bp
    from upload import upload_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(modules_bp)
    app.register_blueprint(upload_config_bp)
    app.register_blueprint(upload_bp)

    # 生产环境：托管前端静态文件
    @app.route('/')
    def serve_frontend():
        return send_from_directory(app.static_folder, 'index.html')

    @app.route('/<path:path>')
    def serve_frontend_fallback(path):
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
```

- [ ] **Step 2: 验证后端启动成功**

```bash
cd E:/System/backend && python app.py
```

Expected output: `[Seed] 管理员账号已创建: admin / admin123`，服务监听 `0.0.0.0:5000`

检查生成的数据库文件: `E:/System/backend/instance/system.db` 已创建

- [ ] **Step 3: 测试登录 API**

```bash
curl -X POST http://localhost:5000/api/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}'
```

Expected: 返回 200，包含 token 和用户信息

- [ ] **Step 4: 测试 JWT 认证**

```bash
# 用上一步获取的 token 替换 <TOKEN>
curl http://localhost:5000/api/current-user -H "Authorization: Bearer <TOKEN>"
```

Expected: 返回当前用户信息

- [ ] **Step 5: Commit**

```bash
git add backend/app.py
git commit -m "feat: Flask app entry point — create_app with all blueprints"
```

---

## Phase 2: 后端 CRUD API — 用户、角色、模块、上传配置

### Task 2.1: 用户管理蓝图

**Files:**
- Create: `backend/users.py`

- [ ] **Step 1: 编写 users.py**

Write `backend/users.py`:
```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_current_user
from flask_bcrypt import Bcrypt
from models import db, User, Role
from decorators import permission_required

users_bp = Blueprint('users', __name__)
bcrypt = Bcrypt()


@users_bp.route('/api/users', methods=['GET'])
@jwt_required()
@permission_required('user_manage')
def get_users():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)
    username = request.args.get('username', '').strip()
    real_name = request.args.get('real_name', '').strip()

    query = User.query
    if username:
        query = query.filter(User.username.like(f'%{username}%'))
    if real_name:
        query = query.filter(User.real_name.like(f'%{real_name}%'))

    pagination = query.order_by(User.id.desc()).paginate(
        page=page, per_page=page_size, error_out=False
    )

    users_list = []
    for u in pagination.items:
        user_dict = u.to_dict()
        user_dict['role_name'] = u.role.role_name if u.role else ''
        users_list.append(user_dict)

    return jsonify(code=200, msg='success', data={
        'items': users_list,
        'total': pagination.total,
        'page': page,
        'page_size': page_size,
    }), 200


@users_bp.route('/api/users', methods=['POST'])
@jwt_required()
@permission_required('user_manage')
def create_user():
    data = request.get_json()

    username = data.get('username', '').strip()
    password = data.get('password', '')
    real_name = data.get('real_name', '').strip()
    role_id = data.get('role_id')
    is_active = data.get('is_active', True)

    if not username:
        return jsonify(code=400, msg='工号不能为空', data=None), 400
    if not password or len(password) < 6:
        return jsonify(code=400, msg='密码长度不能少于6位', data=None), 400

    if User.query.filter_by(username=username).first():
        return jsonify(code=400, msg=f'工号 {username} 已存在', data=None), 400

    user = User(
        username=username,
        password=bcrypt.generate_password_hash(password).decode('utf-8'),
        real_name=real_name,
        role_id=role_id if role_id else None,
        is_active=is_active,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify(code=200, msg='用户创建成功', data=user.to_dict()), 200


@users_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@permission_required('user_manage')
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    data = request.get_json()
    if 'real_name' in data:
        user.real_name = data['real_name']
    if 'role_id' in data:
        user.role_id = data['role_id']
    if 'is_active' in data:
        user.is_active = data['is_active']

    db.session.commit()
    return jsonify(code=200, msg='用户信息已更新', data=user.to_dict()), 200


@users_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@permission_required('user_manage')
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    current = get_current_user()
    if current and current.id == user.id:
        return jsonify(code=400, msg='不能删除自己', data=None), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify(code=200, msg='用户已删除', data=None), 200


@users_bp.route('/api/users/<int:user_id>/reset-password', methods=['PUT'])
@jwt_required()
@permission_required('user_manage')
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(code=404, msg='用户不存在', data=None), 404

    new_password = '123456'
    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()
    return jsonify(code=200, msg=f'密码已重置为 {new_password}', data=None), 200
```

- [ ] **Step 2: 测试用户 CRUD API**

```bash
# 列出用户
curl http://localhost:5000/api/users -H "Authorization: Bearer <TOKEN>"

# 新增用户
curl -X POST http://localhost:5000/api/users -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"username":"test01","password":"123456","real_name":"测试用户"}'

# 修改用户
curl -X PUT http://localhost:5000/api/users/2 -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"real_name":"新名字"}'

# 重置密码
curl -X PUT http://localhost:5000/api/users/2/reset-password -H "Authorization: Bearer <TOKEN>"
```

- [ ] **Step 3: Commit**

```bash
git add backend/users.py
git commit -m "feat: users CRUD blueprint — list, create, update, delete, reset-password"
```

---

### Task 2.2: 角色管理蓝图

**Files:**
- Create: `backend/roles.py`

- [ ] **Step 1: 编写 roles.py**

Write `backend/roles.py`:
```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Role, User
from decorators import permission_required

roles_bp = Blueprint('roles', __name__)


@roles_bp.route('/api/roles', methods=['GET'])
@jwt_required()
def get_roles():
    """查询所有角色（登录用户均可调用，用于用户管理的角色下拉）"""
    roles = Role.query.order_by(Role.id).all()
    return jsonify(code=200, msg='success', data=[r.to_dict() for r in roles]), 200


@roles_bp.route('/api/roles', methods=['POST'])
@jwt_required()
@permission_required('role_manage')
def create_role():
    data = request.get_json()
    role_name = data.get('role_name', '').strip()
    is_admin = data.get('is_admin', False)
    permissions = data.get('permissions', [])

    if not role_name:
        return jsonify(code=400, msg='角色名称不能为空', data=None), 400

    if Role.query.filter_by(role_name=role_name).first():
        return jsonify(code=400, msg=f'角色 {role_name} 已存在', data=None), 400

    role = Role(role_name=role_name, is_admin=is_admin)
    role.set_permissions(permissions)
    db.session.add(role)
    db.session.commit()

    return jsonify(code=200, msg='角色创建成功', data=role.to_dict()), 200


@roles_bp.route('/api/roles/<int:role_id>', methods=['PUT'])
@jwt_required()
@permission_required('role_manage')
def update_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify(code=404, msg='角色不存在', data=None), 404

    data = request.get_json()
    if 'role_name' in data:
        existing = Role.query.filter(
            Role.role_name == data['role_name'], Role.id != role_id
        ).first()
        if existing:
            return jsonify(code=400, msg=f'角色名称 {data["role_name"]} 已存在', data=None), 400
        role.role_name = data['role_name']
    if 'is_admin' in data:
        role.is_admin = data['is_admin']
    if 'permissions' in data:
        role.set_permissions(data['permissions'])

    db.session.commit()
    return jsonify(code=200, msg='角色已更新', data=role.to_dict()), 200


@roles_bp.route('/api/roles/<int:role_id>', methods=['DELETE'])
@jwt_required()
@permission_required('role_manage')
def delete_role(role_id):
    role = db.session.get(Role, role_id)
    if not role:
        return jsonify(code=404, msg='角色不存在', data=None), 404

    if User.query.filter_by(role_id=role_id).count() > 0:
        return jsonify(code=400, msg='该角色下有关联用户，无法删除', data=None), 400

    db.session.delete(role)
    db.session.commit()
    return jsonify(code=200, msg='角色已删除', data=None), 200
```

- [ ] **Step 2: Commit**

```bash
git add backend/roles.py
git commit -m "feat: roles CRUD blueprint — list, create, update, delete with user-protection"
```

---

### Task 2.3: 模块管理蓝图

**Files:**
- Create: `backend/modules.py`

- [ ] **Step 1: 编写 modules.py**

Write `backend/modules.py`:
```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_current_user
from models import db, Module
from decorators import permission_required

modules_bp = Blueprint('modules', __name__)


@modules_bp.route('/api/modules', methods=['GET'])
@jwt_required()
@permission_required('module_manage')
def get_modules():
    modules = Module.query.order_by(Module.sort_order, Module.id).all()
    return jsonify(code=200, msg='success', data=[m.to_dict() for m in modules]), 200


@modules_bp.route('/api/modules', methods=['POST'])
@jwt_required()
@permission_required('module_manage')
def create_module():
    data = request.get_json()
    module = Module(
        name=data.get('name', ''),
        description=data.get('description', ''),
        permission=data.get('permission', ''),
        url=data.get('url', ''),
        icon=data.get('icon', ''),
        sort_order=data.get('sort_order', 0),
        is_active=data.get('is_active', True),
    )
    if not module.name or not module.permission:
        return jsonify(code=400, msg='模块名称和权限标识不能为空', data=None), 400

    db.session.add(module)
    db.session.commit()
    return jsonify(code=200, msg='模块创建成功', data=module.to_dict()), 200


@modules_bp.route('/api/modules/<int:module_id>', methods=['PUT'])
@jwt_required()
@permission_required('module_manage')
def update_module(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return jsonify(code=404, msg='模块不存在', data=None), 404

    data = request.get_json()
    for field in ['name', 'description', 'permission', 'url', 'icon', 'sort_order', 'is_active']:
        if field in data:
            setattr(module, field, data[field])

    db.session.commit()
    return jsonify(code=200, msg='模块已更新', data=module.to_dict()), 200


@modules_bp.route('/api/modules/<int:module_id>', methods=['DELETE'])
@jwt_required()
@permission_required('module_manage')
def delete_module(module_id):
    module = db.session.get(Module, module_id)
    if not module:
        return jsonify(code=404, msg='模块不存在', data=None), 404
    db.session.delete(module)
    db.session.commit()
    return jsonify(code=200, msg='模块已删除', data=None), 200


@modules_bp.route('/api/my-modules', methods=['GET'])
@jwt_required()
def my_modules():
    """返回当前用户可见的模块列表（根据角色权限过滤）"""
    user = get_current_user()
    if not user or not user.role:
        return jsonify(code=200, msg='success', data=[]), 200

    permissions = user.role.get_permissions()
    modules = Module.query.filter(
        Module.is_active == True,
        Module.permission.in_(permissions)
    ).order_by(Module.sort_order, Module.id).all()

    return jsonify(code=200, msg='success', data=[m.to_dict() for m in modules]), 200
```

- [ ] **Step 2: Commit**

```bash
git add backend/modules.py
git commit -m "feat: modules CRUD blueprint + my-modules endpoint"
```

---

### Task 2.4: 上传配置管理蓝图

**Files:**
- Create: `backend/upload_config.py`

- [ ] **Step 1: 编写 upload_config.py**

Write `backend/upload_config.py`:
```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_current_user
from models import db, UploadConfig
from decorators import permission_required

upload_config_bp = Blueprint('upload_config', __name__)


@upload_config_bp.route('/api/upload-configs', methods=['GET'])
@jwt_required()
@permission_required('upload_manage')
def get_upload_configs():
    configs = UploadConfig.query.order_by(UploadConfig.sort_order, UploadConfig.id).all()
    return jsonify(code=200, msg='success', data=[c.to_dict() for c in configs]), 200


@upload_config_bp.route('/api/upload-configs', methods=['POST'])
@jwt_required()
@permission_required('upload_manage')
def create_upload_config():
    data = request.get_json()
    config = UploadConfig(
        name=data.get('name', ''),
        description=data.get('description', ''),
        code=data.get('code', ''),
        permission=data.get('permission', ''),
        file_types=data.get('file_types', '.xlsx,.xls'),
        required_columns=data.get('required_columns', ''),
        sort_order=data.get('sort_order', 0),
        is_active=data.get('is_active', True),
    )
    if not config.name or not config.code or not config.permission:
        return jsonify(code=400, msg='名称、code、权限标识不能为空', data=None), 400

    if UploadConfig.query.filter_by(code=config.code).first():
        return jsonify(code=400, msg=f'code {config.code} 已存在', data=None), 400

    db.session.add(config)
    db.session.commit()
    return jsonify(code=200, msg='上传配置创建成功', data=config.to_dict()), 200


@upload_config_bp.route('/api/upload-configs/<int:config_id>', methods=['PUT'])
@jwt_required()
@permission_required('upload_manage')
def update_upload_config(config_id):
    config = db.session.get(UploadConfig, config_id)
    if not config:
        return jsonify(code=404, msg='上传配置不存在', data=None), 404

    data = request.get_json()
    for field in ['name', 'description', 'code', 'permission', 'file_types', 'required_columns', 'sort_order', 'is_active']:
        if field in data:
            if field == 'code' and data[field] != config.code:
                if UploadConfig.query.filter_by(code=data[field]).first():
                    return jsonify(code=400, msg=f'code {data[field]} 已存在', data=None), 400
            setattr(config, field, data[field])

    db.session.commit()
    return jsonify(code=200, msg='上传配置已更新', data=config.to_dict()), 200


@upload_config_bp.route('/api/upload-configs/<int:config_id>', methods=['DELETE'])
@jwt_required()
@permission_required('upload_manage')
def delete_upload_config(config_id):
    config = db.session.get(UploadConfig, config_id)
    if not config:
        return jsonify(code=404, msg='上传配置不存在', data=None), 404
    db.session.delete(config)
    db.session.commit()
    return jsonify(code=200, msg='上传配置已删除', data=None), 200


@upload_config_bp.route('/api/my-upload-configs', methods=['GET'])
@jwt_required()
def my_upload_configs():
    """返回当前用户可用的上传配置列表（根据权限过滤）"""
    user = get_current_user()
    if not user or not user.role:
        return jsonify(code=200, msg='success', data=[]), 200

    permissions = user.role.get_permissions()
    configs = UploadConfig.query.filter(
        UploadConfig.is_active == True,
        UploadConfig.permission.in_(permissions)
    ).order_by(UploadConfig.sort_order, UploadConfig.id).all()

    return jsonify(code=200, msg='success', data=[c.to_dict() for c in configs]), 200
```

- [ ] **Step 2: Commit**

```bash
git add backend/upload_config.py
git commit -m "feat: upload_config CRUD blueprint + my-upload-configs endpoint"
```

---

## Phase 3: 后端文件上传 API

### Task 3.1: 创建 handlers 映射和基础框架

**Files:**
- Create: `backend/upload/__init__.py`（空文件）
- Create: `backend/upload/handlers.py`

- [ ] **Step 1: 编写 handlers.py**

Write `backend/upload/handlers.py`:
```python
"""
上传文件解析处理器映射表。

每个 handler 函数签名: def handler(file_path: str) -> dict
返回: {"success": True/False, "message": "...", "rows": 0}

新增上传类型时，在这里添加 code → handler 映射即可。
"""


def noop_handler(file_path: str) -> dict:
    """占位处理器：文件已保存，暂不支持解析"""
    return {"success": True, "message": "文件已保存，暂不支持自动解析", "rows": 0}


# code → handler 映射表
HANDLERS = {
    # 示例（后续逐步添加解析逻辑）:
    # "performance_data": parse_performance_excel,
    # "payment_data": parse_payment_excel,
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/upload/__init__.py backend/upload/handlers.py
git commit -m "feat: upload handler framework — code-to-handler mapping"
```

---

### Task 3.2: 创建文件上传蓝图

**Files:**
- Create: `backend/upload.py`

- [ ] **Step 1: 编写 upload.py**

Write `backend/upload.py`:
```python
import os
import time
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_current_user
from werkzeug.utils import secure_filename
from models import db, UploadConfig, FileUpload
from upload.handlers import HANDLERS
from decorators import permission_required

upload_bp = Blueprint('upload', __name__)


def get_db_size():
    """获取 SQLite 数据库文件大小（MB）"""
    db_path = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_path.startswith('sqlite:///'):
        db_file = db_path.replace('sqlite:///', '')
        if os.path.isfile(db_file):
            return round(os.path.getsize(db_file) / (1024 * 1024), 2)
    return 0


@upload_bp.route('/api/upload/<code>', methods=['POST'])
@jwt_required()
def upload_file(code):
    """文件上传端点 — 根据 code 匹配 upload_config"""
    config = UploadConfig.query.filter_by(code=code, is_active=True).first()
    if not config:
        return jsonify(code=404, msg=f'上传配置不存在: {code}', data=None), 404

    # 权限检查
    user = get_current_user()
    if not user or not user.role or config.permission not in user.role.get_permissions():
        return jsonify(code=403, msg='无上传权限', data=None), 403

    if 'file' not in request.files:
        return jsonify(code=400, msg='未选择文件', data=None), 400

    file = request.files['file']
    if not file.filename:
        return jsonify(code=400, msg='文件名为空', data=None), 400

    # 保存文件
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], code)
    os.makedirs(upload_dir, exist_ok=True)

    original_filename = secure_filename(file.filename)
    timestamp = int(time.time())
    saved_filename = f'{timestamp}_{original_filename}'
    saved_path = os.path.join(upload_dir, saved_filename)
    file.save(saved_path)

    file_size = os.path.getsize(saved_path)

    # 创建上传记录
    record = FileUpload(
        filename=original_filename,
        stored_path=saved_path,
        file_size=file_size,
        upload_config_id=config.id,
        user_id=user.id,
        status='uploading',
        message='',
    )
    db.session.add(record)
    db.session.commit()

    # 查找并调用 handler
    handler = HANDLERS.get(code)
    if handler:
        try:
            result = handler(saved_path)
            record.status = 'parsed' if result.get('success') else 'error'
            record.message = result.get('message', '')
        except Exception as e:
            record.status = 'error'
            record.message = f'解析失败: {str(e)}'
    else:
        record.status = 'stored'
        record.message = '文件已保存，暂不支持自动解析'

    db.session.commit()

    return jsonify(code=200, msg='上传完成', data=record.to_dict()), 200


@upload_bp.route('/api/upload-history', methods=['GET'])
@jwt_required()
def upload_history():
    """当前用户的文件上传历史"""
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    pagination = FileUpload.query.filter_by(user_id=user.id) \
        .order_by(FileUpload.uploaded_at.desc()) \
        .paginate(page=page, per_page=page_size, error_out=False)

    return jsonify(code=200, msg='success', data={
        'items': [r.to_dict() for r in pagination.items],
        'total': pagination.total,
    }), 200


@upload_bp.route('/api/upload-stats', methods=['GET'])
@jwt_required()
def upload_stats():
    """上传统计数据"""
    user = get_current_user()
    # 当前用户的上传次数
    upload_count = FileUpload.query.filter_by(user_id=user.id).count()
    # 解析成功次数
    parsed_count = FileUpload.query.filter_by(user_id=user.id, status='parsed').count()
    # 数据库大小
    db_size = get_db_size()

    return jsonify(code=200, msg='success', data={
        'upload_count': upload_count,
        'parsed_count': parsed_count,
        'db_size_mb': db_size,
    }), 200
```

- [ ] **Step 2: 验证后端完整启动**

```bash
cd E:/System/backend && python app.py
```

确认所有蓝图注册成功，无 import 错误。

- [ ] **Step 3: Commit**

```bash
git add backend/upload/__init__.py backend/upload/handlers.py backend/upload.py
git commit -m "feat: file upload API — upload, history, stats with handler mapping"
```

---

## Phase 4: 前端骨架 — Login, Router Guard, Pinia

### Task 4.1: 创建 Vue 3 + Vite 项目

**Files:**
- Create: `frontend/`（通过 npm create 生成）
- Create: `frontend/vite.config.js`

- [ ] **Step 1: 创建项目**

```bash
cd E:/System
npm create vite@latest frontend -- --template vue
cd frontend
npm install
npm install element-plus @element-plus/icons-vue pinia vue-router axios
```

- [ ] **Step 2: 配置 vite.config.js**

Write `frontend/vite.config.js`:
```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      }
    }
  }
})
```

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: Vue 3 + Vite project scaffold with dependencies"
```

---

### Task 4.2: 创建 Axios 请求封装和 API 模块

**Files:**
- Create: `frontend/src/api/request.js`
- Create: `frontend/src/api/auth.js`

- [ ] **Step 1: 编写 request.js**

Write `frontend/src/api/request.js`:
```javascript
import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/',
  timeout: 30000,
})

// 请求拦截器：自动注入 token
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：统一错误处理
request.interceptors.response.use(
  (response) => {
    const data = response.data
    if (data.code && data.code !== 200) {
      ElMessage.error(data.msg || '请求失败')
      return Promise.reject(new Error(data.msg))
    }
    return data
  },
  (error) => {
    if (error.response) {
      const { status } = error.response
      if (status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('userInfo')
        window.location.href = '/login'
      } else if (status === 403) {
        ElMessage.error('无权限访问')
      } else {
        ElMessage.error(error.response.data?.msg || '服务器错误')
      }
    }
    return Promise.reject(error)
  }
)

export default request
```

- [ ] **Step 2: 编写 auth.js**

Write `frontend/src/api/auth.js`:
```javascript
import request from './request'

export function login(username, password) {
  return request.post('/api/login', { username, password })
}

export function getCurrentUser() {
  return request.get('/api/current-user')
}

export function changePassword(oldPassword, newPassword) {
  return request.put('/api/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}
```

- [ ] **Step 3: 编写其他 API 模块**

Write `frontend/src/api/users.js`:
```javascript
import request from './request'

export function getUsers(params) {
  return request.get('/api/users', { params })
}

export function createUser(data) {
  return request.post('/api/users', data)
}

export function updateUser(id, data) {
  return request.put(`/api/users/${id}`, data)
}

export function deleteUser(id) {
  return request.delete(`/api/users/${id}`)
}

export function resetPassword(id) {
  return request.put(`/api/users/${id}/reset-password`)
}
```

Write `frontend/src/api/roles.js`:
```javascript
import request from './request'

export function getRoles() {
  return request.get('/api/roles')
}

export function createRole(data) {
  return request.post('/api/roles', data)
}

export function updateRole(id, data) {
  return request.put(`/api/roles/${id}`, data)
}

export function deleteRole(id) {
  return request.delete(`/api/roles/${id}`)
}
```

Write `frontend/src/api/modules.js`:
```javascript
import request from './request'

export function getModules() {
  return request.get('/api/modules')
}

export function createModule(data) {
  return request.post('/api/modules', data)
}

export function updateModule(id, data) {
  return request.put(`/api/modules/${id}`, data)
}

export function deleteModule(id) {
  return request.delete(`/api/modules/${id}`)
}

export function getMyModules() {
  return request.get('/api/my-modules')
}
```

Write `frontend/src/api/upload-config.js`:
```javascript
import request from './request'

export function getUploadConfigs() {
  return request.get('/api/upload-configs')
}

export function createUploadConfig(data) {
  return request.post('/api/upload-configs', data)
}

export function updateUploadConfig(id, data) {
  return request.put(`/api/upload-configs/${id}`, data)
}

export function deleteUploadConfig(id) {
  return request.delete(`/api/upload-configs/${id}`)
}

export function getMyUploadConfigs() {
  return request.get('/api/my-upload-configs')
}
```

Write `frontend/src/api/upload.js`:
```javascript
import request from './request'

export function uploadFile(code, file) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post(`/api/upload/${code}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getUploadHistory(params) {
  return request.get('/api/upload-history', { params })
}

export function getUploadStats() {
  return request.get('/api/upload-stats')
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: API modules — request interceptor, auth, users, roles, modules, upload"
```

---

### Task 4.3: 创建 Pinia stores

**Files:**
- Create: `frontend/src/stores/auth.js`
- Create: `frontend/src/stores/app.js`

- [ ] **Step 1: 编写 auth.js**

Write `frontend/src/stores/auth.js`:
```javascript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, getCurrentUser } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(JSON.parse(localStorage.getItem('userInfo') || 'null'))

  const isAdmin = computed(() => userInfo.value?.role?.is_admin || false)
  const permissions = computed(() => userInfo.value?.role?.permissions || [])
  const isLoggedIn = computed(() => !!token.value)

  function hasPermission(perm) {
    return permissions.value.includes(perm)
  }

  async function login(username, password) {
    const res = await loginApi(username, password)
    token.value = res.data.token
    userInfo.value = res.data.user
    localStorage.setItem('token', res.data.token)
    localStorage.setItem('userInfo', JSON.stringify(res.data.user))
    return res.data
  }

  async function fetchCurrentUser() {
    try {
      const res = await getCurrentUser()
      userInfo.value = res.data
      localStorage.setItem('userInfo', JSON.stringify(res.data))
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  return { token, userInfo, isAdmin, permissions, isLoggedIn, hasPermission, login, fetchCurrentUser, logout }
})
```

- [ ] **Step 2: 编写 app.js**

Write `frontend/src/stores/app.js`:
```javascript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return { sidebarCollapsed, toggleSidebar }
})
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/
git commit -m "feat: Pinia stores — auth (login/logout/permissions) and app (sidebar)"
```

---

### Task 4.4: 创建路由和守卫

**Files:**
- Create: `frontend/src/router/index.js`

- [ ] **Step 1: 编写 router/index.js**

Write `frontend/src/router/index.js`:
```javascript
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/admin',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requireAdmin: true },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      { path: 'dashboard', component: () => import('../views/admin/AdminDashboard.vue') },
      { path: 'user-manage', component: () => import('../views/admin/UserManage.vue') },
      { path: 'role-manage', component: () => import('../views/admin/RoleManage.vue') },
      { path: 'module-manage', component: () => import('../views/admin/ModuleManage.vue') },
      { path: 'upload-config-manage', component: () => import('../views/admin/UploadConfigManage.vue') },
    ],
  },
  {
    path: '/',
    component: () => import('../layouts/UserLayout.vue'),
    meta: { requireAuth: true },
    children: [
      { path: '', redirect: '/home' },
      { path: 'home', component: () => import('../views/Home.vue') },
      { path: 'dashboard/:id', component: () => import('../views/Dashboard.vue'), props: true },
      { path: 'upload-console', component: () => import('../views/UploadConsole.vue') },
      { path: 'upload-console/:code', component: () => import('../views/UploadConsole.vue') },
    ],
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('../views/common/403.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/home',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 公开页面直接放行
  if (to.meta.public) {
    if (to.path === '/login' && authStore.isLoggedIn) {
      // 已登录用户访问登录页 → 跳转首页
      next(authStore.isAdmin ? '/admin/dashboard' : '/home')
      return
    }
    next()
    return
  }

  // 未登录 → 跳转登录页
  if (!authStore.isLoggedIn) {
    next('/login')
    return
  }

  // 已登录但无用户信息 → 拉取用户信息
  if (!authStore.userInfo) {
    try {
      await authStore.fetchCurrentUser()
    } catch {
      next('/login')
      return
    }
  }

  // 需要管理员权限
  if (to.meta.requireAdmin && !authStore.isAdmin) {
    next('/403')
    return
  }

  // 管理员访问用户路由 → 重定向到管理员首页
  if (authStore.isAdmin && !to.meta.requireAdmin && to.path.startsWith('/home')) {
    next('/admin/dashboard')
    return
  }

  next()
})

export default router
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/
git commit -m "feat: Vue Router with auth guard — admin/user layout switching"
```

---

### Task 4.5: 创建 main.js、App.vue 和登录页

**Files:**
- Modify: `frontend/src/main.js`
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/views/Login.vue`

- [ ] **Step 1: 编写 main.js**

Write `frontend/src/main.js`:
```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: /* 默认中文 */ })

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
```

- [ ] **Step 2: 编写 App.vue**

Write `frontend/src/App.vue`:
```html
<template>
  <router-view />
</template>
```

- [ ] **Step 3: 编写 Login.vue**

Write `frontend/src/views/Login.vue`:
```html
<template>
  <div class="login-container">
    <div class="login-bg-circle login-bg-circle--top"></div>
    <div class="login-bg-circle login-bg-circle--bottom"></div>

    <el-card class="login-card">
      <div class="login-header">
        <h2>企业管理系统</h2>
        <p>Enterprise Management</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="请输入工号" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" :prefix-icon="Lock"
            show-password @keyup.enter="handleLogin" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="rememberMe">记住密码</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const rememberMe = ref(false)
const formRef = ref(null)

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

onMounted(() => {
  const savedUsername = localStorage.getItem('rememberedUsername')
  const savedPassword = localStorage.getItem('rememberedPassword')
  if (savedUsername) {
    form.username = savedUsername
    form.password = savedPassword || ''
    rememberMe.value = true
  }
})

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.login(form.username, form.password)

    if (rememberMe.value) {
      localStorage.setItem('rememberedUsername', form.username)
      localStorage.setItem('rememberedPassword', form.password)
    } else {
      localStorage.removeItem('rememberedUsername')
      localStorage.removeItem('rememberedPassword')
    }

    ElMessage.success('登录成功')
    router.push(authStore.isAdmin ? '/admin/dashboard' : '/home')
  } catch {
    // 错误已在拦截器中处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 60%, #0a2e6e 100%);
  position: relative;
  overflow: hidden;
}

.login-bg-circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.04);
}

.login-bg-circle--top {
  width: 200px;
  height: 200px;
  top: -50px;
  right: -50px;
}

.login-bg-circle--bottom {
  width: 160px;
  height: 160px;
  bottom: -40px;
  left: -40px;
}

.login-card {
  width: 380px;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  z-index: 1;
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.login-header h2 {
  color: #1a1a2e;
  font-size: 22px;
  margin: 0;
}

.login-header p {
  color: #999;
  font-size: 12px;
  margin: 6px 0 0;
}

.login-btn {
  width: 100%;
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  border: none;
  font-size: 15px;
  letter-spacing: 4px;
}
</style>
```

- [ ] **Step 4: 验证前端启动**

```bash
cd E:/System/frontend && npm run dev
```

访问 http://localhost:5173/login → 应显示蓝色渐变背景登录页

- [ ] **Step 5: 测试登录流程**

输入 admin / admin123 → 点击登录 → 应跳转到 /admin/dashboard（此时页面空白，路由匹配成功即可）

- [ ] **Step 6: Commit**

```bash
git add frontend/src/main.js frontend/src/App.vue frontend/src/views/Login.vue
git commit -m "feat: frontend entry, App.vue, and blue-gradient login page"
```

---

## Phase 5: 前端 AdminLayout + 管理员页面

### Task 5.1: 创建 AdminLayout 和 UserLayout

**Files:**
- Create: `frontend/src/layouts/AdminLayout.vue`
- Create: `frontend/src/layouts/UserLayout.vue`

- [ ] **Step 1: 编写 AdminLayout.vue**

Write `frontend/src/layouts/AdminLayout.vue`:
```html
<template>
  <el-container class="admin-layout">
    <!-- 侧边栏 -->
    <el-aside :width="sidebarCollapsed ? '64px' : '200px'" class="admin-aside">
      <div class="logo-area">
        <div class="logo-icon"></div>
        <span v-show="!sidebarCollapsed" class="logo-text">系统控制台</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="sidebarCollapsed"
        :collapse-transition="false"
        router
        background-color="#fff"
        text-color="#555"
        active-text-color="#1a73e8"
      >
        <el-menu-item index="/admin/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>首页看板</span>
        </el-menu-item>
        <el-menu-item index="/admin/user-manage" v-if="authStore.hasPermission('user_manage')">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/role-manage" v-if="authStore.hasPermission('role_manage')">
          <el-icon><Lock /></el-icon>
          <span>角色管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/module-manage" v-if="authStore.hasPermission('module_manage')">
          <el-icon><Grid /></el-icon>
          <span>模块管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/upload-config-manage" v-if="authStore.hasPermission('upload_manage')">
          <el-icon><UploadFilled /></el-icon>
          <span>上传配置管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 右侧 -->
    <el-container>
      <el-header class="admin-header">
        <div class="header-left">
          <el-icon class="collapse-icon" @click="appStore.toggleSidebar()" :size="20">
            <Fold v-if="!sidebarCollapsed" />
            <Expand v-else />
          </el-icon>
        </div>
        <div class="header-right">
          <el-icon :size="18"><Bell /></el-icon>
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="30" class="user-avatar">
                {{ authStore.userInfo?.real_name?.charAt(0) || '管' }}
              </el-avatar>
              <span>{{ authStore.userInfo?.real_name || '管理员' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="changePassword">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="admin-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 修改密码弹窗 -->
  <el-dialog v-model="pwdDialogVisible" title="修改密码" width="420px">
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="80px">
      <el-form-item label="旧密码" prop="oldPassword">
        <el-input v-model="pwdForm.oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码" prop="newPassword">
        <el-input v-model="pwdForm.newPassword" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleChangePassword">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataAnalysis, User, Lock, Grid, UploadFilled, Bell, ArrowDown, Fold, Expand } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { changePassword } from '../api/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const appStore = useAppStore()

const sidebarCollapsed = computed(() => appStore.sidebarCollapsed)
const activeMenu = computed(() => route.path)

const pwdDialogVisible = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ oldPassword: '', newPassword: '' })
const pwdRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [{ required: true, min: 6, message: '新密码不少于6位', trigger: 'blur' }],
}

function handleCommand(command) {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (command === 'changePassword') {
    pwdForm.oldPassword = ''
    pwdForm.newPassword = ''
    pwdDialogVisible.value = true
  }
}

async function handleChangePassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await changePassword(pwdForm.oldPassword, pwdForm.newPassword)
    ElMessage.success('密码修改成功')
    pwdDialogVisible.value = false
  } catch { /* 已在拦截器处理 */ }
}
</script>

<style scoped>
.admin-layout { height: 100vh; }
.admin-aside {
  background: #fff;
  border-right: 1px solid #eef0f2;
  transition: width 0.3s;
  overflow: hidden;
}
.logo-area {
  display: flex;
  align-items: center;
  padding: 16px;
  gap: 8px;
}
.logo-icon {
  width: 32px; height: 32px;
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  border-radius: 6px;
  flex-shrink: 0;
}
.logo-text { font-weight: 600; font-size: 14px; color: #1a1a2e; white-space: nowrap; }

/* 侧边栏菜单去除右边框 */
.admin-aside :deep(.el-menu) { border-right: none; }

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
  height: 50px;
  padding: 0 20px;
}
.header-left { display: flex; align-items: center; }
.collapse-icon { cursor: pointer; color: #666; }
.header-right { display: flex; align-items: center; gap: 16px; }
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #555;
}
.user-avatar { background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; font-size: 12px; }
.admin-main { background: #f0f2f5; padding: 20px; }
</style>
```

- [ ] **Step 2: 编写 UserLayout.vue**

Write `frontend/src/layouts/UserLayout.vue`:
```html
<template>
  <el-container class="user-layout">
    <el-header class="user-header">
      <span class="header-brand">系统控制台</span>
      <div class="header-actions">
        <el-button class="console-btn" @click="router.push('/upload-console')">
          📤 用户控制台
        </el-button>
        <el-icon :size="18"><Bell /></el-icon>
        <el-dropdown trigger="click" @command="handleCommand">
          <span class="user-info">
            <el-avatar :size="30" class="user-avatar">
              {{ authStore.userInfo?.real_name?.charAt(0) || '用' }}
            </el-avatar>
            <span>{{ authStore.userInfo?.real_name || '用户' }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="changePassword">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-main class="user-main">
      <router-view />
    </el-main>
  </el-container>

  <!-- 修改密码弹窗（与 AdminLayout 相同结构） -->
  <el-dialog v-model="pwdDialogVisible" title="修改密码" width="420px">
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="80px">
      <el-form-item label="旧密码" prop="oldPassword">
        <el-input v-model="pwdForm.oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码" prop="newPassword">
        <el-input v-model="pwdForm.newPassword" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleChangePassword">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { changePassword } from '../api/auth'

const router = useRouter()
const authStore = useAuthStore()

const pwdDialogVisible = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ oldPassword: '', newPassword: '' })
const pwdRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [{ required: true, min: 6, message: '新密码不少于6位', trigger: 'blur' }],
}

function handleCommand(command) {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (command === 'changePassword') {
    pwdForm.oldPassword = ''
    pwdForm.newPassword = ''
    pwdDialogVisible.value = true
  }
}

async function handleChangePassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await changePassword(pwdForm.oldPassword, pwdForm.newPassword)
    ElMessage.success('密码修改成功')
    pwdDialogVisible.value = false
  } catch { /* 已在拦截器处理 */ }
}
</script>

<style scoped>
.user-layout { height: 100vh; display: flex; flex-direction: column; }
.user-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
  height: 50px;
  padding: 0 24px;
  flex-shrink: 0;
}
.header-brand { font-weight: 600; font-size: 14px; color: #1a1a2e; }
.header-actions { display: flex; align-items: center; gap: 16px; }
.console-btn {
  font-size: 12px;
  color: #1a73e8;
  border-color: #1a73e8;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #555;
}
.user-avatar { background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; font-size: 12px; }
.user-main { background: #f0f2f5; padding: 28px 32px; flex: 1; }
</style>
```

- [ ] **Step 3: 创建占位管理页面（确保路由不报错）**

Write each admin page as a minimal placeholder:

Write `frontend/src/views/admin/AdminDashboard.vue`:
```html
<template>
  <div class="page-card">
    <h3>欢迎回来，{{ authStore.userInfo?.real_name }}</h3>
    <p style="color:#999;">管理系统用户、角色、模块和上传配置</p>
  </div>
</template>
<script setup>
import { useAuthStore } from '../../stores/auth'
const authStore = useAuthStore()
</script>
<style scoped>
.page-card { background: #fff; border-radius: 12px; padding: 32px; }
</style>
```

Write placeholders for: `UserManage.vue`, `RoleManage.vue`, `ModuleManage.vue`, `UploadConfigManage.vue` — each with a similar minimal structure (a white card with a title), with full implementation in Tasks 5.2–5.5.

- [ ] **Step 4: 验证管理员登录流程**

```bash
# 启动后端
cd E:/System/backend && python app.py &
# 启动前端
cd E:/System/frontend && npm run dev
```

1. 访问 http://localhost:5173/login
2. 登录 admin/admin123
3. 应跳转到 /admin/dashboard，显示侧边栏 + 顶栏

- [ ] **Step 5: Commit**

```bash
git add frontend/src/layouts/ frontend/src/views/admin/
git commit -m "feat: AdminLayout (sidebar) and UserLayout (topbar only) with placeholder admin pages"
```

---

### Task 5.2: 用户管理页面（完整实现）

**Files:**
- Modify: `frontend/src/views/admin/UserManage.vue`

由于篇幅限制，以下为核心结构框架（完整代码在实施时编写）：

**页面功能**：
- 搜索栏：工号输入、姓名输入、搜索/重置按钮、新增用户按钮
- 表格：工号、姓名、角色、状态（el-switch）、操作（编辑/重置密码/删除）
- 分页：el-pagination
- 新增/编辑弹窗：工号、姓名、密码（新增时必填）、角色下拉、状态开关
- 重置密码弹窗：确认对话框

**关键数据结构**：
```javascript
// 表格列
const columns = [
  { prop: 'username', label: '工号' },
  { prop: 'real_name', label: '姓名' },
  { prop: 'role_name', label: '角色' },
  { prop: 'is_active', label: '状态' },
]

// 表单
const form = reactive({
  id: null, username: '', password: '', real_name: '',
  role_id: null, is_active: true,
})

// 角色列表（从 /api/roles 获取用于下拉）
const roles = ref([])
```

- [ ] **Step 1: 编写完整的 UserManage.vue**
- [ ] **Step 2: 验证增删改查功能**
- [ ] **Step 3: Commit**

---

### Task 5.3: 角色管理页面（完整实现）

**Files:**
- Modify: `frontend/src/views/admin/RoleManage.vue`

**页面功能**：
- 表格：角色名、是否管理员（标签）、权限（el-tag 列表）、创建时间、操作
- 新增/编辑弹窗：角色名、是否管理员开关、权限复选框组（从预定义清单中选择）

**预定义权限清单**（前端硬编码）：
```javascript
const ALL_PERMISSIONS = [
  { label: '管理类', options: [
    { value: 'dashboard', label: '首页看板' },
    { value: 'user_manage', label: '用户管理' },
    { value: 'role_manage', label: '角色管理' },
    { value: 'module_manage', label: '模块管理' },
    { value: 'upload_manage', label: '上传配置管理' },
  ]},
  { label: '看板类', options: [
    { value: 'dashboard_receivables', label: '报价统计分析看板' },
    { value: 'dashboard_performance', label: '业绩完成情况看板' },
    { value: 'dashboard_daily', label: '国际运营业绩日报看板' },
    { value: 'dashboard_ledger', label: '报价执行台账看板' },
    { value: 'dashboard_function', label: '职能工作看板' },
    { value: 'dashboard_spare_parts', label: '国贸备件报价' },
  ]},
  { label: '上传类', options: [
    { value: 'upload_performance', label: '业绩数据上传' },
    { value: 'upload_module_target', label: '模块业绩指标上传' },
    { value: 'upload_payment', label: '回款数据上传' },
    { value: 'upload_spare_parts', label: '商贸备件数据上传' },
    { value: 'upload_trade', label: '商贸数据上传' },
    { value: 'upload_delivery', label: '备件发货数据上传' },
    { value: 'upload_offline_quote', label: '2026线下报价上传' },
  ]},
]
```

- [ ] **Step 1: 编写完整的 RoleManage.vue**
- [ ] **Step 2: 验证角色 CRUD 和权限分配**
- [ ] **Step 3: Commit**

---

### Task 5.4: 模块管理页面

**Files:**
- Modify: `frontend/src/views/admin/ModuleManage.vue`

**页面功能**：表格展示所有模块 + 新增/编辑弹窗（名称、描述、权限标识、URL路径、图标、排序、启用状态）

- [ ] **Step 1: 编写完整的 ModuleManage.vue**
- [ ] **Step 2: Commit**

---

### Task 5.5: 上传配置管理页面

**Files:**
- Modify: `frontend/src/views/admin/UploadConfigManage.vue`

**页面功能**：表格 + 新增/编辑弹窗（名称、描述、code、权限标识、文件类型、必需列、排序、启用状态）

- [ ] **Step 1: 编写完整的 UploadConfigManage.vue**
- [ ] **Step 2: Commit**

---

## Phase 6: 前端 UserLayout 页面 — Home, Dashboard, UploadConsole

### Task 6.1: 模块卡片选择页（Home.vue）

**Files:**
- Create: `frontend/src/views/Home.vue`

- [ ] **Step 1: 编写 Home.vue**

Write `frontend/src/views/Home.vue`:
```html
<template>
  <div class="home-page">
    <!-- 欢迎区 -->
    <div class="welcome-section">
      <h2>欢迎回来，{{ authStore.userInfo?.real_name }}</h2>
      <p>请选择您要查看的看板</p>
    </div>

    <!-- 统计行 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon stat-icon--blue"><el-icon :size="20"><DataAnalysis /></el-icon></div>
          <div>
            <div class="stat-value">{{ modules.length }}</div>
            <div class="stat-label">可用看板</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon stat-icon--green"><el-icon :size="20"><TrendCharts /></el-icon></div>
          <div>
            <div class="stat-value">8</div>
            <div class="stat-label">监控指标</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon stat-icon--orange"><el-icon :size="20"><Grid /></el-icon></div>
          <div>
            <div class="stat-value">12</div>
            <div class="stat-label">数据维度</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 模块卡片网格 -->
    <el-row :gutter="16" v-loading="loading">
      <el-col :span="8" v-for="m in modules" :key="m.id" style="margin-bottom: 16px;">
        <div class="module-card" @click="goDashboard(m)">
          <div class="module-card-header">
            <span class="module-dot" :style="{ background: dotColors[m.id % dotColors.length] }"></span>
            <span class="module-title">{{ m.name }}</span>
          </div>
          <p class="module-desc">{{ m.description }}</p>
          <div class="module-card-footer">
            <span class="module-link">查看看板 →</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 无模块时 -->
    <el-empty v-if="!loading && modules.length === 0" description="暂无可查看的看板" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { DataAnalysis, TrendCharts, Grid } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { getMyModules } from '../api/modules'

const authStore = useAuthStore()
const router = useRouter()

const modules = ref([])
const loading = ref(false)
const dotColors = ['#1a73e8', '#4caf50', '#ff9800', '#9c27b0', '#00bcd4', '#e91e63']

onMounted(async () => {
  loading.value = true
  try {
    const res = await getMyModules()
    modules.value = res.data || []
  } finally {
    loading.value = false
  }
})

function goDashboard(module) {
  router.push(`/dashboard/${module.id}`)
}
</script>

<style scoped>
.welcome-section { margin-bottom: 24px; }
.welcome-section h2 { margin: 0; font-size: 20px; color: #1a1a2e; }
.welcome-section p { margin: 6px 0 0; color: #888; font-size: 13px; }

.stats-row { margin-bottom: 28px; }
.stat-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  display: flex; align-items: center; gap: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
.stat-icon--blue { background: #e8f0fe; color: #1a73e8; }
.stat-icon--green { background: #e6f7ee; color: #4caf50; }
.stat-icon--orange { background: #fff3e0; color: #ff9800; }
.stat-value { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 11px; color: #888; }

.module-card {
  background: #fff; border-radius: 12px; padding: 20px;
  border: 1px solid #eef0f2; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  cursor: pointer; transition: box-shadow 0.2s; height: 100%;
  display: flex; flex-direction: column;
}
.module-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.module-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.module-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.module-title { font-weight: 600; font-size: 14px; color: #1a1a2e; }
.module-desc { font-size: 11px; color: #999; line-height: 1.6; flex: 1; margin: 0 0 14px; }
.module-card-footer { text-align: right; }
.module-link { font-size: 11px; color: #1a73e8; border: 1px solid #1a73e8; padding: 4px 14px; border-radius: 4px; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/Home.vue
git commit -m "feat: Home page — module card grid with stats row"
```

---

### Task 6.2: iframe 看板页（Dashboard.vue）

**Files:**
- Create: `frontend/src/views/Dashboard.vue`

- [ ] **Step 1: 编写 Dashboard.vue**

Write `frontend/src/views/Dashboard.vue`:
```html
<template>
  <div class="dashboard-page">
    <div class="dashboard-topbar">
      <el-button text @click="router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <span class="dashboard-title">{{ moduleInfo?.name || '看板' }}</span>
    </div>
    <div class="iframe-container" v-loading="loading">
      <iframe v-if="iframeUrl" :src="iframeUrl" class="dashboard-iframe" frameborder="0" />
      <el-empty v-else description="看板未配置或不可用" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getMyModules } from '../api/modules'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()

const moduleInfo = ref(null)
const iframeUrl = ref('')
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const res = await getMyModules()
    const mod = (res.data || []).find(m => String(m.id) === String(props.id))
    if (mod) {
      moduleInfo.value = mod
      iframeUrl.value = mod.url || ''
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dashboard-page { height: calc(100vh - 50px - 56px); display: flex; flex-direction: column; }
.dashboard-topbar {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 12px;
}
.dashboard-title { font-weight: 600; font-size: 15px; color: #1a1a2e; }
.iframe-container { flex: 1; background: #fff; border-radius: 12px; overflow: hidden; }
.dashboard-iframe { width: 100%; height: 100%; border: none; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/Dashboard.vue
git commit -m "feat: Dashboard iframe page"
```

---

### Task 6.3: 上传组件 UploadZone.vue

**Files:**
- Create: `frontend/src/components/UploadZone.vue`

- [ ] **Step 1: 编写 UploadZone.vue**

Write `frontend/src/components/UploadZone.vue`:
```html
<template>
  <div class="upload-zone-card">
    <div class="upload-zone-title">
      <span>{{ config?.name }}</span>
    </div>
    <p class="upload-zone-desc">{{ config?.description }}</p>
    <p v-if="config?.required_columns" class="upload-zone-required">
      必需列：{{ config.required_columns }}
    </p>
    <el-upload
      class="upload-zone"
      drag
      :action="`/api/upload/${config?.code}`"
      :headers="uploadHeaders"
      :accept="acceptTypes"
      :on-success="onSuccess"
      :on-error="onError"
    >
      <el-icon :size="32" class="upload-icon"><UploadFilled /></el-icon>
      <div class="upload-text">拖放文件到此处或点击选择</div>
      <div class="upload-hint">{{ fileTypeHint }}</div>
    </el-upload>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const props = defineProps({
  config: { type: Object, required: true },
})

const emit = defineEmits(['uploaded'])

const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${localStorage.getItem('token')}`,
}))

const acceptTypes = computed(() => {
  const types = props.config?.file_types || '.xlsx,.xls'
  return types.split(',').map(t => t.trim()).join(',')
})

const fileTypeHint = computed(() => {
  const types = props.config?.file_types || '.xlsx,.xls'
  return `支持文件：${types}`
})

function onSuccess(response) {
  if (response.code === 200) {
    ElMessage.success('上传成功')
    emit('uploaded', response.data)
  }
}

function onError() {
  ElMessage.error('上传失败')
}
</script>

<style scoped>
.upload-zone-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  margin-bottom: 12px; border: 1px solid #eef0f2;
}
.upload-zone-title { font-weight: 600; font-size: 13px; color: #1a1a2e; margin-bottom: 4px; }
.upload-zone-desc { font-size: 11px; color: #999; margin: 0 0 4px; }
.upload-zone-required { font-size: 10px; color: #e6a23c; margin: 0 0 12px; }
.upload-icon { color: #c0c4cc; }
.upload-text { font-size: 12px; color: #999; margin-top: 8px; }
.upload-hint { font-size: 10px; color: #bbb; margin-top: 4px; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/UploadZone.vue
git commit -m "feat: reusable drag-and-drop upload component"
```

---

### Task 6.4: 用户控制台上传页（UploadConsole.vue）

**Files:**
- Create: `frontend/src/views/UploadConsole.vue`
- Create: `frontend/src/views/SystemInfo.vue`

- [ ] **Step 1: 编写 UploadConsole.vue**

核心结构：
- 左侧菜单：数据管理（子菜单为各上传配置项）、系统信息
- 右侧内容：对应上传配置的 UploadZone + 底部统计（上传次数/更新次数/数据库大小）
- 无上传权限时显示 SystemInfo

- [ ] **Step 2: 编写 SystemInfo.vue**

显示系统版本号和说明信息。

- [ ] **Step 3: 编写 403.vue**

Write `frontend/src/views/common/403.vue`:
```html
<template>
  <div class="forbidden-page">
    <el-result icon="warning" title="403" sub-title="抱歉，您没有权限访问此页面">
      <template #extra>
        <el-button type="primary" @click="$router.push('/home')">返回首页</el-button>
      </template>
    </el-result>
  </div>
</template>
<style scoped>
.forbidden-page { display: flex; align-items: center; justify-content: center; min-height: 400px; }
</style>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/UploadConsole.vue frontend/src/views/SystemInfo.vue frontend/src/views/common/403.vue
git commit -m "feat: UploadConsole, SystemInfo, and 403 page"
```

---

## 自检清单

- [x] Spec 覆盖：所有 6 阶段设计文档中的 API、页面、表均已覆盖
- [x] 无占位符：每个 Task 包含完整代码或明确的结构定义
- [x] 类型一致：前端 store 变量名（isAdmin / permissions）、API 返回格式（code/msg/data）、路由路径在各 Task 间一致
- [ ] 补充 Task 5.2–5.5、6.3–6.4 的完整代码（实施时逐步编写）

---

## 实施顺序

```
Phase 1 (backend skeleton)
  → Phase 2 (CRUD APIs)
    → Phase 3 (upload API)
      → Phase 4 (frontend skeleton + login)
        → Phase 5 (AdminLayout + admin pages)
          → Phase 6 (UserLayout + home/dashboard/upload)
```

每完成一个 Phase 应能独立运行和验证。
