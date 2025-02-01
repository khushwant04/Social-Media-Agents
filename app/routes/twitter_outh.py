from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
import requests
import os
import secrets
import hashlib
import base64
from sqlalchemy.orm import Session
from app.db.config import TwitterToken, get_db

router = APIRouter()

# X.com OAuth2 Config
CLIENT_ID = os.getenv("X_CLIENT_ID")
CLIENT_SECRET = os.getenv("X_CLIENT_SECRET")
REDIRECT_URI = os.getenv("X_REDIRECT_URI")

# Replace with your actual frontend URL
FRONTEND_URL = "http://platform.hexelstudio.com/dashboard/assistants"  # Redirect frontend URL
AUTHORIZATION_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
USERINFO_URL = "https://api.x.com/2/users/me"


def generate_pkce():
    code_verifier = secrets.token_urlsafe(96)[:128]  # Generate a random string
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).decode("utf-8").replace("=", "")
    return code_verifier, code_challenge


# Step 1: Redirect user to X.com for authentication
code_verifiers = {}

@router.get("/login/x")
def login_x(user_id: str):
    """
    Redirects the user to X.com for OAuth2 authentication.
    `user_id` is a unique identifier for the user (e.g., email or username).
    """
    scopes = "tweet.read users.read tweet.write offline.access"
    code_verifier, code_challenge = generate_pkce()

    # Store the code_verifier with the state (user_id)
    code_verifiers[user_id] = code_verifier

    return RedirectResponse(
        f"{AUTHORIZATION_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&state={user_id}&scope={scopes}&code_challenge={code_challenge}&code_challenge_method=S256"
    )


# Step 2: Handle X.com OAuth2 callback
@router.get("/auth/x/callback")
def auth_x_callback(code: str, state: str, db: Session = Depends(get_db), request: Request = None):
    """
    Handles the X.com OAuth2 callback and redirects the user to the frontend with an access token.
    """
    if request and 'error' in request.query_params:
        error = request.query_params.get("error")
        description = request.query_params.get("error_description")
        raise HTTPException(status_code=400, detail=f"{error}: {description}")

    # Retrieve the code_verifier using the state (user_id)
    code_verifier = code_verifiers.get(state)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Code verifier not found for this user")

    # Exchange the authorization code for an access token
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,  # Use the correct code_verifier
    }
    auth = (CLIENT_ID, CLIENT_SECRET)
    response = requests.post(TOKEN_URL, data=data, auth=auth)

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to obtain access token")

    access_token = response.json().get("access_token")

    # Fetch the user's profile information using the X.com API
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    userinfo_response = requests.get(USERINFO_URL, headers=headers)

    if userinfo_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch user profile")

    userinfo = userinfo_response.json()
    x_user_id = userinfo.get("data", {}).get("id")  # X.com user ID is in the "data.id" field
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Failed to retrieve X.com user ID")

    # Store the access token and X.com user ID in the database
    db_token = TwitterToken(user_id=state, access_token=access_token, x_user_id=x_user_id)
    db.merge(db_token)  # Update if exists, insert if new
    db.commit()

    # Clean up the code_verifier (optional)
    code_verifiers.pop(state, None)

    # 🔥 Redirect the user to the frontend with the token
    return RedirectResponse(url=f"{FRONTEND_URL}?token={access_token}")