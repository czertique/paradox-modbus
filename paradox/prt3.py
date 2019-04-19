import logging
import sys
import serial
import re
import time
from common.config import get_config
from paradox.objects import *

logger_name = 'prt3_mqtt'

# PRT class
# Defines structures we can read/write on PRT3 and its operations
class PRT:
    areas = [None]*8
    zones = [None]*192
    users = [None]*999
    _config = None
    _buffer = ""
    _panel_type = None
    _sum_areas = 0
    _sum_zones = 0
    _sum_users = 0
    _ser = None
    _log = None

    def input_serial(self, buf, regex_response = None):
        self._buffer = self._buffer + buf
        self._log.debug("Received data: %s" % (buf.strip().replace('\r', ';')))
        ret = []
        if '\r' in self._buffer:
            command = self._buffer.split('\r')
            for x in range(0, len(command)-1):
                event_ret = self.parse_event(command[x], regex_response)
                if event_ret != None:
                    ret.append(event_ret)
            self._buffer = command[-1]
        return ret

    def parse_event(self, str, regex_response = None):
        self._log.debug("Parsing: %s" % (str))
        regex_event = "^G([0-9]{3})N([0-9]{3})A([0-9]{3})$"

        if (regex_response != None) and (re.search(regex_response, str)):
            rx = re.split(regex_response, str)
            return rx

        elif (re.search(regex_event, str)):
            rx = re.split(regex_event, str)
            if rx:
                cmd_group = int(rx[1])
                cmd_event = int(rx[2])
                cmd_area = int(rx[3])
                self._log.debug("Match [EVENT] gr=%d en=%d ar=%d" % (cmd_group, cmd_event, cmd_area))

                if cmd_group == 0:
                    self._log.info("Zone OK: %d / %d" % (cmd_event, cmd_area))
                    self.zones[cmd_event].open = False
                    self.zones[cmd_event].tamper = False
                    self.zones[cmd_event].fire = False

                if cmd_group == 1:
                    self._log.info("Zone open: %d / %d" % (cmd_event, cmd_area))
                    self.zones[cmd_event].open = True

                if cmd_group == 2:
                    self._log.info("Zone in tamper: %d / %d" % (cmd_event, cmd_area))
                    self.zones[cmd_event].tamper = True

                if cmd_group == 3:
                    self._log.info("Zone in fire loop trouble: %d / %d" % (cmd_event, cmd_area))
                    self.zones[cmd_event].fire = True
            return None

        else:
            self._log.debug("Unknown command: %s" % (str))
            return None

    def wait_response(self, regex):
        ret = None
        counter = 0
        while (counter < 10) and (ret == None):
            counter += 1
            serin = self._ser.readline()
            if (serin != ''):
                ret = self.input_serial(serin, regex)
                if ret != None:
                    return ret

        return None
    
    def prt3_command(self, cmd, regex):
        self._log.debug("Sending command: %s" % (cmd))
        self._ser.write(cmd + "\r")
        self._log.debug("Sent; waiting for response")
        ret = self.wait_response(regex)
        return ret
    
    def fetch_area(self, id):
        self._log.debug("Fetching area [%d]" % (id))

        # Request area label
        ret = self.prt3_command("AL%03d" % (id), "^(AL)([0-9]{3})(.{16})$")
        for area in ret:
            if area[1] == "AL":
                self.areas[id-1].name = area[3]

        # Request area status
        ret = self.prt3_command("RA%03d" % (id), "^(RA)([0-9]{3})([DAFSI])([MO])([TO])([NO])([PO])([AO])([SO])$")
        for area in ret:
            if area[1] == "RA":
                self.areas[id-1].arm_disarmed = (area[3] == 'D')
                self.areas[id-1].arm_armed = (area[3] == 'A')
                self.areas[id-1].arm_force = (area[3] == 'F')
                self.areas[id-1].arm_stay = (area[3] == 'S')
                self.areas[id-1].arm_instant = (area[3] == 'I')
                self.areas[id-1].zone_in_memory = (area[4] == 'M')
                self.areas[id-1].trouble = (area[5] == 'T')
                self.areas[id-1].not_ready = (area[6] == 'N')
                self.areas[id-1].in_programming = (area[7] == 'P')
                self.areas[id-1].in_alarm = (area[8] == 'A')
                self.areas[id-1].strobe = (area[9] == 'S')
    
    def fetch_zone(self, id):
        self._log.debug("Fetching zone [%d]" % (id))

        # Request zone label
        ret = self.prt3_command("ZL%03d" % (id), "^(ZL)([0-9]{3})(.{16})$")
        for zone in ret:
            if zone[1] == "ZL":
                self.zones[id-1].name = zone[3]

        # Request zone status
        ret = self.prt3_command("RZ%03d" % (id), "^(RZ)([0-9]{3})([COTF])([AO])([FO])([SO])([LO])$")
        for zone in ret:
            if zone[1] == "RZ":
                self.zones[id-1].open = (zone[3] == 'O')
                self.zones[id-1].tamper = (zone[3] == 'T')
                self.zones[id-1].fire = (zone[3] == 'F')
                self.zones[id-1].alarm = (zone[4] == 'A')
                self.zones[id-1].fire_alarm = (zone[5] == 'F')
                self.zones[id-1].supervision_lost = (zone[6] == 'S')
                self.zones[id-1].low_battery = (zone[7] == 'L')
    
    def fetch_user(self, id):
        self._log.debug("Fetching user [%d]" % (id))

        # Request user label
        ret = self.prt3_command("UL%03d" % (id), "^(UL)([0-9]{3})(.{16})$")
        for user in ret:
            if user[1] == "UL":
                self.users[id-1].name = user[3]

    def panel_sync(self):
        self._log.info("Fetching panel status")

        for area in self.areas:
            if area != None:
                self.fetch_area(area.id)

        for zone in self.zones:
            if zone != None:
                self.fetch_zone(zone.id)

        for user in self.users:
            if user != None:
                self.fetch_user(user.id)

    def __init__(self, config):
        self._log = logging.getLogger(logger_name)
        self._config = config
        
        # Open serial port
        try:
            serial_port = get_config(self._config, "prt3.port")
            serial_speed = int(get_config(self._config, "prt3.speed"))
        except:
            self._log.error("Invalid port configuration: %s" % (get_config(self._config, "prt3")))
            sys.exit(1)

        self._log.info("Opening serial port %s" % (serial_port))
        self._ser = serial.Serial(port=serial_port, baudrate=serial_speed, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, 
                    bytesize=serial.EIGHTBITS, timeout=0.5, xonxoff=False, rtscts=False, dsrdtr=False)

        # Load panel configuration
        cfg_panel = get_config(self._config, "panel")
    
        try:
            # Set basic config variables
            self._panel_type = cfg_panel["type"]

            # Load monitored area ranges
            for i in cfg_panel["areas"]:
                for i2 in range(i[0], i[1]+1):
                    self.areas[i2-1] = PRT_Area(i2)
                    self._sum_areas += 1

            # Load monitored zone ranges
            for i in cfg_panel["zones"]:
                for i2 in range(i[0], i[1]+1):
                    self.zones[i2-1] = PRT_Zone(i2)
                    self._sum_zones += 1

            # Load monitored user ranges
            for i in cfg_panel["users"]:
                for i2 in range(i[0], i[1]+1):
                    self.users[i2-1] = PRT_User(i2)
                    self._sum_users += 1

        except:
            self._log.error("Unable to parse panel config")
            sys.exit(1)
        
        self._log.debug("Panel object successfully initialized")
        self._log.debug("* Areas = %d; Zones = %d; Users = %d" % (self._sum_areas, self._sum_zones, self._sum_users))

        # Sync current panel status
        self.panel_sync()
    
    def close(self):
        # Close serial port before quitting
        self._log.info("Closing serial port")
        self._ser.close()

    def loop(self):
        serin = self._ser.readline()
        if (serin != ''):
            self.input_serial(serin)

