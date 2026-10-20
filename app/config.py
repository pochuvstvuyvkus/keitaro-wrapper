from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Settings are read from the environment, then from .env.local and .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    keitaro_url: str = Field("https://tlgk.host", description="Keitaro base URL, no trailing /")
    keitaro_api_key: str = Field("", repr=False)
    # Cloudflare in front of the tracker answers 403 to non-browser user agents.
    keitaro_user_agent: str = DEFAULT_USER_AGENT
    keitaro_timeout: float = 20.0

    # Defaults for new campaigns: group FORTESTS, source FORTESTS, domain in.posdk.xyz.
    keitaro_group_id: int = 4970
    keitaro_traffic_source_id: int = 473
    keitaro_domain_id: int = 4622

    geo_redirect_url: str = "https://google.com"

    database_url: str = "sqlite:///./adrobot.db"
    offers_cache_ttl: int = 300

    @property
    def keitaro_admin_url(self) -> str:
        return f"{self.keitaro_url.rstrip('/')}/admin/"

    def campaign_admin_url(self, campaign_id: int) -> str:
        return f"{self.keitaro_admin_url}#!/campaigns/{campaign_id}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
