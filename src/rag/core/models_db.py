from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey

from .db import Base

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer,primary_key=True)
    name = Column(String, unique=True)
    created_at = Column(DateTime, server_default=func.now())

class Documents(Base):
    __tablename__ = "documents"
    id = Column(Integer,primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    gdrive_id = Column(String, unique=True)
    filename = Column(String)
    file_hash = Column(String)
    ingested_at = Column(DateTime, server_default=func.now())