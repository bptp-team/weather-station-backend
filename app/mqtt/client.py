import logging
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Thread

import paho.mqtt.client as mqtt

from app.mqtt.parser import parse_message

logger = logging.getLogger(__name__)


class MqttSubscriber:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        topic: str,
        client_id: str,
        on_event: Callable,
    ) -> None:
        self._topic = topic
        self._on_event = on_event
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._host = host
        self._port = port
        self._thread: Thread | None = None

    def start(self) -> None:
        self._client.connect(self._host, self._port)
        self._thread = Thread(target=self._client.loop_forever, name="mqtt-client", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._client.disconnect()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            logger.error("MQTT connection failed: %s", reason_code)
            return
        client.subscribe(self._topic)
        logger.info("Subscribed to MQTT topic %s", self._topic)

    def _on_message(self, client, userdata, message) -> None:
        try:
            event = parse_message(
                message.topic,
                message.payload,
                received_at=datetime.now(timezone.utc),
            )
        except ValueError:
            logger.warning("Ignoring invalid MQTT message on %s", message.topic, exc_info=True)
            return
        
        self._on_event(event)