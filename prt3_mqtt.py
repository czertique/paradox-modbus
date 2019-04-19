#!/usr/bin/env python

import logging
import sys
import time
import json
import signal
from paradox.prt3 import PRT
from common.config import get_config
from paradox.objects import *

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

# prt = PRT(get_config(config, "panel"))
prt = PRT(config)

while (not can_exit):
    prt.loop()

prt.close()
