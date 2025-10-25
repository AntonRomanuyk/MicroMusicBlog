from pydantic_settings  import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_user: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_BASE_DIR: Path = BASE_DIR / "uploads"
    AVATAR_DIR: Path = UPLOAD_BASE_DIR / "avatars"
    POST_FILES_DIR: Path = UPLOAD_BASE_DIR / "post_files"

    class Config:
        env_file = ".env"


settings = Settings()