from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    telegram_bot_token: str
    openrouter_api_key: str
    openrouter_model: str = "openai/gpt-4.1-mini"
    redis_url: str = "redis://localhost:6379/0"
    google_sa_json: str

def get_settings() -> Settings:
    return Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        google_sa_json=os.environ["GOOGLE_SA_JSON"],
    )
