#!/usr/bin/env python

import logging
import sys
import time
import json
import signal
import argparse
from paradox.prt3 import PRT
from common.config import get_config
# from paradox.objects import *
from q.client import Client
#from types import SimpleNamespace
# import datetime

# Global constants
logger_name = 'prt3_mqtt'
config_filename = 'config.json'

# Global variables
config = None
can_exit = False
last_sync = None

# Parse arguments
parser = argparse.ArgumentParser(description='Paradox PRT3 to MQTT interface')
parser.add_argument('-d', '--debug', help='Enable debugging (set loglevel + start ptvsd), use twice to wait for debugger to attach (-dd)', action='count')
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
def exit_gracefully(sig, frame):
    global can_exit
    log.info("Caught ^C; exitting")
    can_exit = True
signal.signal(signal.SIGINT, exit_gracefully)   

# Process MQTT request
def process_request(client_id, request_id, request):
    ret = {
        "clientid": client_id,
        "reqid": request_id
    }
    # ret.huhuhu = "hahaha"
    return ret

# MQTT callback (process request via PRT3)
def mqtt_callback(userdata, msg):
    try:
        payload = json.loads(msg.payload)

        client_id = payload["clientid"]
        request_id = payload["reqid"]

        for request in payload["request"]:
            req_type = request["type"]
            ret = process_request(client_id, request_id, request)
            queue.send_response(client_id, request_id, json.dumps(ret))

            log.info("Received MQTT request [topic = %s; client_id = %s; request_id = %s]: %s" % (msg.topic, client_id, request_id, req_type))

    except:
        log.warning("Invalid MQTT request received: %s" % (msg.payload))

# PRT3 event callback (send message to MQTT)
def prt3_event_callback(event):
    queue.send_event(json.dumps(event))

# Read config file
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
    log.info("Invalid logging level configured; setting INFO")
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

# Init MQTT queue and set callback
queue = Client(config, mqtt_callback)

# Init PRT3 processor and set callback
prt = PRT(config, prt3_event_callback)

# Main loop
while (not can_exit):
    if (last_sync == None) or ((time.time() - last_sync) >= 10):
        prt.panel_sync()
        last_sync = time.time()
    prt.loop()

prt.close()
