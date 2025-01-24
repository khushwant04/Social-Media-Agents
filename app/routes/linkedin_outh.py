from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
import requests
import os
from sqlalchemy.orm import Session
from app.db.config import LinkedInToken, get_db

router = APIRouter()

# LinkedIn OAuth2 Config
CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI")

AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
SHARE_URL = "https://api.linkedin.com/v2/ugcPosts"

# Step 1: Redirect user to LinkedIn for authentication
@router.get("/login/linkedin")
def login_linkedin(user_id: str):
    """
    Redirects the user to LinkedIn for OAuth2 authentication.
    `user_id` is a unique identifier for the user (e.g., email or username).
    """
    scopes = "openid profile email w_member_social"  # Updated scopes for OpenID Connect
    return RedirectResponse(
        f"{AUTHORIZATION_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&state={user_id}&scope={scopes}"
    )

# Step 2: Handle LinkedIn OAuth2 callback
@router.get("/auth/linkedin/callback")
def auth_linkedin_callback(code: str, state: str, db: Session = Depends(get_db), request: Request = None):
    """
    Handles the LinkedIn OAuth2 callback and stores the access token and URN for the user.
    """
    if request and 'error' in request.query_params:
        error = request.query_params.get("error")
        description = request.query_params.get("error_description")
        raise HTTPException(status_code=400, detail=f"{error}: {description}")

    # Debugging: Print the authorization code
    print(f"Authorization code: {code}")  # Debugging

    # Exchange the authorization code for an access token
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    response = requests.post(TOKEN_URL, data=data)
    print(f"Token exchange response: {response.status_code}, {response.text}")  # Debugging

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to obtain access token")

    access_token = response.json().get("access_token")
    print(f"Access token: {access_token}")  # Debugging

    # Fetch the user's profile information using the OpenID Connect userinfo endpoint
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    userinfo_response = requests.get(USERINFO_URL, headers=headers)
    print(f"Userinfo response: {userinfo_response.status_code}, {userinfo_response.text}")  # Debugging

    if userinfo_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch user profile")

    userinfo = userinfo_response.json()
    linkedin_urn = userinfo.get("sub")  # LinkedIn URN is in the "sub" field
    if not linkedin_urn:
        raise HTTPException(status_code=400, detail="Failed to retrieve LinkedIn URN")

    # Store the access token and LinkedIn URN in the database
    db_token = LinkedInToken(user_id=state, access_token=access_token, linkedin_urn=linkedin_urn)
    db.merge(db_token)  # Update if exists, insert if new
    db.commit()

    return {"message": "Authentication successful", "user_id": state}
