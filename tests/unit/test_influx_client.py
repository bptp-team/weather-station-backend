from pydantic import SecretStr

from app.core.settings import Settings
from app.db.influx import create_influx_client


def test_client_sends_the_configured_token() -> None:
    settings = Settings(_env_file=None, influx_token=SecretStr("apiv3_example"))

    client = create_influx_client(settings)

    assert client.default_header["Authorization"] == "Token apiv3_example"


def test_client_omits_authorization_without_a_token() -> None:
    settings = Settings(_env_file=None)

    client = create_influx_client(settings)

    assert "Authorization" not in client.default_header


def test_token_is_hidden_from_the_settings_representation() -> None:
    settings = Settings(_env_file=None, influx_token=SecretStr("apiv3_example"))

    assert "apiv3_example" not in repr(settings)
