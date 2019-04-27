import logging
import sys
from common.config import get_config, get_config_default
import paho.mqtt.client as mqtt

logger_name = 'modbus_mqtt'

class Client:
    _log = None
    _config = None
    _client = None
    _msg_callback = None

    client_name = None

    def _on_connect(self, client, userdata, flags, rc):
        self._log.info("Connected to queue with result code %d" % (rc))

        req_topic_events = get_config(self._config, "queue.queues.events") + "/#"
        req_topic_broadcasts = get_config(self._config, "queue.queues.broadcasts") + "/#"
        req_topic_responses = get_config(self._config, "queue.queues.responses") + "/" + self.client_name+ "/#"

        self._log.info("Subscribing to topic: %s" % (req_topic_events))
        self._log.info("Subscribing to topic: %s" % (req_topic_broadcasts))
        self._log.info("Subscribing to topic: %s" % (req_topic_responses))
        client.subscribe(req_topic_events)
        client.subscribe(req_topic_broadcasts)
        client.subscribe(req_topic_responses)

    def _on_message(self, client, userdata, msg):
        if self._msg_callback:
            self._msg_callback(userdata, msg)

    def send_request(self, payload, topic = None):
        try:
            _topic = get_config(self._config, "queue.queues.requests") + (("/" + topic) if topic else "")
            self._client.publish(_topic, payload)
        except:
            self._log.error("Unable to send MQTT request")

    def __init__(self, config, msg_callback):
        self._log = logging.getLogger(logger_name)
        self._config = config
        self.client_name = get_config(config, "queue.client_name")

        self._client = mqtt.Client(client_id = self.client_name)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        tls_enabled = False
        if (get_config_default(config, "queue.tls", False)):
            tls_enabled = get_config_default(config, "queue.tls.enabled", False)
            tls_capath = get_config_default(config, "queue.tls.capath", None)
            tls_cert = get_config(config, "queue.tls.cert")
            tls_key = get_config(config, "queue.tls.key")
            tls_insecure = get_config_default(config, "queue.tls.disableHostnameCheck", False)
        else:
            self._log.warning("TLS not configured, not using encryption")
        
        if tls_enabled:
            self._client.tls_set(ca_certs = tls_capath, certfile = tls_cert, keyfile = tls_key)
            if tls_insecure:
                self._client.tls_insecure_set(True)
        
        self._log.info("Initializing MQTT client")
        self._client.connect_async(get_config(self._config, "queue.host"), get_config(self._config, "queue.port"))

        self._msg_callback = msg_callback
        self._client.loop_start()

    def close(self):
        self._log.info("Disconnecting from message broker")
        self._client.disconnect()
