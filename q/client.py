import logging
import sys
from common.config import get_config
import paho.mqtt.client as mqtt

logger_name = 'prt3_mqtt'

class Client:
    _log = None
    _config = None
    _client = None
    _msg_callback = None

    def _on_connect(self, client, userdata, flags, rc):
        self._log.info("Connected to queue with result code "+str(rc))
        client.subscribe(get_config(self._config, "queue.queues.requests"))

    def _on_message(self, client, userdata, msg):
        if self._msg_callback:
            self._msg_callback(userdata, msg)

    def send_event(self, payload):
        try:
            self._client.publish(get_config(self._config, "queue.queues.events"), payload)
        except:
            self._log.error("Unable to send MQTT event")

    def send_broadcast(self, payload):
        try:
            self._client.publish(get_config(self._config, "queue.queues.broadcasts"), payload)
        except:
            self._log.error("Unable to send MQTT broadcast")

    def send_response(self, client_id, request_id, payload):
        try:
            self._client.publish(get_config(self._config, "queue.queues.responses"), payload)
        except:
            self._log.error("Unable to send MQTT response")

    def __init__(self, config, msg_callback):
        self._log = logging.getLogger(logger_name)
        self._config = config

        self._client = mqtt.Client(client_id = "prt3_mqtt")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._log.info("Initializing MQTT client")
        self._client.connect_async(get_config(self._config, "queue.host"), get_config(self._config, "queue.port"))

        self._msg_callback = msg_callback
        self._client.loop_start()

    def close(self):
        self._client.disconnect()
