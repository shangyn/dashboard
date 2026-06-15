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
