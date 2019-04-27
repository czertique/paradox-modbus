#!/usr/bin/env python

import logging
import sys
import time
import json
import signal
import argparse
import re
from common.config import get_config
from modbus.queue_client import Client
from modbus.modbus_slave import Modbus
from threading import Lock

# Global constants
logger_name = 'modbus_mqtt'

# Global variables
config = None
can_exit = False

# Parse arguments
parser = argparse.ArgumentParser(description='Paradox PRT3 to MQTT interface')
parser.add_argument('-d', '--debug', help='Enable debugging (set loglevel + start ptvsd), use twice to wait for debugger to attach (-dd)', action='count')
parser.add_argument('-c', '--config', help='Config file', action='store', default="/usr/local/etc/paradox-modbus/config_modbus.json")
args = parser.parse_args()

# Set up logger
log = logging.getLogger(logger_name)
log.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)

# Install event handler for SIGINT to allow program to exit gracefully
#def exit_gracefully(sig, frame):
#    global can_exit
#    global queue
#    global modbus
#    if (not can_exit):
#        log.info("Caught ^C; exitting")
#        can_exit = True
#    else:
#        log.info("Caught second ^C; force exitting")
#        if 'queue' in globals():
#            queue.close()
#        if 'modbus' in globals():
#            modbus.close()
#        exit(0)
# signal.signal(signal.SIGINT, exit_gracefully)   

# Read config file
config_filename = args.config
try:
    with open (config_filename, "r") as config_file:
        config = json.loads(config_file.read())

        if (args.debug):
            config["debug"]["loglevel"] = "debug"
            config["debug"]["enabled"] = True
            if (args.debug >= 2):
                config["debug"]["wait"] = True
except:
    type, value, traceback = sys.exc_info()
    log.error("Unable to read configuration: %s" % (value))

# Set loglevel
loglevel_string = get_config(config, "debug.loglevel").upper()
try:
    loglevel = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }[loglevel_string]
    log.info("Setting loglevel: %s" % (loglevel_string))
except:
    log.warn("Invalid logging level configured; setting INFO")
    loglevel = logging.INFO

log.setLevel(loglevel)
handler.setLevel(loglevel)

# Start debugging interface if enabled
# Wait for debugger if enabled
if get_config(config, "debug.enabled"):
    log.debug("Debugging enabled")
    import ptvsd
    ptvsd.enable_attach(address=('0.0.0.0', 3000), redirect_output=True)
    if get_config(config, "debug.wait"):
        log.debug("Waiting for debugger to attach")
        ptvsd.wait_for_attach()

def mqtt_callback(userdata, msg):
    log.debug("Received MQTT message in topic %s" % (msg.topic))

    message_data = None
    try:
        message_data = json.loads(msg.payload)
    except:
        log.error("Unable to parse message from queue: %s" % (msg.payload))

    if message_data:
        # Check if incoming message is event
        topic_events = get_config(config, "queue.queues.events")
        topic_regex = "^"+topic_events+"/([^/]+)/([0-9]+)$"
        if re.search(topic_regex, msg.topic):
            rx = re.split(topic_regex, msg.topic)
            event_type = rx[1]
            event_input = rx[2]
            modbus.process_queue_event(event_type, event_input, message_data)

def modbus_callback():
    log.debug("Received Modbus request")

# Init MQTT queue and set callback
queue = Client(config, mqtt_callback)

# Init MQTT queue and set callback
modbus = Modbus(config, modbus_callback)

modbus.loop()

# while (not can_exit):
    # modbus.loop
    #time.sleep(0.5)

queue.close()
modbus.close()
