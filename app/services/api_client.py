"""HTTP client for https://api.dharun.dev/v1/mandi with retries and strict response checks."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import settings

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Any failure talking to the mandi API (network, HTTP status, bad payload)."""


@dataclass
class FetchResult:
    records: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_session(retries: int) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries, connect=retries, read=retries, backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


class MandiApiClient:
    def __init__(self, base_url: str | None = None, timeout: int | None = None,
                 limit: int | None = None, max_pages: int | None = None,
                 session: requests.Session | None = None):
        self.base_url = base_url or settings.mandi_api_url
        self.timeout = timeout or settings.api_timeout_seconds
        self.limit = limit or settings.api_page_limit
        self.max_pages = max(1, max_pages or settings.api_max_pages)
        self.session = session or build_session(settings.api_retries)

    def _get_page(self, state: str, commodity: str, page: int) -> list[dict]:
        params = {"state": state, "commodity": commodity, "limit": self.limit}
        if page > 0:  # first request stays identical to your proven fatch_mandi_data.py call
            params["offset"] = page * self.limit
        try:
            resp = self.session.get(self.base_url, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ApiError(f"request failed: {exc}") from exc
        try:
            payload = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ApiError("response was not valid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            keys = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            raise ApiError(f"unexpected response shape (top-level: {keys})")
        return payload["data"]

    def fetch(self, state: str, commodity: str) -> FetchResult:
        result = FetchResult()
        previous: list[dict] | None = None
        for page in range(self.max_pages):
            try:
                batch = self._get_page(state, commodity, page)
            except ApiError as exc:
                if page == 0:
                    raise  # nothing usable at all -> caller records a failure
                result.warnings.append(f"{commodity}: page {page + 1} failed ({exc}); kept earlier pages")
                break
            if previous is not None and batch == previous:
                result.warnings.append(f"{commodity}: API ignored offset (page repeated); stopped paging")
                break
            result.records.extend(batch)
            if len(batch) < self.limit:
                break
            previous = batch
        return result
