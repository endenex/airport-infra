from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Pydantic-settings v2 doesn't always pick up .env reliably depending on CWD
# resolution. Load it via python-dotenv first so os.environ is populated
# before Settings() reads it.
#
# override=True so that empty-string env vars (e.g. shell init scripts that
# pre-declare ANTHROPIC_API_KEY="") don't shadow real values from .env.
# Safe because .env is gitignored — it doesn't exist in CI/production where
# env vars are set authoritatively.
load_dotenv(override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = ""

    # LLM
    anthropic_api_key: str = ""
    llm_extraction_model: str = "claude-haiku-4-5-20251001"
    llm_complex_model: str = "claude-sonnet-4-6"
    llm_high_confidence_threshold: float = 0.85

    # Authenticated data sources
    companies_house_api_key: str = ""
    edinet_subscription_key: str = ""

    # Document storage (Cloudflare R2)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "airport-infra-documents"

    # App
    environment: str = "development"
    debug: bool = False


settings = Settings()
