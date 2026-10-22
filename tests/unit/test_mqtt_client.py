import paho.mqtt.client as mqtt
import pytest

from app.core.settings import Settings
from app.mqtt.client import MqttSubscriber


class RecordingClient:
    def __init__(self, *args, **kwargs) -> None:
        self.credentials: tuple[str, str] | None = None

    def username_pw_set(self, username: str, password: str | None = None) -> None:
        self.credentials = (username, password)


@pytest.fixture
def recording_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mqtt, "Client", RecordingClient)


def make_subscriber(**credentials: str) -> MqttSubscriber:
    return MqttSubscriber(
        host="mosquitto",
        port=1883,
        topic="weather/+/+",
        client_id="weather-station-backend",
        on_event=lambda event: None,
        **credentials,
    )


@pytest.mark.usefixtures("recording_client")
def test_subscriber_sends_the_configured_credentials() -> None:
    subscriber = make_subscriber(username="weather-station-backend", password="broker-password")

    assert subscriber._client.credentials == ("weather-station-backend", "broker-password")


@pytest.mark.usefixtures("recording_client")
def test_subscriber_connects_anonymously_without_a_username() -> None:
    subscriber = make_subscriber()

    assert subscriber._client.credentials is None


def test_settings_keep_the_broker_password_out_of_their_representation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEATHER_MQTT_USERNAME", "weather-station-backend")
    monkeypatch.setenv("WEATHER_MQTT_PASSWORD", "broker-password")

    settings = Settings(_env_file=None)

    assert settings.mqtt_username == "weather-station-backend"
    assert settings.mqtt_password.get_secret_value() == "broker-password"
    assert "broker-password" not in repr(settings)
