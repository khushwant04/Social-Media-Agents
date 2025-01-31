from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging

# Import internal dependencies
from app.services.linkedin_agent import LinkedInAgent
from app.db.config import get_db

# Initialize router
router = APIRouter(prefix="/linkedin", tags=["linkedin"])
logger = logging.getLogger(__name__)

class LinkedInPostRequest(BaseModel):
    user_id: str
    query: str

def get_linkedin_agent(db: Session = Depends(get_db)):
    return LinkedInAgent.from_environment(db)

@router.post("/post")
async def create_linkedin_post(
    request: LinkedInPostRequest,
    agent: LinkedInAgent = Depends(get_linkedin_agent)
):
    """Create and publish LinkedIn post"""
    try:
        result = agent.research_and_post(
            user_id=request.user_id,
            query=request.query,
            enable_human_review=False
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
