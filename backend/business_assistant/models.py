"""Persistent settings for the business assistant."""
from datetime import datetime

from models import db


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
