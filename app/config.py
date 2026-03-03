from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    telegram_bot_token: str
    gigachat_api_key: str
    gigachat_base_url: str = "https://gigachat.devices.sberbank.ru/api/v1"
    gigachat_model: str = "GigaChat-2"  # Default model name
    redis_url: str = "redis://localhost:6379/0"
    google_sa_json: str

def get_settings() -> Settings:
    return Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        gigachat_api_key=os.environ["GIGACHAT_API_KEY"],
        gigachat_base_url=os.getenv("GIGACHAT_BASE_URL", "https://gigachat.devices.sberbank.ru/api/v1"),
        gigachat_model=os.getenv("GIGACHAT_MODEL", "GigaChat-2"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        google_sa_json=os.environ["GOOGLE_SA_JSON"],
    )