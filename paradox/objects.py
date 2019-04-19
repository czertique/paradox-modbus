class PRT_Area:
    id = None
    name = None
    arm_disarmed = None
    arm_armed = None
    arm_force = None
    arm_stay = None
    arm_instant = None
    zone_in_memory = None
    trouble = None
    not_ready = None
    in_programming = None
    in_alarm = None
    strobe = None

    def __init__(self, id):
        self.id = id


class PRT_Zone:
    id = None
    open = None
    tamper = None
    fire = None
    name = None
    alarm = None
    fire_alarm = None
    supervision_lost = None
    low_battery = None

    def __init__(self, id):
        self.id = id

    def getData(self):
        return {
            "id": self.id,
            "name": self.name,
            "open": self.open,
            "tamper": self.tamper,
            "fire": self.fire,
            "alarm": self.alarm,
            "fire_alarm": self.fire_alarm,
            "supervision_lost": self.supervision_lost,
            "low_battery": self.low_battery
        }

class PRT_User:
    id = None
    name = None

    def __init__(self, id):
        self.id = id

    def getData(self):
        return {
            "id": self.id,
            "name": self.name
        }
