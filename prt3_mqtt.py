#!/usr/bin/env python

import logging
import sys
import time
import json
import signal
from paradox.prt3 import PRT
from common.config import get_config
# from paradox.objects import *
from q.client import Client
#from types import SimpleNamespace

# Global constants
logger_name = 'prt3_mqtt'
config_filename = 'config.json'

# Global variables
config = None
can_exit = False

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

def process_request(client_id, request_id, request):
    #ret = SimpleNamespace(
     #     clientid = client_id,
      #    reqid = request_id
       # )
    #ret = lambda: None
    #ret.clientid = client_id
    #ret.reqid = request_id
    ret = {
        "clientid": client_id,
        "reqid": request_id
    }
    return ret

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

def prt3_event_callback(event):
    queue.send_event(json.dumps(event))

# Read config file
try:
    with open (config_filename, "r") as config_file:
        config = json.loads(config_file.read())
except:
    type, value, traceback = sys.exc_info()
    log.error("Unable to read configuration: %s" % (value))

# Start debugging interface if enabled
# Wait for debugger if enabled
if get_config(config, "debug.enabled"):
    log.debug("Debugging enabled")
    import ptvsd
    ptvsd.enable_attach(address=('0.0.0.0', 3000), redirect_output=True)
    if get_config(config, "debug.wait"):
        log.debug("Waiting for debugger to attach")
        ptvsd.wait_for_attach()

queue = Client(config, mqtt_callback)
prt = PRT(config, prt3_event_callback)

while (not can_exit):
    prt.loop()

prt.close()
