import pytest
import requests

from app.services.api_client import ApiError, MandiApiClient


class FakeResponse:
    def __init__(self, payload=None, status=200, bad_json=False):
        self.payload, self.status_code, self.bad_json = payload, status, bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        if self.bad_json:
            raise ValueError("no json")
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(responses, **kw):
    s = FakeSession(responses)
    return MandiApiClient(base_url="http://x", timeout=5, limit=2, session=s, **kw), s


def test_single_page_default():
    c, s = client([FakeResponse({"data": [{"a": 1}, {"a": 2}]})], max_pages=1)
    res = c.fetch("Rajasthan", "Wheat")
    assert len(res.records) == 2 and len(s.calls) == 1
    assert "offset" not in s.calls[0] and s.calls[0]["state"] == "Rajasthan"


def test_pagination_stops_on_short_page():
    c, s = client([FakeResponse({"data": [{"a": 1}, {"a": 2}]}),
                   FakeResponse({"data": [{"a": 3}]})], max_pages=5)
    res = c.fetch("Rajasthan", "Wheat")
    assert len(res.records) == 3 and s.calls[1]["offset"] == 2


def test_repeated_page_detected_when_offset_ignored():
    page = {"data": [{"a": 1}, {"a": 2}]}
    c, _ = client([FakeResponse(page), FakeResponse(page)], max_pages=5)
    res = c.fetch("Rajasthan", "Wheat")
    assert len(res.records) == 2 and any("ignored offset" in w for w in res.warnings)


def test_later_page_failure_keeps_earlier_records():
    c, _ = client([FakeResponse({"data": [{"a": 1}, {"a": 2}]}), FakeResponse(status=500)], max_pages=3)
    res = c.fetch("Rajasthan", "Wheat")
    assert len(res.records) == 2 and res.warnings


@pytest.mark.parametrize("resp", [
    FakeResponse(status=503),
    FakeResponse(bad_json=True),
    FakeResponse({"unexpected": []}),
    FakeResponse([1, 2, 3]),
    requests.exceptions.ConnectionError("down"),
    requests.exceptions.Timeout("slow"),
])
def test_first_page_failures_raise_api_error(resp):
    c, _ = client([resp])
    with pytest.raises(ApiError):
        c.fetch("Rajasthan", "Wheat")
