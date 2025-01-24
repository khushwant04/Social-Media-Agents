from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import os
import requests
from enum import Enum
from dotenv import load_dotenv
import getpass

from langgraph.graph import START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI

class SearchEngine(Enum):
    GOOGLE = "google"
    # Extensible for future search providers
    # BING = "bing"
    # DUCKDUCKGO = "duckduckgo"

@dataclass
class SearchConfig:
    provider: SearchEngine
    api_key: str
    search_engine_id: Optional[str] = None
    max_results: int = 5
    safe_search: bool = True

class SearchError(Exception):
    """Custom exception for search-related errors"""
    pass

class EnvironmentManager:
    @staticmethod
    def setup_required_env_vars(required_vars: List[str]) -> None:
        for var in required_vars:
            if not os.environ.get(var):
                os.environ[var] = getpass.getpass(f"Enter {var}: ")
    
    @staticmethod
    def load_environment():
        load_dotenv()
        
    @staticmethod
    def get_required_env(var_name: str, error_message: Optional[str] = None) -> str:
        value = os.getenv(var_name)
        if not value:
            raise ValueError(error_message or f"Environment variable {var_name} is not set")
        return value

class SearchProvider:
    def __init__(self, config: SearchConfig):
        self.config = config
    
    def search(self, query: str) -> List[Dict[str, str]]:
        if self.config.provider == SearchEngine.GOOGLE:
            return self._google_search(query)
        # Add more providers here
        raise ValueError(f"Unsupported search provider: {self.config.provider}")
    
    def _google_search(self, query: str) -> List[Dict[str, str]]:
        if not self.config.search_engine_id:
            raise SearchError("Search engine ID is required for Google Custom Search")
            
        url = (
            f"https://www.googleapis.com/customsearch/v1"
            f"?q={query}"
            f"&key={self.config.api_key}"
            f"&cx={self.config.search_engine_id}"
            f"&num={self.config.max_results}"
            f"&safe={'active' if self.config.safe_search else 'off'}"
        )
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                raise SearchError(f"Google API error: {data['error']['message']}")
            
            items = data.get('items', [])
            return [
                {
                    'title': item.get('title', ''),
                    'link': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'source': 'google'
                }
                for item in items[:self.config.max_results]
            ]
        except requests.RequestException as e:
            raise SearchError(f"Search request failed: {str(e)}")
        except ValueError as e:
            raise SearchError(f"Invalid response format: {str(e)}")

class WebAgent:
    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        search_provider: SearchProvider,
        system_prompt: Optional[str] = None
    ):
        self.llm = llm
        self.search_provider = search_provider
        self.tools = [self._create_search_tool()]
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.system_message = SystemMessage(content=system_prompt or self._default_system_prompt())
        self.react_graph = self._build_graph()
    
    def _default_system_prompt(self) -> str:
        return """You are a helpful assistant with access to a search tool. 
        IMPORTANT: Do NOT say you don't have information or need to search first.
        Instead, IMMEDIATELY use the search tool whenever you need to find information about:
        - People
        - Current events
        - Facts you're not completely certain about
        - Any topic that might need up-to-date information
        
        Just use the tool directly without announcing that you're going to search.
        After getting search results, provide a clear and concise summary of the information."""
    
    def _create_search_tool(self) -> Tool:
        return Tool(
            name="web_search",
            description="Search the web for recent results.",
            func=self._search
        )
    
    def _search(self, query: str) -> List[Dict[str, str]]:
        try:
            return self.search_provider.search(query)
        except SearchError as e:
            print(f"Search error: {str(e)}")
            return []
    
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("assistant", self.assistant)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_edge(START, "assistant")
        builder.add_conditional_edges("assistant", tools_condition)
        builder.add_edge("tools", "assistant")
        return builder.compile()
    
    def assistant(self, state: MessagesState) -> Dict[str, List]:
        return {
            "messages": [
                self.llm_with_tools.invoke([self.system_message] + state["messages"])
            ]
        }
    
    def invoke(self, user_message: str) -> str:
        try:
            messages = [HumanMessage(content=user_message)]
            result = self.react_graph.invoke({"messages": messages})
            return result['messages'][-1].content
        except Exception as e:
            return f"Error processing request: {str(e)}"

def main():
    try:
        # Setup environment
        EnvironmentManager.load_environment()
        EnvironmentManager.setup_required_env_vars(["GOOGLE_API_KEY", "SEARCH_ENGINE_ID"])
        
        # Get configuration from environment
        google_api_key = EnvironmentManager.get_required_env("GOOGLE_API_KEY")
        search_engine_id = EnvironmentManager.get_required_env("SEARCH_ENGINE_ID")
        
        # Initialize search configuration
        search_config = SearchConfig(
            provider=SearchEngine.GOOGLE,  # Changed from SearchProvider to SearchEngine
            api_key=google_api_key,
            search_engine_id=search_engine_id,
            max_results=5
        )
        
        # Initialize search provider
        search_provider = SearchProvider(search_config)
        
        # Initialize LLM
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            max_tokens=4096,
            api_key=google_api_key
        )
        
        # Create WebAgent
        web_agent = WebAgent(llm, search_provider)
        
        # Example usage
        response = web_agent.invoke("Tell me something about Khushwant Sanwalot?")
        print(response)
        
    except Exception as e:
        print(f"Error in main execution: {str(e)}")
        raise

if __name__ == "__main__":
    main()