from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Standard boto3 credentials (preferred — from workshop .env)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""           # required for temporary/hackathon credentials
    aws_default_region: str = "us-east-1"

    # Fallback: bearer token HTTP (used if no access key is set)
    aws_bearer_token_bedrock: str = ""

    aws_account_id: str = "719573866669"
    aws_region: str = "us-east-1"
    video_file: str = ""  # test video key in S3 (used by test scripts)
    s3_bucket: str = "segmentiq-videos"
    s3_vectors_bucket: str = "segmentiq-embeddings"
    dynamodb_table: str = "segmentiq-videos"
    redis_url: str = "redis://localhost:6379/0"
    app_env: str = "development"
    cors_origins: str = "*"

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()
