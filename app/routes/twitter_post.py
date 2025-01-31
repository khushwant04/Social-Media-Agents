from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging
from app.services.twitter_agent import SocialMediaAgent  # Your agent class
from app.db.config import get_db  # Shared database dependency

router = APIRouter(prefix="/twitter", tags=["twitter"])

# Configure logging
logger = logging.getLogger(__name__)

class TwitterPostRequest(BaseModel):
    user_id: str
    query: str

def get_twitter_agent(db: Session = Depends(get_db)):
    return SocialMediaAgent.from_environment(db)

@router.post("/post")
async def create_twitter_post(
    request: TwitterPostRequest,
    agent: SocialMediaAgent = Depends(get_twitter_agent)
):
    """Create and publish Twitter/X post"""
    try:
        logger.info(f"Received request: {request}")
        result = agent.research_and_post(
            user_id=request.user_id,
            query=request.query,
            enable_human_review=False
        )
        return result
    except Exception as e:
        logger.error(f"Error creating tweet: {e}")
        raise HTTPException(status_code=500, detail=str(e))