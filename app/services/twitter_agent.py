from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
import re
import os
import requests
import logging
from app.services.web_agent import WebAgent, SearchProvider, SearchConfig, EnvironmentManager, SearchEngine
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.routes.twitter_outh import TwitterToken, generate_pkce

# Configure logging to prevent GRPC warnings
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

class SocialMediaAgent:
    """Social media management agent with enhanced content handling"""
    
    CONTENT_TEMPLATE = """**Social Media Post Creation**
    Create engaging content from this input:
    - Remove ALL markdown/formatting
    - Use Twitter-friendly tone
    - Add 1-3 relevant emojis
    - Include 2-3 hashtags
    - Strict {char_limit} character limit
    - Preserve key information
    
    Input:
    {content}"""

    def __init__(
        self,
        web_agent: WebAgent,
        db_session: Session,
        twitter_client_id: Optional[str] = None,
        twitter_client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        max_post_length: int = 280
    ):
        self.web_agent = web_agent
        self.db = db_session
        self.code_verifiers = {}
        self.max_post_length = max_post_length
        
        # Twitter/X configuration
        self.client_id = twitter_client_id or os.getenv("X_CLIENT_ID")
        self.client_secret = twitter_client_secret or os.getenv("X_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("X_REDIRECT_URI")
        
        # API endpoints
        self.authorization_url = "https://x.com/i/oauth2/authorize"
        self.token_url = "https://api.x.com/2/oauth2/token"
        self.tweet_url = "https://api.x.com/2/tweets"
        self.userinfo_url = "https://api.x.com/2/users/me"

    @classmethod
    def from_environment(cls, db_session: Session):
        """Factory method using environment variables"""
        EnvironmentManager.load_environment()
        EnvironmentManager.setup_required_env_vars([
            "GOOGLE_API_KEY", 
            "SEARCH_ENGINE_ID",
            "X_CLIENT_ID",
            "X_CLIENT_SECRET",
            "X_REDIRECT_URI"
        ])

        search_config = SearchConfig(
            provider=SearchEngine.GOOGLE,
            api_key=os.getenv("GOOGLE_API_KEY"),
            search_engine_id=os.getenv("SEARCH_ENGINE_ID")
        )
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            max_tokens=4096,
            api_key=os.getenv("GOOGLE_API_KEY")
        )
        
        return cls(
            web_agent=WebAgent(llm, SearchProvider(search_config)),
            db_session=db_session,
            twitter_client_id=os.getenv("X_CLIENT_ID"),
            twitter_client_secret=os.getenv("X_CLIENT_SECRET"),
            redirect_uri=os.getenv("X_REDIRECT_URI")
        )

    def _clean_content(self, text: str) -> str:
        """Sanitize input text from formatting"""
        patterns = [
            (r'\*\*(.*?)\*\*', r'\1'),     # Bold
            (r'\*(.*?)\*', r'\1'),         # Italic
            (r'^#+\s*', ''),               # Headers
            (r'\[(.*?)\]\(.*?\)', r'\1'),  # Links
            (r'!\[.*?\]\(.*?\)', ''),      # Images
            (r'`{3}.*?`{3}', ''),          # Code blocks
            (r'`(.*?)`', r'\1'),           # Inline code
            (r'<.*?>', ''),                # HTML tags
            (r'&[a-z]+;', ''),             # HTML entities
            (r'[\\_~>]', '')               # Special characters
        ]
        
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text, flags=re.DOTALL)
        
        return text.strip()

    def _generate_post(self, content: str, max_length: int) -> str:
        """Generate optimized social media content"""
        prompt = self.CONTENT_TEMPLATE.format(
            content=content,
            char_limit=max_length
        )
        
        response = self.web_agent.llm.invoke([
            SystemMessage(content="You are a professional social media content creator."),
            HumanMessage(content=prompt)
        ]).content
        
        return self._process_content(response, max_length)

    def _process_content(self, content: str, max_length: int) -> str:
        """Validate and finalize content"""
        cleaned = self._clean_content(content)
        
        if len(cleaned) < 15:
            raise ValueError("Generated content is too short")
            
        return self._smart_truncate(cleaned, max_length)

    def _smart_truncate(self, content: str, max_length: int) -> str:
        """Intelligent content shortening"""
        if len(content) <= max_length:
            return content
        
        truncated = content[:max_length]
        break_points = ['. ', '! ', '? ', '\n\n', '\n', '; ', ', ']
        
        for point in break_points:
            last_index = truncated.rfind(point)
            if last_index > max_length * 0.75:
                return truncated[:last_index].strip() + '...'
        
        return content[:max_length-3] + '...'

    def start_twitter_oauth(self, user_id: str) -> str:
        """Initialize Twitter OAuth flow"""
        code_verifier, code_challenge = generate_pkce()
        self.code_verifiers[user_id] = code_verifier
        
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": user_id,
            "scope": "tweet.read users.read tweet.write offline.access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        
        return f"{self.authorization_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"

    def complete_twitter_oauth(self, code: str, state: str) -> Dict[str, str]:
        """Complete Twitter OAuth authentication"""
        code_verifier = self.code_verifiers.pop(state, None)
        if not code_verifier:
            raise ValueError("Invalid or expired OAuth state")

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier,
        }

        response = requests.post(
            self.token_url,
            data=token_data,
            auth=(self.client_id, self.client_secret)
        )
        
        if response.status_code != 200:
            raise ConnectionError(f"OAuth failed: {response.json().get('error_description', 'Unknown error')}")

        token_info = response.json()
        access_token = token_info["access_token"]
        
        # Get user info
        user_info = requests.get(
            self.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"}
        ).json()
        
        x_user_id = user_info.get("data", {}).get("id")
        if not x_user_id:
            raise ValueError("Failed to retrieve X user ID")

        # Store token
        token_record = TwitterToken(
            user_id=state,
            access_token=access_token,
            x_user_id=x_user_id
        )
        self.db.merge(token_record)
        self.db.commit()

        return {"status": "success", "user_id": state}

    def post_to_twitter(self, user_id: str, content: str) -> Dict[str, Any]:
        """Post content to Twitter/X"""
        token_record = self.db.query(TwitterToken).filter_by(user_id=user_id).first()
        if not token_record:
            raise ValueError("User not authenticated")

        response = requests.post(
            self.tweet_url,
            headers={
                "Authorization": f"Bearer {token_record.access_token}",
                "Content-Type": "application/json"
            },
            json={"text": content}
        )

        if response.status_code not in [200, 201]:
            error_info = response.json()
            raise ConnectionError(
                f"Twitter API error ({response.status_code}): {error_info.get('detail', 'Unknown error')}"
            )

        return response.json()

    def _human_review(self, content: str, max_length: int) -> Optional[str]:
        """Interactive content approval process"""
        if not content or len(content) < 10:
            raise ValueError("Invalid content for review")
        
        print("\n=== Proposed Post ===")
        print(content)
        print(f"\nCharacter count: {len(content)}/{max_length}")
        
        while True:
            choice = input("\n1. Approve\n2. Edit\n3. Cancel\nChoice (1-3): ").strip()
            
            if choice == "1":
                if len(content) > max_length:
                    print(f"Warning: {len(content)-max_length} over limit!")
                    continue
                return content
            elif choice == "2":
                new_content = self._get_user_edit(content, max_length)
                if new_content is not None:
                    content = new_content
                    print("\n=== Updated Post ===")
                    print(content)
                    print(f"\nNew length: {len(content)}/{max_length}")
            elif choice == "3":
                return None
            else:
                print("Invalid choice. Please select 1-3.")

    def _get_user_edit(self, current_content: str, max_length: int) -> Optional[str]:
        """User editing interface"""
        print("\nEdit your post (CTRL+D when done):")
        print("-----------------------------------")
        try:
            lines = []
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
            
        new_content = "\n".join(lines).strip()
        
        if not new_content:
            print("Keeping original content")
            return current_content
            
        if len(new_content) > max_length:
            print(f"⚠️ Exceeds limit by {len(new_content)-max_length}!")
            if input("Try again? (y/n): ").lower() == 'y':
                return self._get_user_edit(current_content, max_length)
            return current_content
            
        return new_content

    def research_and_post(
        self,
        user_id: str,
        query: str,
        max_length: Optional[int] = None,
        hashtag_policy: str = "smart",
        enable_human_review: bool = True
    ) -> Dict[str, Any]:
        """Complete posting workflow"""
        try:
            # Generate content
            raw_content = self.web_agent.invoke(query)
            if not raw_content:
                raise ValueError("No content generated")
                
            # Process content
            post_length = max_length or self.max_post_length
            formatted = self._generate_post(
                self._clean_content(raw_content),
                post_length
            )
            
            # Apply hashtag strategy
            final_content = self._apply_hashtag_policy(formatted, hashtag_policy)
            
            # Human review
            if enable_human_review:
                final_content = self._human_review(final_content, post_length)
                if not final_content:
                    return {"status": "canceled", "message": "Post canceled"}

            return self.post_to_twitter(user_id, final_content)
            
        except Exception as e:
            logger.error(f"Posting failed: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _apply_hashtag_policy(self, content: str, policy: str) -> str:
        """Manage hashtag inclusion strategy"""
        hashtags = re.findall(r'#\S+', content)
        clean = re.sub(r'#\S+', '', content).strip()
        
        if policy == "none":
            return clean
            
        if policy == "smart":
            if len(clean) + len(' '.join(hashtags)) <= self.max_post_length:
                return f"{clean}\n\n{' '.join(hashtags[:3])}".strip()
            return clean
            
        if policy == "aggressive":
            return f"{clean}\n\n{' '.join(hashtags[:5])}".strip()
            
        return content

# if __name__ == "__main__":
#     from sqlalchemy import create_engine
#     from sqlalchemy.orm import sessionmaker

#     # Configure database
#     engine = create_engine(os.getenv("DATABASE_URL"))
#     Session = sessionmaker(bind=engine)
    
#     with Session() as session:
#         agent = SocialMediaAgent.from_environment(session)
#         result = agent.research_and_post(
#             user_id="ksanwalot04",
#             query="Create a post about Deepseek ai R1 model",
#             enable_human_review=True
#         )

#         if result.get("status") == "canceled":
#             print("Post canceled by user")
#         else:
#             print(f"Posted successfully: {result.get('data', {}).get('id', '')}")