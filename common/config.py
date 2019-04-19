import logging
import sys
import serial

logger_name = 'prt3_mqtt'
log = logging.getLogger(logger_name)

# Get configuration option from config file using path
# Example: get_config(config, "debug.enabled")
def get_config(config, path):
    try:
        _path = path.split(".")
        ret = config
        for i in _path:
            ret = ret[i]
    except:
        log.error("Unable to get configuration option: %s" % (path))
        sys.exit(1)
    else:
        return ret
