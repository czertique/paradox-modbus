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
    _event_callback = None

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

    def process_zone_event(self, group, event, area):
        # Zone OK
        if group == 0:
            self._log.info("Zone OK: %d / %d" % (event, area))
            self.zones[event-1].open = False
            self.zones[event-1].tamper = False
            self.zones[event-1].fire = False

        # Zone open
        if group == 1:
            self._log.info("Zone open: %d / %d" % (event, area))
            self.zones[event-1].open = True

        # Zone in tamper
        if group == 2:
            self._log.info("Zone in tamper: %d / %d" % (event, area))
            self.zones[event-1].tamper = True

        # Zone in fire loop trouble
        if group == 3:
            self._log.info("Zone in fire loop trouble: %d / %d" % (event, area))
            self.zones[event-1].fire = True

        # Zone status queue notification
        if (self._event_callback) and (0 <= group <= 3):
            event = {
                "type": "zone",
                "event": {
                    0: "ok",
                    1: "open",
                    2: "tamper",
                    3: "fire_loop_trouble",
                }[group],
                "area": area,
                "data": self.zones[event-1].getData(),
            }
            self._event_callback(event)
  
    def process_nonreportable_event(self, group, event, area):
        if event == 0:
            self._event_callback({"type": "tlm_trouble", "area": area})
                    
        if event == 1:
            self._event_callback({"type": "smoke_detector_reset", "area": area})

        if event == 2:
            self._event_callback({"type": "arm_nodelay", "area": area})

        if event == 3:
            self._event_callback({"type": "arm_in_stay", "area": area})

        if event == 4:
            self._event_callback({"type": "arm_in_away", "area": area})

        if event == 5:
            self._event_callback({"type": "fullarm_in_stay", "area": area})

        if event == 6:
            self._event_callback({"type": "voice_access", "area": area})

        if event == 7:
            self._event_callback({"type": "remote_access", "area": area})

        if event == 8:
            self._event_callback({"type": "pc_comm_fail", "area": area})

        if event == 9:
            self._event_callback({"type": "midnight", "area": area})

        if event == 10:
            self._event_callback({"type": "ip_user_login", "area": area})

        if event == 11:
            self._event_callback({"type": "ip_user_logout", "area": area})

        if event == 12:
            self._event_callback({"type": "user_callup", "area": area})

        if event == 13:
            self._event_callback({"type": "force_answer", "area": area})

        if event == 14:
            self._event_callback({"type": "force_hangup", "area": area})

    def process_useraccess(self, group, event, area):
        if group == 5:
            self._event_callback({
                "type": "keypad_usercode_entered",
                "area": area,
                "user": self.users[event-1].getData()
                })
        
        if group == 6:
            self._event_callback({
                "type": "door_access",
                "area": area,
                "door": event
            })

        if group == 7:
            self._event_callback({
                "type": "bypass_programming_access",
                "area": area,
                "user": event
            })

    def process_delayzonealarm(self, group, event, area):
            self._event_callback({
                "type": "tx_delay_zone_alarm",
                "area": area,
                "zone": event
            })

    def process_arming(self, group, event, area):
        # Arm with master code / user code
        if (9 <= group <= 10):
            self._event_callback({
                "type": "arm",
                "source": {
                    9: "mastercode",
                    10: "usercode"
                }[group],
                "area": area,
                "user": event
            })
        
        # Arm with keyswitch
        if group == 11:
            self._event_callback({
                "type": "arm",
                "source": "keyswitch",
                "area": area,
                "keyswitch": event
            })

        # Special arming
        if group == 12:
            self._event_callback({
                "type": "arm",
                "source": "keyswitch",
                "area": area,
                "keyswitch": event
            })

    def process_disarming(self, group, event, area):
        # Disarm with master code / user code
        if (13 <= group <= 14) or (16 <= group <= 17) or (19 <= group <= 20):
            self._event_callback({
                "type": "disarm",
                "state": {
                    13: "ok",
                    14: "ok",
                    16: "after_alarm",
                    17: "after_alarm",
                    19: "during_alarm",
                    20: "during_alarm"
                }[group],
                "source": {
                    13: "mastercode",
                    14: "usercode",
                    16: "mastercode",
                    17: "usercode",
                    19: "mastercode",
                    20: "usercode"
                }[group],
                "area": area,
                "user": event
            })
        
        # Disarm with keyswitch
        if (group == 15) or (group == 18) or (group == 21):
            self._event_callback({
                "type": "disarm",
                "state": {
                    15: "ok",
                    18: "after_alarm",
                    21: "during_alarm",
                }[group],
                "source": "keyswitch",
                "area": area,
                "keyswitch": event
            })

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

                # Zone events
                if (0 <= cmd_group <= 3):
                    self.process_zone_event(cmd_group, cmd_event, cmd_area)

                # Non-reportable events
                if cmd_group == 4:
                    self.process_nonreportable_event(cmd_group, cmd_event, cmd_area)
                
                # User code entered on keypad
                if (5 <= cmd_group <= 7):
                    self.process_useraccess(cmd_group, cmd_event, cmd_area)

                # TX Delay Zone Alarm
                if cmd_group == 8:
                    self.process_delayzonealarm(cmd_group, cmd_event, cmd_area)

                if (9 <= cmd_group <= 11):
                    self.process_arming(cmd_group, cmd_event, cmd_area)

                if (13 <= cmd_group <= 21):
                    self.process_disarming(cmd_group, cmd_event, cmd_area)

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

    def __init__(self, config, event_callback):
        self._log = logging.getLogger(logger_name)
        self._config = config
        self._event_callback = event_callback
        
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

