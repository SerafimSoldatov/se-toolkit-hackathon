import json
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    """Presentation analysis record."""
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    presentation_hash = Column(String, nullable=False, index=True)
    original_feedback = Column(Text, nullable=True)  # JSON string
    improved_feedback = Column(Text, nullable=True)  # JSON string
    priority = Column(String, nullable=True)  # visual/concise/colorful/clear/imitate
    reference_presentation_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "presentation_hash": self.presentation_hash,
            "original_feedback": json.loads(self.original_feedback) if self.original_feedback else None,
            "improved_feedback": json.loads(self.improved_feedback) if self.improved_feedback else None,
            "priority": self.priority,
            "reference_presentation_hash": self.reference_presentation_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
