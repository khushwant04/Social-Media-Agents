# routes/linkedin_post.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
# Import internal dependencies
from app.services.linkedin_agent import LinkedInAgent
from app.db.config import get_db

# Initialize router
router = APIRouter(prefix="/linkedin", tags=["linkedin"])
logger = logging.getLogger(__name__)

def get_linkedin_agent(db: Session = Depends(get_db)):
    return LinkedInAgent.from_environment(db)

@router.post("/post")
async def create_linkedin_post(
    user_id: str,
    query: str,
    agent: LinkedInAgent = Depends(get_linkedin_agent)
):
    """Create and publish LinkedIn post"""
    try:
        result = agent.research_and_post(
            user_id=user_id,
            query=query,
            enable_human_review=False
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))