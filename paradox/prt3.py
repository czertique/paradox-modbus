import logging
import sys
import serial
import io
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
    users = [None]*1000
    _config = None
    _buffer = ""
    _panel_type = None
    _sum_areas = 0
    _sum_zones = 0
    _sum_users = 0
    _ser = None
    _serial = None
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
            self._log.info("Zone OK: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].open = False
            self.zones[event-1].tamper = False
            self.zones[event-1].fire = False
            self.zones[event-1].last_state_update = time.time()

        # Zone open
        if group == 1:
            self._log.info("Zone open: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].open = True
            self.zones[event-1].last_state_update = time.time()

        # Zone in tamper
        if group == 2:
            self._log.info("Zone in tamper: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].tamper = True
            self.zones[event-1].last_state_update = time.time()

        # Zone in fire loop trouble
        if group == 3:
            self._log.info("Zone in fire loop trouble: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].fire = True
            self.zones[event-1].last_state_update = time.time()

        if group == 23:
            self._log.info("Zone bypassed: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))

        if group == 24:
            self._log.info("Zone in alarm: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].alarm = True

        if group == 25:
            self._log.info("Zone in fire alarm: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].fire_alarm = True

        if group == 26:
            self._log.info("Zone alarm restore: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].alarm = False

        if group == 27:
            self._log.info("Zone fire alarm restore: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].fire_alarm = False

        if group == 32:
            self._log.info("Zone shutdown: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))

        if group == 33:
            self._log.info("Zone tamper: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].tamper = True

        if group == 34:
            self._log.info("Zone tamper restore: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].tamper = False

        if group == 41:
            self._log.info("Zone battery low: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].low_battery = True

        if group == 42:
            self._log.info("Zone lost supervision: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].supervision_lost = True

        if group == 43:
            self._log.info("Zone battery low restored: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].low_battery = False

        if group == 44:
            self._log.info("Zone restored supervision: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))
            self.zones[event-1].supervision_lost = False

        if group == 55:
            self._log.info("Intellizone triggered: %d/%d [%s / %s]" % (area, event, self.areas[area-1].name, self.zones[event-1].name))

        # Zone status queue notification
        if (self._event_callback) and ((0 <= group <= 3) or (23 <= group <= 27) or (32 <= group <= 34)):
            payload = {
                "type": "zone",
                "event": {
                    0: "ok",
                    1: "open",
                    2: "tamper",
                    3: "fire_loop_trouble",
                    23: "bypassed",
                    24: "alarm",
                    25: "fire_alarm",
                    26: "alarm_restore",
                    27: "fire_alarm_restore",
                    32: "shutdown",
                    33: "tamper",
                    34: "tamper_restore",
                    41: "lowbatt",
                    42: "nosupervision",
                    43: "lowbatt_restore",
                    44: "nosupervision_restore",
                    55: "intellizone_triggered"
                }[group],
                "area": area,
                "data": self.zones[event-1].getData(),
            }
            payload["timestamp"] = time.time()
            self._event_callback(payload, "zone/" + str(event))
  
    def process_nonreportable_event(self, group, event, area):
        payload = {"type": "unknown", "area": None}
        if event == 0:
            payload = {"type": "tlm_trouble", "area": area}
                    
        if event == 1:
            payload = {"type": "smoke_detector_reset", "area": area}

        if event == 2:
            payload = {"type": "arm_nodelay", "area": area}

        if event == 3:
            payload = {"type": "arm_in_stay", "area": area}

        if event == 4:
            payload = {"type": "arm_in_away", "area": area}

        if event == 5:
            payload = {"type": "fullarm_in_stay", "area": area}

        if event == 6:
            payload = {"type": "voice_access", "area": area}

        if event == 7:
            payload = {"type": "remote_access", "area": area}

        if event == 8:
            payload = {"type": "pc_comm_fail", "area": area}

        if event == 9:
            payload = {"type": "midnight", "area": area}

        if event == 10:
            payload = {"type": "ip_user_login", "area": area}

        if event == 11:
            payload = {"type": "ip_user_logout", "area": area}

        if event == 12:
            payload = {"type": "user_callup", "area": area}

        if event == 13:
            payload = {"type": "force_answer", "area": area}

        if event == 14:
            payload = {"type": "force_hangup", "area": area}
        
        self._log.info("Nonreportable event; type = %s, area = %s" % (payload["type"], payload["area"]))
        self._event_callback(payload, "nonrep")

    def process_useraccess_event(self, group, event, area):
        payload = {"type": "unknown", "user": None, "area": None}

        if group == 5:
            payload = {
                "type": "keypad_usercode_entered",
                "area": area,
                "user": self.users[event].getData() if self.users[event] else None
            }
        
        if group == 6:
            payload = {
                "type": "door_access",
                "area": area,
                "door": event
            }

        if group == 7:
            payload = {
                "type": "bypass_programming_access",
                "area": area,
                "user": event
            }

        self._log.info("User access event; type = %s, user = %s, area = %s" % (payload["type"], payload["user"]["name"] if payload["user"] else "unknown", payload["area"]))
        self._event_callback(payload, "useraccess")

    def process_delayzonealarm_event(self, group, event, area):
        payload = {
            "type": "tx_delay_zone_alarm",
            "area": area,
            "zone": event
        }
        self._log.info("TX delay zone alarm; type = %s, area = %d, zone = %d" % (payload["type"], payload["area"], payload["zone"]))
        self._event_callback(payload, "txdelayzonealarm")

    def process_arming_event(self, group, event, area):
        payload = {"type": "unknown", "user": None, "area": None, "source": None, "event": None}

        # Arm with master code / user code
        if (9 <= group <= 10):
            payload = {
                "type": "arm",
                "source": {
                    9: "mastercode",
                    10: "usercode"
                }[group],
                "area": area,
                "user": self.users[event].getData() if self.users[event] else None
            }
        
        # Arm with keyswitch
        if group == 11:
            payload = {
                "type": "arm",
                "source": "keyswitch",
                "area": area,
                "keyswitch": event,
                "user": None
            }

        # Special arming
        if group == 12:
            payload = {
                "type": "arm",
                "source": "special",
                "area": area,
                "event": {
                    0: "auto",
                    1: "winload",
                    2: "late_to_close",
                    3: "no_movement",
                    4: "partial",
                    5: "onetouch",
                    6: "_future_",
                    7: "_future_",
                    8: "invoice_module"
                }[event],
                "user": None
            }

        # Early / late arm
        if (46 <= group <= 47):
            payload = {
                "type": "arm",
                "state": {
                    46: "early",
                    47: "late"
                }[group],
                "source": "usercode",
                "area": area,
                "user": self.users[event].getData() if self.users[event] else None
            }

        self._log.info("Arming event; type = %s, source = %s, user = %s, area = %s" % (payload["type"], payload["source"], payload["user"]["name"] if payload["user"] else "unknown", payload["area"]))
        self._event_callback(payload, "arming")

    def process_disarming_event(self, group, event, area):
        payload = {"type": "unknown", "state": None, "source": None, "area": None, "user": None}

        # Disarm with master code / user code
        if (13 <= group <= 14) or (16 <= group <= 17) or (19 <= group <= 20):
            payload = {
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
                "user": self.users[event].getData() if self.users[event] else None
            }
        
        # Disarm with keyswitch
        if (group == 15) or (group == 18) or (group == 21):
            payload = {
                "type": "disarm",
                "state": {
                    15: "ok",
                    18: "after_alarm",
                    21: "during_alarm",
                }[group],
                "source": "keyswitch",
                "area": area,
                "keyswitch": event,
                "user": None
            }

        # Special disarming
        if group == 22:
            payload = {
                "type": "disarm",
                "source": "special",
                "state": None,
                "area": area,
                "event": {
                    0: "auto_cancelled",
                    1: "onetouch_instant",
                    2: "winload",
                    3: "winload_afteralarm",
                    4: "winload_cancelledalarm",
                    5: "_future_",
                    6: "_future_",
                    7: "_future_",
                    8: "invoice_module"
                }[event],
                "user": None
            }
    
        # Early / late disarm
        if (28 <= group <= 29):
            payload = {
                "type": "disarm",
                "state": {
                    28: "early",
                    29: "late"
                }[group],
                "source": "usercode",
                "area": area,
                "user": self.users[event].getData() if self.users[event] else None
            }

        self._log.info("Disarming event; type = %s, state = %s, source = %s, user = %s, area = %s" % (payload["type"], payload["state"], payload["source"], payload["user"]["name"] if payload["user"] else "unknown", payload["area"]))
        self._event_callback(payload, "arming")

    def process_special_alarm_event(self, group, event, area):
        payload = {
            "type": "special_alarm",
            "source": {
                0: "emergency_panic",
                1: "medical_panic",
                2: "fire_panic",
                3: "recent_closing",
                4: "police_code",
                5: "global_shutdown"
            }[event],
            "area": area
        }
        self._log.info("Special alarm event; type = %s, source = %s, area = %s" % (payload["type"], payload["source"], payload["area"]))
        self._event_callback(payload, "special_alarm")

    def process_duress_alarm_event(self, group, event, area):
        payload = {
            "type": "duress_alarm",
            "user": event,
            "area": area
        }
        self._log.info("Special alarm event; type = %s, user = %s, area = %s" % (payload["type"], payload["user"]["name"] if payload["user"] else "unknown", payload["area"]))
        self._event_callback(payload, "duress_alarm")

    def process_special_tamper_event(self, group, event, area):
        payload = {
            "type": "special_tamper",
            "source": "keypad_lockout",
            "area": area
        }
        self._log.info("Special tamper event; type = %s, source = %s, area = %s" % (payload["type"], payload["source"], payload["area"]))
        self._event_callback(payload, "special_tamper")

    def process_trouble_event(self, group, event, area):
        payload = {
            "type": "trouble",
            "event": {
                36: "trouble",
                37: "restore"
            }[group],
            "source": {
                0: "tlm",
                1: "ac_failure",
                2: "battery_failure",
                3: "aux_current_limit",
                4: "bell_current_limit",
                5: "bell_absent",
                6: "clock",
                7: "global_fire_loop",
                8: "panel_tamper"
            }[event],
            "area": area
        }

        self._log.info("Trouble event; event = %s, source = %s, area = %s" % (payload["event"], payload["source"], payload["area"]))
        self._event_callback(payload, "trouble")

    def process_module_event(self, group, event, area):
        payload = {
            "type": "module_trouble",
            "event": {
                38: "trouble",
                39: "restore"
            }[group],
            "source": {
                0: "combus_fault",
                1: "tamper",
                2: "memory_error",
                3: "tlm_trouble",
                4: "fail_to_communicate",
                5: "printer_fault",
                6: "ac_failure",
                7: "battery_failure",
                8: "aux_failure"
            }[event],
            "area": area
        }

        self._log.info("Module trouble event; event = %s, source = %s, area = %s" % (payload["event"], payload["source"], payload["area"]))
        self._event_callback(payload, "module_trouble")

    def process_comm_fail_event(self, group, event, area):
        payload = {
            "type": "comm_fail_telephone",
            "telephone_number": event,
            "area": area
        }

        self._log.info("Fail to Communicate on telephone number; telephone_number = %s, area = %s" % (payload["event"], payload["area"]))
        self._event_callback(payload, "comm_fail_telephone")

    def process_special_event(self, group, event, area):
        payload = {
            "type": "special_event",
            "event": {
                0: "full_startup",
                1: "software_reset",
                2: "test_report",
                3: "future_use",
                4: "winload_in",
                5: "winload_out",
                6: "installer_programming_in",
                7: "installer_programming_out"
            }[event],
            "area": area
        }

        self._log.info("Special event; event = %s, area = %s" % (payload["event"], payload["area"]))
        self._event_callback(payload, "special_event")

    def process_utility_key_event(self, group, event, area):
        payload = {
            "type": "utility_key",
            "utility_key": event,
            "area": area
        }

        self._log.info("Utility key event; utility_key = %s, area = %s" % (payload["event"], payload["area"]))
        self._event_callback(payload, "utility_key")

    def process_door_event(self, group, event, area):
        payload = {
            "type": "door",
            "event": {
                49: "request_exit",
                50: "access_denied",
                51: "left_open_alarm",
                52: "forced_open_alarm",
                53: "left_open_restore",
                54: "forced_open_restore"
            }[group],
            "door": event,
            "area": area
        }

        self._log.info("Door event; event = %s, door = %s, area = %s" % (payload["event"], payload["door"], payload["area"]))
        self._event_callback(payload, "door")

    def process_combus_event(self, group, event, area):
        payload = {
            "type": "combus",
            "event": {
                58: "module_assigned",
                59: "module_removed"
            }[group],
            "module_addr": event,
            "module": area
        }

        self._log.info("Combus module event; event = %s, module_addr = %s, module = %s" % (payload["event"], payload["module_addr"], payload["module"]))
        self._event_callback(payload, "combus")

    def process_future_use_event(self, group, event, area):
        payload = {
            "type": "future_use",
            "group": group,
            "event": event,
            "area": area
        }

        self._log.info("_FUTURE USE_ event; group = %s, event = %s, area = %s" % (payload["group"], payload["event"], payload["area"]))
        self._event_callback(payload, "future_use")

    def process_access_granted_event(self, group, event, area):
        payload = {
            "type": "access",
            "event": {
                62: "granted",
                63: "denied"
            }[group],
            "user": event,
            "area": area
        }

        self._log.info("Access granted/denied event; event = %s, user = %s, area = %s" % (payload["event"], payload["user"]["name"] if payload["user"] else "unknown", payload["area"]))
        self._event_callback(payload, "access")

    def process_status_event(self, group, event, area):
        payload = {"type": "status", "event": None, "area": None, "kind": None}
        
        if group == 64:
            payload = {
                "type": "status",
                "event": {
                    0: "arm",
                    1: "arm",
                    2: "arm",
                    3: "arm",
                    4: "alarm",
                    5: "alarm",
                    6: "alarm",
                    7: "alarm"
                }[event],
                "kind": {
                    0: "normal",
                    1: "force",
                    2: "stay",
                    3: "instant",
                    4: "strobe",
                    5: "silent",
                    6: "audible",
                    7: "fire"
                }[event],
                "area": area
            }

        if group == 65:
            payload = {
                "type": "status",
                "event": {
                    0: "ready",
                    1: "exit_delay",
                    2: "entry_delay",
                    3: "system_trouble",
                    4: "alarm_in_memory",
                    5: "zones_bypassed",
                    6: "bypass_master_installer_programming",
                    7: "keypad_lockout"
                }[event],
                "kind": None,
                "area": area
            }

        if group == 66:
            payload = {
                "type": "status",
                "event": {
                    0: "intellizone_delay_enganged",
                    1: "fire_delay_enganged",
                    2: "auto_arm",
                    3: "voice_arm",
                    4: "tamper",
                    5: "zone_low_battery",
                    6: "fire_loop_trouble",
                    7: "zone_supervision_trouble"
                }[event],
                "kind": None,
                "area": area
            }

        self._log.info("System status event; type = %s, event = %s, kind = %s, area = %s" % (payload["type"], payload["event"], payload["kind"], payload["area"]))
        self._event_callback(payload, "status")


    def process_unknown_event(self, str):
        self._log.info("Unknown event command: %s" % (str))
        self._event_callback({
            "type": "unknown_event",
            "data": str
        }, "unknown")

    def process_unknown_command(self, str):
        self._log.info("Unknown command: %s" % (str))
        self._event_callback({
            "type": "unknown_command",
            "data": str
        }, "unknown")

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
                if (0 <= cmd_group <= 3) or (23 <= cmd_group <= 27) or (32 <= cmd_group <= 34) or (41 <= cmd_group <= 44) or (cmd_group == 55):
                    self.process_zone_event(cmd_group, cmd_event, cmd_area)

                # Non-reportable events
                elif cmd_group == 4:
                    self.process_nonreportable_event(cmd_group, cmd_event, cmd_area)
                
                # User code entered on keypad
                elif (5 <= cmd_group <= 7):
                    self.process_useraccess_event(cmd_group, cmd_event, cmd_area)

                # TX Delay Zone Alarm
                elif cmd_group == 8:
                    self.process_delayzonealarm_event(cmd_group, cmd_event, cmd_area)

                elif (9 <= cmd_group <= 12) or (46 <= cmd_group <= 47):
                    self.process_arming_event(cmd_group, cmd_event, cmd_area)

                elif (13 <= cmd_group <= 22) or (28 <= cmd_group <= 29):
                    self.process_disarming_event(cmd_group, cmd_event, cmd_area)
                
                elif cmd_group == 30:
                    self.process_special_alarm_event(cmd_group, cmd_event, cmd_area)
                
                elif cmd_group == 31:
                    self.process_duress_alarm_event(cmd_group, cmd_event, cmd_area)

                elif cmd_group == 35:
                    self.process_special_tamper_event(cmd_group, cmd_event, cmd_area)

                elif (36 <= cmd_group <= 37):
                    self.process_trouble_event(cmd_group, cmd_event, cmd_area)

                elif (38 <= cmd_group <= 39):
                    self.process_module_event(cmd_group, cmd_event, cmd_area)

                elif cmd_group == 40:
                    self.process_comm_fail_event(cmd_group, cmd_event, cmd_area)

                elif cmd_group == 45:
                    self.process_special_event(cmd_group, cmd_event, cmd_area)

                elif cmd_group == 48:
                    self.process_utility_key_event(cmd_group, cmd_event, cmd_area)

                elif (49 <= cmd_group <= 54):
                    self.process_door_event(cmd_group, cmd_event, cmd_area)

                elif (58 <= cmd_group <= 59):
                    self.process_combus_event(cmd_group, cmd_event, cmd_area)

                elif (60 <= cmd_group <= 61):
                    self.process_future_use_event(cmd_group, cmd_event, cmd_area)

                elif (62 <= cmd_group <= 63):
                    self.process_access_granted_event(cmd_group, cmd_event, cmd_area)

                elif (64 <= cmd_group <= 66):
                    self.process_status_event(cmd_group, cmd_event, cmd_area)

                else:
                    self.process_unknown_event(str)

            return None

        else:
            self.process_unknown_command(str)
            return None

    def serial_readline(self, timeout = 0.5):
        timer_start = time.time()
        ret = ""
        eol = False
        while ((time.time() - timer_start <= timeout) and (not eol)):
            readbytes = self._ser.read()
            if len(readbytes) > 0:
                ret += readbytes
                if readbytes == '\r':
                    eol = True
        return ret
    
    def wait_response(self, regex):
        ret = None
        counter = 0
        while (counter < 10) and (ret == None):
            counter += 1
            serin = self.serial_readline()
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
        name_update = get_config(self._config, "prt3.refresh.names") * 60

        # Request area label
        if (self.areas[id-1].last_name_update == None) or ((time.time() - self.areas[id-1].last_name_update) >= name_update):
            ret = self.prt3_command("AL%03d" % (id), "^(AL)([0-9]{3})(.{16})$")
            for area in ret:
                if area[1] == "AL":
                    self.areas[id-1].name = area[3].strip()
                    self.areas[id-1].last_name_update = time.time()

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
                self.areas[id-1].last_state_update = time.time()
    
    def fetch_zone(self, id):
        self._log.debug("Fetching zone [%d]" % (id))
        name_update = get_config(self._config, "prt3.refresh.names") * 60

        # Request zone label
        if (self.zones[id-1].last_name_update == None) or ((time.time() - self.zones[id-1].last_name_update) >= name_update):
            ret = self.prt3_command("ZL%03d" % (id), "^(ZL)([0-9]{3})(.{16})$")
            for zone in ret:
                if zone[1] == "ZL":
                    self.zones[id-1].name = zone[3].strip()
                    self.zones[id-1].last_name_update = time.time()

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
                self.zones[id-1].last_state_update = time.time()

    def fetch_user(self, id):
        self._log.debug("Fetching user [%d]" % (id))

        self.users[0].name = "Master Technician"

        # Request user label
        ret = self.prt3_command("UL%03d" % (id), "^(UL)([0-9]{3})(.{16})$")
        for user in ret:
            if user[1] == "UL":
                self.users[id].name = user[3].strip()
                self.users[id].last_name_update = time.time()

    def panel_sync(self):
        self._log.debug("Panel sync poll")
        area_update = get_config(self._config, "prt3.refresh.area") * 60
        zone_update = get_config(self._config, "prt3.refresh.zone") * 60
        user_update = get_config(self._config, "prt3.refresh.user") * 60

        for area in self.areas:
            if (area != None) and ( (area.last_state_update == None) or (time.time() - area.last_state_update >= area_update) ):
                self.fetch_area(area.id)

        for zone in self.zones:
            if (zone != None) and ( (zone.last_state_update == None) or (time.time() - zone.last_state_update >= zone_update) ):
                self.fetch_zone(zone.id)

        for user in self.users:
            if (user != None) and (user.id != 0) and ( (user.last_name_update == None) or (time.time() - user.last_name_update >= user_update) ):
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
                    bytesize=serial.EIGHTBITS, timeout=0.1, xonxoff=False, rtscts=False, dsrdtr=False)

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
            self.users[0] = PRT_User(0)
            for i in cfg_panel["users"]:
                for i2 in range(i[0], i[1]+1):
                    self.users[i2] = PRT_User(i2)
                    self._sum_users += 1

        except:
            self._log.error("Unable to parse panel config")
            sys.exit(1)
        
        self._log.debug("Panel object successfully initialized")
        self._log.debug("* Areas = %d; Zones = %d; Users = %d" % (self._sum_areas, self._sum_zones, self._sum_users))

    def close(self):
        # Close serial port before quitting
        self._log.info("Closing serial port")
        self._ser.close()

    def loop(self):
        serin = self.serial_readline()
        if (serin != ''):
            self.input_serial(serin)

