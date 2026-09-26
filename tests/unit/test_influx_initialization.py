import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from app.core.settings import Settings
from app.db import influx


def test_database_creation_sets_fifteen_day_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_requests: list[tuple[Request, int]] = []

    class FakeResponse:
        def __enter__(self) -> object:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def fake_urlopen(request: Request, timeout: int) -> FakeResponse:
        captured_requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(influx, "urlopen", fake_urlopen)
    settings = Settings(influx_url="http://influx.test/", influx_database="weather")

    influx.ensure_database_exists(settings)

    request, timeout = captured_requests[0]
    assert request.full_url == "http://influx.test/api/v3/configure/database"
    assert request.method == "POST"
    assert json.loads(request.data.decode("utf-8")) == {
        "db": "weather",
        "retention_period": "15d",
    }
    assert timeout == 10


def test_existing_database_is_not_updated(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def conflict_urlopen(request: Request, timeout: int) -> None:
        nonlocal calls
        calls += 1
        raise HTTPError(request.full_url, 409, "Conflict", {}, None)

    monkeypatch.setattr(influx, "urlopen", conflict_urlopen)
    settings = Settings(influx_url="http://influx.test", influx_database="weather")

    influx.ensure_database_exists(settings)

    assert calls == 1
