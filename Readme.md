# Social Media Agent 🤖📱

A smart API-based social media management system that automates post creation and publishing using AI. Supports LinkedIn and Twitter/X with secure OAuth2 authentication.

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)](https://www.python.org/)

## Features ✨

- **Multi-Platform Support**
  - LinkedIn professional post generation
  - Twitter/X tweet optimization
- **AI-Powered Content Creation**
  - GPT-4/Gemini content generation
  - Automatic markdown cleanup
  - Smart hashtag suggestions
- **Secure Authentication**
  - OAuth2 with PKCE (Proof Key for Code Exchange)
  - Token encryption and secure storage
- **Advanced Post Management**
  - Customizable length limits
  - Hashtag policies (smart/aggressive/none)
  - Human review mode
- **Enterprise Ready**
  - PostgreSQL database integration
  - Rate limiting
  - Comprehensive logging

## Tech Stack 🛠️

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database**: [PostgreSQL](https://www.postgresql.org/) + [SQLAlchemy](https://www.sqlalchemy.org/)
- **AI**: [Google Gemini](https://ai.google.dev/)/[OpenAI GPT](https://openai.com/)
- **Auth**: OAuth2 with PKCE
- **Deployment**: Docker ready

## Installation 💻

```bash
# Clone repository
git clone https://github.com/yourusername/social-media-agent.git
cd social-media-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt