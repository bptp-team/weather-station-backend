from app.core.settings import Settings
from app.main import create_app


def create_test_app(settings: Settings):
    class TestSubscriber:
        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    return create_app(
        settings=settings,
        repository_factory=lambda settings: object(),
        subscriber_factory=lambda settings, service: TestSubscriber(),
        database_initializer=lambda settings: None,
    )


def test_settings_parse_comma_separated_origins() -> None:
    settings = Settings(allowed_origins="http://localhost:5173,http://192.168.1.10:5173")

    assert settings.cors_origins == [
        "http://localhost:5173",
        "http://192.168.1.10:5173",
    ]


def test_settings_reject_wildcard_origin() -> None:
    try:
        Settings(allowed_origins="*")
    except ValueError as error:
        assert "Wildcard CORS origins are not allowed" in str(error)
    else:
        raise AssertionError("Wildcard CORS origins must be rejected")


def test_app_uses_configured_cors_origins() -> None:
    app = create_test_app(Settings(allowed_origins="http://localhost:5173"))

    assert app.user_middleware[0].kwargs["allow_origins"] == ["http://localhost:5173"]
    assert app.user_middleware[0].kwargs["allow_headers"] == []


def test_app_rejects_wildcard_cors_headers() -> None:
    app = create_test_app(Settings(allowed_origins="http://localhost:5173"))

    assert "*" not in app.user_middleware[0].kwargs["allow_headers"]


def test_app_has_no_allowed_origins_by_default() -> None:
    app = create_test_app(Settings())

    assert app.user_middleware[0].kwargs["allow_origins"] == []