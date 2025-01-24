# Define the Token model
from sqlalchemy import Column, String, Text


class Token(Base):
    __tablename__ = "tokens"
    user_id = Column(String, primary_key=True, index=True)
    access_token = Column(Text, nullable=False)
    linkedin_urn = Column(String, nullable=False)  # Added field