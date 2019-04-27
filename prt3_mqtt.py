#!/usr/bin/env python

import logging
import sys
import time
import json
import signal
import argparse
import re
from paradox.prt3 import PRT
from paradox.queue_client import Client
from common.config import get_config
from threading import Lock

# Global constants
logger_name = 'prt3_mqtt'

# Global variables
config = None
can_exit = False
last_sync = None

serial_lock = Lock()

# Parse arguments
parser = argparse.ArgumentParser(description='Paradox PRT3 to MQTT interface')
parser.add_argument('-d', '--debug', help='Enable debugging (set loglevel + start ptvsd), use twice to wait for debugger to attach (-dd)', action='count')
parser.add_argument('-c', '--config', help='Config file', action='store', default="/usr/local/etc/paradox-modbus/config_prt3.json")
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
    global prt
    global queue
    if (not can_exit):
        log.info("Caught ^C; exitting")
        can_exit = True
    else:
        log.info("Caught second ^C; force exitting")
        if 'prt' in globals():
            prt.close()
        if 'queue' in globals():
            queue.close()
        exit(0)
signal.signal(signal.SIGINT, exit_gracefully)   

# Process MQTT request
def process_request(client_id, request_id, request, topic = None):
    ret = {
        "clientid": client_id,
        "reqid": request_id,
        "topic": topic
    }
    return ret

def process_arming_request(request):
    global prt
    
    response = None

    req_code = None
    if "code" in request:
        req_code = request["code"]

    if ("arm" in request) and (req_code):
        for req in request["arm"]:
            req_area = req["area"]
            req_armtype = req["arm_type"]
            cmd = str("AA%03d%s%s" % (req_area, {
                    "regular": "A",
                    "force": "F",
                    "stay": "S",
                    "instant": "I"
                }[req_armtype],
                req_code))
            regex = "^"+cmd[:5]+"&(ok|fail)$"
            log.info("Processing arm request: %s" % (cmd))
            prt_response = prt.prt3_command(cmd, regex)
            response = {
                "arm": {
                    "area": req_area,
                    "result": prt_response
                }
            }

    if "quickarm" in request:
        for req in request["quickarm"]:
            req_area = req["area"]
            req_armtype = req["arm_type"]
            cmd = str("AQ%03d%s" % (req_area, {
                    "regular": "A",
                    "force": "F",
                    "stay": "S",
                    "instant": "I"
                }[req_armtype]))
            regex = "^"+cmd[:5]+"&(ok|fail)$"
            log.info("Processing quick arm request: %s" % (cmd))
            prt_response = prt.prt3_command(cmd, regex)
            response = {
                "quickarm": {
                    "area": req_area,
                    "result": prt_response
                }
            }

    if ("disarm" in request) and (req_code):
        for req in request["disarm"]:
            req_area = req["area"]
            cmd = str("AD%03d%s" % (req_area, req_code))
            regex = "^"+cmd[:5]+"&(ok|fail)$"
            log.info("Processing disarm request: %s" % (cmd))
            prt_response = prt.prt3_command(cmd, regex)
            response = {
                "disarm": {
                    "area": req_area,
                    "result": prt_response
                }
            }
    
    return response

def process_panic_request(request):
    global prt

    response = None
    
    if ("type" in request) and ("area" in request):
        req_type = request["type"]
        req_area = request["area"]

        cmd = str("P%s%03d" % ({
                "emergency": "E",
                "medical": "M",
                "fire": "F"
            }[req_type], req_area))
        regex = "^"+cmd[:5]+"&(ok|fail)$"
        log.info("Processing panic request: %s" % (cmd))
        prt_response = prt.prt3_command(cmd, regex)
        response = {
                "area": req_area,
                "result": prt_response
        }

    return response

def process_smoke_reset_request(request):
    global prt

    response = None
    
    if ("area" in request):
        req_area = request["area"]

        cmd = str("SR%03d" % (req_area))
        regex = "^"+cmd[:5]+"&(ok|fail)$"
        log.info("Processing smoke reset request: %s" % (cmd))
        prt_response = prt.prt3_command(cmd, regex)
        response = {
                "area": req_area,
                "result": prt_response
        }

    return response

def process_utility_key_request(request):
    global prt

    response = None
    
    if ("id" in request):
        req_id = request["id"]

        cmd = str("UK%03d" % (req_id))
        regex = "^"+cmd[:5]+"&(ok|fail)$"
        log.info("Processing utility key request: %s" % (cmd))
        prt_response = prt.prt3_command(cmd, regex)
        response = {
                "id": req_id,
                "result": prt_response
        }

    return response

def process_virtual_input_request(request):
    global prt

    response = None
    
    if ("id" in request) and ("state" in request):
        req_id = request["id"]
        req_state = {
                True: "O",
                False: "C"
            }[request["state"]]

        cmd = str("V%s%03d" % (req_state, req_id))
        regex = "^"+cmd[:5]+"&(ok|fail)$"
        log.info("Processing virtual input request: %s" % (cmd))
        prt_response = prt.prt3_command(cmd, regex)
        response = {
                "id": req_id,
                "result": prt_response
        }

    return response

# MQTT callback (process request via PRT3)
def mqtt_callback(userdata, msg):
    serial_lock.acquire()

    try:
        payload = json.loads(msg.payload)

        client_id = payload["clientid"]
        request_id = payload["reqid"]

        for request in payload["request"]:
            topic_root = get_config(config, "queue.queues.requests")
            topic_regex = "^" + topic_root + "/([^/]+)/([^/]+)$"
            if (re.search(topic_regex, msg.topic)):
                rx = re.split(topic_regex, msg.topic)
                topic_user = rx[1]
                topic_operation = rx[2]
                log.debug("Received MQTT request [user = %s; operation = %s; topic = %s, client_id = %s, request_id = %s]" % (topic_user, topic_operation, msg.topic, client_id, request_id))

                ret = None
                response_topic = None
                
                if topic_operation == "arming":
                    ret = process_arming_request(request)
                    ret["client_id"] = client_id
                    ret["request_id"] = request_id
                    response_topic = topic_user + "/arming"

                elif topic_operation == "panic":
                    ret = process_panic_request(request)
                    ret["client_id"] = client_id
                    ret["request_id"] = request_id
                    response_topic = topic_user + "/panic"

                elif topic_operation == "smokereset":
                    ret = process_smoke_reset_request(request)
                    ret["client_id"] = client_id
                    ret["request_id"] = request_id
                    response_topic = topic_user + "/smokereset"

                elif topic_operation == "utilitykey":
                    ret = process_utility_key_request(request)
                    ret["client_id"] = client_id
                    ret["request_id"] = request_id
                    response_topic = topic_user + "/utilitykey"

                elif topic_operation == "vinput":
                    ret = process_virtual_input_request(request)
                    ret["client_id"] = client_id
                    ret["request_id"] = request_id
                    response_topic = topic_user + "/vinput"

                if ret:
                    queue.send_response(json.dumps(ret), response_topic)
            else:
                log.warn("Invalid MQTT request topic [topic = %s; client_id = %s; request_id = %s]" % (msg.topic, client_id, request_id))

    except:
        log.warn("Invalid MQTT request received: %s" % (msg.payload))

    serial_lock.release()

# PRT3 event callback (send message to MQTT)
def prt3_event_callback(event, topic = None):
    queue.send_event(json.dumps(event), topic)

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

# Init MQTT queue and set callback
queue = Client(config, mqtt_callback)

# Init PRT3 processor and set callback
prt = PRT(config, prt3_event_callback)

# Main loop
while (not can_exit):
    serial_lock.acquire()
    if (last_sync == None) or ((time.time() - last_sync) >= 10):
        prt.panel_sync()
        last_sync = time.time()
    prt.loop()
    serial_lock.release()

queue.close()
prt.close()
