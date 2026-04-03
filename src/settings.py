from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # App
    app_name: str = Field(default="FastAPI Minimal Template", env="APP_NAME")
    app_version: str = Field(default="0.1.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    run_seeds: bool = Field(default=False, env="RUN_SEEDS")

    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    grpc_port: int = Field(default=50051, env="GRPC_PORT")

    # Database (Peewee)
    database_url: str = Field(default="sqlite:///db.sqlite", env="DATABASE_URL")

    # Cache (Redis)
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_ttl: int = Field(default=3600, env="REDIS_TTL")

    # AWS S3
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(
        default=None, env="AWS_SECRET_ACCESS_KEY"
    )
    aws_session_token: Optional[str] = Field(default=None, env="AWS_SESSION_TOKEN")
    aws_region: Optional[str] = Field(default=None, env="AWS_REGION")
    aws_s3_endpoint_url: Optional[str] = Field(default=None, env="AWS_S3_ENDPOINT_URL")
    aws_s3_bucket: Optional[str] = Field(default=None, env="AWS_S3_BUCKET")

    # LLM
    llm_provider: str = Field(default="gemini", env="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-2.5-flash", env="LLM_MODEL")
    llm_api_key: Optional[str] = Field(default=None, env="LLM_API_KEY")
    llm_host: Optional[str] = Field(default=None, env="LLM_HOST")
    llm_use_vertex_ai: bool = Field(default=False, env="LLM_USE_VERTEX_AI")
    llm_vertex_project: Optional[str] = Field(default=None, env="LLM_VERTEX_PROJECT")
    llm_vertex_location: Optional[str] = Field(default=None, env="LLM_VERTEX_LOCATION")

    # OCR
    ocr_provider: str = Field(default="ppstructure", env="OCR_PROVIDER")
    ocr_lang: str = Field(default="en", env="OCR_LANG")
    ocr_use_gpu: bool = Field(default=False, env="OCR_USE_GPU")

    # Event Bus (Kafka)
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", env="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_consumer_group_id: str = Field(
        default="fastapi-minimal-template", env="KAFKA_CONSUMER_GROUP_ID"
    )
    kafka_consumer_auto_offset_reset: str = Field(
        default="earliest", env="KAFKA_CONSUMER_AUTO_OFFSET_RESET"
    )

    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173", env="CORS_ORIGINS"
    )
    cors_allow_credentials: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    cors_allow_methods: str = Field(
        default="GET,POST,PUT,DELETE,OPTIONS", env="CORS_ALLOW_METHODS"
    )
    cors_allow_headers: str = Field(
        default="Authorization,Content-Type,Accept", env="CORS_ALLOW_HEADERS"
    )

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def kafka_bootstrap_servers_list(self) -> list[str]:
        """Parse kafka_bootstrap_servers into a list"""
        return self.kafka_bootstrap_servers.split(",")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse cors_origins into a list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def cors_allow_methods_list(self) -> list[str]:
        """Parse cors_allow_methods into a list"""
        return [method.strip() for method in self.cors_allow_methods.split(",")]

    @property
    def cors_allow_headers_list(self) -> list[str]:
        """Parse cors_allow_headers into a list"""
        return [header.strip() for header in self.cors_allow_headers.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
