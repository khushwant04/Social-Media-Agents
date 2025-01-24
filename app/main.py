from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
from app.db.config import Base, engine
from app.routes import (
    linkedin_outh, twitter_outh, linkedin_post, twitter_post
)
# Load environment variables
load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(twitter_outh.router)
app.include_router(twitter_post.router)
app.include_router(linkedin_outh.router)
app.include_router(linkedin_post.router)


