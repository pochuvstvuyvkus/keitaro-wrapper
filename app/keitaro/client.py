import logging
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger(__name__)


class KeitaroError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class KeitaroClient:
    """Thin wrapper over the Keitaro Admin API (/admin_api/v1)."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        if not settings.keitaro_api_key:
            raise KeitaroError("KEITARO_API_KEY не задан: заполните .env")
        self._http = httpx.Client(
            base_url=f"{settings.keitaro_url.rstrip('/')}/admin_api/v1",
            headers={
                "Api-Key": settings.keitaro_api_key,
                "User-Agent": settings.keitaro_user_agent,
                "Accept": "application/json",
            },
            timeout=settings.keitaro_timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, json: Any = None) -> Any:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise KeitaroError(f"Keitaro недоступен: {exc}") from exc
        log.info("keitaro %s %s -> %s", method, path, response.status_code)
        if response.status_code >= 400:
            raise KeitaroError(_error_text(response), response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise KeitaroError(
                f"Keitaro вернул не JSON ({response.status_code})", response.status_code
            ) from exc

    # Campaigns
    def list_campaigns(self) -> list[dict]:
        return self._request("GET", "/campaigns")

    def get_campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", payload)

    def delete_campaign(self, campaign_id: int) -> dict:
        """Moves the campaign to the archive (state=deleted)."""
        return self._request("DELETE", f"/campaigns/{campaign_id}")

    # Streams
    def campaign_streams(self, campaign_id: int) -> list[dict]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/streams/{stream_id}", payload)

    # Dictionaries
    def list_offers(self) -> list[dict]:
        return self._request("GET", "/offers")

    def list_groups(self, group_type: str = "campaigns") -> list[dict]:
        return self._request("GET", f"/groups?type={group_type}")

    def list_traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources")


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("error"):
        detail = body["error"]
    elif response.status_code == 403 and "cloudflare" in response.text.lower():
        detail = "Cloudflare отклонил запрос (проверьте KEITARO_USER_AGENT)"
    else:
        detail = response.text[:300] or response.reason_phrase
    return f"Keitaro {response.status_code}: {detail}"
