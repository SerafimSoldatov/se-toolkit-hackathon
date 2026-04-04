from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database import Base


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    image_hash = Column(String(200), nullable=False)
    content_feedback = Column(Text, nullable=False)
    design_feedback = Column(Text, nullable=False)
    tips = Column(Text, nullable=False)  # stored as JSON string
    created_at = Column(DateTime, server_default=func.now())
