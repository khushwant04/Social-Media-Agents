from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
import re
import os
import requests
import logging
from app.services.web_agent import WebAgent, SearchProvider, SearchConfig, EnvironmentManager, SearchEngine
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.routes.linkedin_outh import LinkedInToken  # Shared Token model

# Configure logging to prevent GRPC warnings
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

class LinkedInAgent:
    """LinkedIn management agent with content handling"""
    
    CONTENT_TEMPLATE = """**LinkedIn Post Creation**
    Create professional content from this input:
    - Remove ALL markdown/formatting
    - Use business-appropriate tone
    - Add 1-2 relevant emojis
    - Include 3-5 industry-specific hashtags
    - Maintain paragraph structure
    - Strict {char_limit} character limit
    - Preserve key insights
    
    Input:
    {content}"""

    def __init__(
        self,
        web_agent: WebAgent,
        db_session: Session,
        linkedin_client_id: Optional[str] = None,
        linkedin_client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        max_post_length: int = 3000  # LinkedIn's limit
    ):
        self.web_agent = web_agent
        self.db = db_session
        self.max_post_length = max_post_length
        
        # LinkedIn configuration
        self.client_id = linkedin_client_id or os.getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = linkedin_client_secret or os.getenv("LINKEDIN_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("LINKEDIN_REDIRECT_URI")
        
        # API endpoints
        self.authorization_url = "https://www.linkedin.com/oauth/v2/authorization"
        self.token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        self.share_url = "https://api.linkedin.com/v2/ugcPosts"
        self.userinfo_url = "https://api.linkedin.com/v2/userinfo"

    @classmethod
    def from_environment(cls, db_session: Session):
        """Factory method using environment variables"""
        EnvironmentManager.load_environment()
        EnvironmentManager.setup_required_env_vars([
            "GOOGLE_API_KEY",
            "LINKEDIN_CLIENT_ID",
            "LINKEDIN_CLIENT_SECRET",
            "LINKEDIN_REDIRECT_URI"
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
            linkedin_client_id=os.getenv("LINKEDIN_CLIENT_ID"),
            linkedin_client_secret=os.getenv("LINKEDIN_CLIENT_SECRET"),
            redirect_uri=os.getenv("LINKEDIN_REDIRECT_URI")
        )

    def _clean_content(self, text: str) -> str:
        """Sanitize input text from formatting"""
        patterns = [
            (r'\*\*(.*?)\*\*', r'\1'),
            (r'\*(.*?)\*', r'\1'),
            (r'^#+\s*', ''),
            (r'\[(.*?)\]\(.*?\)', r'\1'),
            (r'!\[.*?\]\(.*?\)', ''),
            (r'<.*?>', ''),
            (r'&[a-z]+;', ''),
            (r'[\\_~>]', '')
        ]
        
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text, flags=re.DOTALL)
        
        return text.strip()

    def _generate_post(self, content: str, max_length: int) -> str:
        """Generate LinkedIn-optimized content"""
        prompt = self.CONTENT_TEMPLATE.format(
            content=content,
            char_limit=max_length
        )
        
        response = self.web_agent.llm.invoke([
            SystemMessage(content="You are a professional LinkedIn content creator."),
            HumanMessage(content=prompt)
        ]).content
        
        return self._process_content(response, max_length)

    def _process_content(self, content: str, max_length: int) -> str:
        """Validate and finalize content"""
        cleaned = self._clean_content(content)
        
        if len(cleaned) < 100:
            raise ValueError("Content too short for LinkedIn")
            
        return self._smart_truncate(cleaned, max_length)

    def _smart_truncate(self, content: str, max_length: int) -> str:
        """Intelligent content shortening for LinkedIn"""
        if len(content) <= max_length:
            return content
        
        # Prioritize paragraph breaks
        truncated = content[:max_length]
        break_points = ['\n\n', '. ', '! ', '? ', '; ', ', ']
        
        for point in break_points:
            last_index = truncated.rfind(point)
            if last_index > max_length * 0.8:
                return truncated[:last_index].strip() + '...'
        
        return content[:max_length-3] + '...'

    def start_linkedin_oauth(self, user_id: str) -> str:
        """Initialize LinkedIn OAuth flow"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": user_id,
            "scope": "openid profile email w_member_social"
        }
        return f"{self.authorization_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"

    def complete_linkedin_oauth(self, code: str, state: str) -> Dict[str, str]:
        """Complete LinkedIn OAuth authentication"""
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        response = requests.post(self.token_url, data=token_data)
        if response.status_code != 200:
            raise ConnectionError("Failed to obtain access token")

        access_token = response.json().get("access_token")
        
        # Get user info
        headers = {"Authorization": f"Bearer {access_token}"}
        userinfo = requests.get(self.userinfo_url, headers=headers).json()
        
        linkedin_urn = userinfo.get("sub")
        if not linkedin_urn:
            raise ValueError("Failed to retrieve LinkedIn URN")

        # Store token
        token_record = LinkedInToken(
            user_id=state,
            access_token=access_token,
            linkedin_urn=linkedin_urn
        )
        self.db.merge(token_record)
        self.db.commit()

        return {"status": "success", "user_id": state}

    def post_to_linkedin(self, user_id: str, content: str) -> Dict[str, Any]:
        """Post content to LinkedIn"""
        token_record = self.db.query(LinkedInToken).filter_by(user_id=user_id).first()
        if not token_record:
            raise ValueError("User not authenticated")

        headers = {
            "Authorization": f"Bearer {token_record.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        post_data = {
            "author": f"urn:li:person:{token_record.linkedin_urn}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        response = requests.post(self.share_url, headers=headers, json=post_data)
        if response.status_code != 201:
            raise ConnectionError(f"LinkedIn API error: {response.text}")

        return response.json()

    def _human_review(self, content: str, max_length: int) -> Optional[str]:
        """Interactive content approval process"""
        print("\n=== Proposed LinkedIn Post ===")
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
        hashtag_policy: str = "professional",
        enable_human_review: bool = True
    ) -> Dict[str, Any]:
        """Complete LinkedIn posting workflow"""
        try:
            raw_content = self.web_agent.invoke(query)
            if not raw_content:
                raise ValueError("No content generated")
                
            post_length = max_length or self.max_post_length
            formatted = self._generate_post(
                self._clean_content(raw_content),
                post_length
            )
            
            final_content = self._apply_hashtag_policy(formatted, hashtag_policy)
            
            if enable_human_review:
                final_content = self._human_review(final_content, post_length)
                if not final_content:
                    return {"status": "canceled", "message": "Post canceled"}

            return self.post_to_linkedin(user_id, final_content)
            
        except Exception as e:
            logger.error(f"LinkedIn posting failed: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _apply_hashtag_policy(self, content: str, policy: str) -> str:
        """Manage LinkedIn hashtag strategy"""
        hashtags = re.findall(r'#\S+', content)
        clean = re.sub(r'#\S+', '', content).strip()
        
        if policy == "none":
            return clean
            
        if policy == "professional":
            if len(clean) + len(' '.join(hashtags)) <= self.max_post_length:
                return f"{clean}\n\n{' '.join(hashtags[:5])}".strip()
            return clean
            
        if policy == "industry":
            return f"{clean}\n\n{' '.join(hashtags[:7])}".strip()
            
        return content

# if __name__ == "__main__":
#     from sqlalchemy import create_engine
#     from sqlalchemy.orm import sessionmaker

#     engine = create_engine(os.getenv("DATABASE_URL"))
#     Session = sessionmaker(bind=engine)
    
#     with Session() as session:
#         agent = LinkedInAgent.from_environment(session)
#         result = agent.research_and_post(
#             user_id="khushwant-sanwalot",
#             query="Create a post about DeepSeek AI R1 model",
#             enable_human_review=True
#         )

#         if result.get("status") == "canceled":
#             print("Post canceled by user")
#         else:
#             print(f"Posted successfully: {result.get('id', '')}")