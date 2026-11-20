"""Persistent state for the business assistant."""
import json
import uuid
from datetime import datetime

from models import db


def _dump_json(value, fallback):
    if value in (None, ''):
        return fallback
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return fallback


def _load_json(value, fallback):
    if not value:
        return fallback
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return loaded if isinstance(loaded, type(fallback)) else fallback


def _format_time(value):
    return value.strftime('%Y-%m-%d %H:%M:%S') if value else ''


class BusinessAssistantSetting(db.Model):
    """Single-row global switch controlled by administrators."""

    __tablename__ = 'ba_setting'

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    updated_by = db.Column(db.Integer, nullable=True)
    updated_by_name = db.Column(db.String(50), default='')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'enabled': bool(self.enabled),
            'updated_by_name': self.updated_by_name or '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
        }


class BusinessAssistantConversation(db.Model):
    """A user-owned assistant conversation and its short-term entities."""

    __tablename__ = 'ba_conversation'

    id = db.Column(db.String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    title = db.Column(db.String(120), default='')
    summary = db.Column(db.String(500), default='')
    last_entities = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def get_last_entities(self):
        return _load_json(self.last_entities, {})

    def set_last_entities(self, value):
        self.last_entities = _dump_json(value, '{}')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title or '',
            'summary': self.summary or '',
            'last_entities': self.get_last_entities(),
            'created_at': _format_time(self.created_at),
            'updated_at': _format_time(self.updated_at),
        }


class BusinessAssistantMessage(db.Model):
    """One persisted turn in an assistant conversation."""

    __tablename__ = 'ba_message'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(db.String(36), index=True, nullable=False)
    role = db.Column(db.String(16), nullable=False)  # user / assistant
    content = db.Column(db.Text, default='')
    result_summary = db.Column(db.Text, default='{}')
    intent = db.Column(db.String(50), default='')
    trace_id = db.Column(db.String(32), index=True, default='')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    def get_result_summary(self):
        return _load_json(self.result_summary, {})

    def set_result_summary(self, value):
        self.result_summary = _dump_json(value, '{}')

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content or '',
            'result_summary': self.get_result_summary(),
            'intent': self.intent or '',
            'trace_id': self.trace_id or '',
            'created_at': _format_time(self.created_at),
        }


class BusinessAssistantQueryLog(db.Model):
    """Audit record for every assistant request, including failures."""

    __tablename__ = 'ba_query_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    trace_id = db.Column(db.String(32), unique=True, index=True, nullable=False)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    username = db.Column(db.String(80), default='')
    conversation_id = db.Column(db.String(36), index=True, default='')
    question = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='success')  # success / needs_input / unsupported / error
    failure_code = db.Column(db.String(50), default='')
    failure_reason = db.Column(db.Text, default='')
    action = db.Column(db.String(50), default='')
    intent_source = db.Column(db.String(20), default='')  # model / rule / fallback
    model_enabled = db.Column(db.Boolean, default=False)
    duration_ms = db.Column(db.Integer, default=0)
    scope_label = db.Column(db.String(50), default='')
    result_summary = db.Column(db.Text, default='{}')
    steps = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    def get_result_summary(self):
        return _load_json(self.result_summary, {})

    def set_result_summary(self, value):
        self.result_summary = _dump_json(value, '{}')

    def get_steps(self):
        return _load_json(self.steps, [])

    def set_steps(self, value):
        self.steps = _dump_json(value, '[]')

    def to_dict(self):
        return {
            'id': self.id,
            'trace_id': self.trace_id,
            'user_id': self.user_id,
            'username': self.username or '',
            'conversation_id': self.conversation_id or '',
            'question': self.question or '',
            'status': self.status or '',
            'failure_code': self.failure_code or '',
            'failure_reason': self.failure_reason or '',
            'action': self.action or '',
            'intent_source': self.intent_source or '',
            'model_enabled': bool(self.model_enabled),
            'duration_ms': int(self.duration_ms or 0),
            'scope_label': self.scope_label or '',
            'result_summary': self.get_result_summary(),
            'steps': self.get_steps(),
            'created_at': _format_time(self.created_at),
        }
