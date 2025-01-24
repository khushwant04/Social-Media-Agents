import os
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class LinkedInToken(Base):
    __tablename__ = "linkedin_tokens"
    user_id = Column(String, primary_key=True, index=True)
    access_token = Column(Text, nullable=False)
    linkedin_urn = Column(String, nullable=False)

# Define the Token model
class TwitterToken(Base):
    __tablename__ = "twitter_tokens"
    user_id = Column(String, primary_key=True, index=True)
    access_token = Column(Text, nullable=False)
    x_user_id = Column(String, nullable=False)  # Added field

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()