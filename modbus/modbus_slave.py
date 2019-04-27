import logging
import sys
import paho.mqtt.client as mqtt
from pymodbus.server.async import StartTcpServer
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.transaction import ModbusRtuFramer, ModbusAsciiFramer
from common.config import get_config, get_config_default

logger_name = 'modbus_mqtt'

class Modbus:
    _log = None
    _config = None
    _modbus_callback = None

    store = None
    context = None
    identity = None

    def __init__(self, config, modbus_callback):
        self._log = logging.getLogger(logger_name)
        self._config = config

        self._log.info("Initializing Modbus slave")
        self._modbus_callback = modbus_callback

        self.store = ModbusSlaveContext(
           di = ModbusSequentialDataBlock(1, [0]*192)
        )

        self.context = ModbusServerContext(slaves=self.store, single=True)

        self.identity = ModbusDeviceIdentification()
        self.identity.VendorName  = 'blbecek.net'
        self.identity.ProductCode = 'PARADOX'
        self.identity.VendorUrl   = 'https://github.com/czertique/paradox-modbus/'
        self.identity.ProductName = 'paradox-modbus interface'
        self.identity.ModelName   = 'paradox-modbus interface'
        self.identity.MajorMinorRevision = '1.0'
    
    def setValue(self, addr, value):
        self._log.debug("modbus.setValue: addr=%s, value=%s" % (addr, value))
        fx=0x2
        self.context.setValues(fx, addr, value)

    def loop(self):
        port = get_config(self._config, "modbus.port")
        listen_addr = get_config(self._config, "modbus.listen_addr")
        StartTcpServer(self.context, identity=self.identity, address=(listen_addr, port))

    def process_queue_event(self, event_type, event_input, event_data):
        # self._log.debug("Processing queue event: %s / %s / %s" % (type, input, data))
        slave_id = 0x00
        ctx = self.context[slave_id]
        if event_type == "zone":
            try:
                zone_number = event_data["data"]["id"]
                zone_open = event_data["data"]["open"]
                zone_tamper = event_data["data"]["tamper"]

                modbus_open_addr = zone_number-1

                self._log.info("Processing zone %d event" % (zone_number))

                fx = 0x02
                ctx.setValues(fx, modbus_open_addr, [zone_open*1])
            except:
                self._log.error("Unable to parse zone event: %s" % (event_data))


    def close(self):
            self._log.info("Destroying Modbus slave")
