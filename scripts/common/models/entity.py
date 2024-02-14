from enum import IntEnum
from json import load

class Direction(IntEnum):
   NE = 0
   SE = 1
   SW = 2
   NW = 3

class Entity:
    with open("scripts/common/config/entity_names.json") as f:
        ENTITY_NAMES = load(f).get("entityNames",[])

    def __init__(self, data: bytes | None = None, **kwargs):
        if data:
            self.unpack(data)
        else:
            self.type = kwargs.get("type", 0)
            self.x = kwargs.get("x", 0.5)
            self.y = kwargs.get("y", 0.5)
            self.z = kwargs.get("z", 0.0)
            self.facing = kwargs.get("facing", Direction.NE)
            self.palette = kwargs.get("palette", 0)
            self.speed = kwargs.get("speed", 0)
            self.behaviour = kwargs.get("behaviour", 0)
            self.dialogue =  kwargs.get("dialogue", 0)
            self.copy_enabled = kwargs.get("copy_enabled", False)
            self.copy_source = kwargs.get("copy_source", 0)
            self.combat_enabled = kwargs.get("combat_enabled", False)
            self.pickup_enabled =  kwargs.get("pickup_enabled", False)
            self.dialogue_enabled = kwargs.get("dialogue_enabled", False)
            self.turn_enabled = kwargs.get("turn_enabled", True)
            self.friction_enabled = kwargs.get("friction_enabled", True)
            self.gravity_enabled = kwargs.get("gravity_enabled", True)
            self.visible = kwargs.get("visible", True)
            self.solid = kwargs.get("solid", True)
            self.reserved = kwargs.get("reserved", False)
    
    def __str__(self):    
        flag_strs = ""
        for flag, letter in zip((self.combat_enabled, self.pickup_enabled, self.dialogue_enabled, 
                                self.turn_enabled, self.friction_enabled, self.gravity_enabled, 
                                self.visible, self.solid, self.reserved, self.copy_enabled),
                                ("C","P","D","T","F","G","V","S","R","Y")):
            flag_strs += letter.upper() if flag else letter.lower()
        
        facing_str = ["NE", "SE", "SW", "NW"][self.facing]

        return f"Entity {self.type:02X}: {self.ENTITY_NAMES[self.type]:30} (X: {self.x:4.1f}, Y: {self.y:4.1f}, Z: {self.z:4.1f}) " \
            f"P:{self.palette} F:{facing_str} B:{self.behaviour:03X} D:{self.dialogue:02X} " \
            f"C:{self.copy_source:01X} [{flag_strs}]"
    
    def unpack(self, data):
        # Extract bytes 
        b0, b1, b2, b3, b4, b5, b6, b7 = data
        
        # Extract facing 
        self.facing = (b0 >> 6) & 0b11
        
        # Extract x 
        x_pos = b0 & 0b111111
        self.x = x_pos + 0.5
        if b3 & 0b10000000:
            self.x += 0.5
        
        # Extract palette
        self.palette = (b1 >> 6) & 0b11
        
        # Extract y
        y_pos = b1 & 0b111111
        self.y = y_pos + 0.5 
        if b3 & 0b01000000:
            self.y += 0.5
        
        # Extract combat_enabled
        self.combat_enabled = bool(b2 & 0b10000000)
        self.pickup_enabled = bool(b2 & 0b01000000)
        self.dialogue_enabled = bool(b2 & 0b00100000)
        self.turn_enabled = not bool(b2 & 0b00010000)
        self.friction_enabled = not bool(b2 & 0b00001000)
        self.speed = b2 & 0b00000111
        
        self.reserved = bool(b3 & 0b00100000)
        self.copy_enabled = bool(b3 & 0b00010000)
        self.copy_source = b3 & 0b00001111
        
        self.behaviour = ((b4 << 2) & 0x300) | b7
        self.dialogue = b4 & 0b00111111

        self.type = b5
        
        self.gravity_enabled = not bool(b6 & 0b10000000)
        self.visible = not bool(b6 & 0b00100000) 
        self.solid = not bool(b6 & 0b00010000)
        self.z = b6 & 0b00001111
        if b6 & 0b01000000:
            self.z += 0.5
    
    def pack(self):
        data = bytes()

        b0 = (self.facing << 6) | (int(self.x - 0.5) & 0b111111)
        data += b0.to_bytes(1,byteorder='big') 

        b1 = (self.palette << 6) | (int(self.y - 0.5) & 0b111111)  
        data += b1.to_bytes(1,byteorder='big')

        b2 = (self.combat_enabled << 7) | \
            (self.pickup_enabled << 6) | \
            (self.dialogue_enabled << 5) | \
            ((not self.turn_enabled) << 4) | \
            ((not self.friction_enabled) << 3) | \
            (self.speed & 0b00000111)
        data += b2.to_bytes(1,byteorder='big')

        b3 = 0
        if (self.x - int(self.x)) < 0.5:
            b3 |= 0b10000000  
        if (self.y - int(self.y)) < 0.5:
            b3 |= 0b01000000
        b3 |= (self.reserved << 5) | \
            (self.copy_enabled << 4) | \
            (self.copy_source & 0b00001111)
        data += b3.to_bytes(1,byteorder='big')

        b4 = ((self.behaviour & 0x300) >> 2) | (self.dialogue & 0b00111111) 
        data += b4.to_bytes(1,byteorder='big')

        data += self.type.to_bytes(1,byteorder='big') 

        b6 = (not (self.gravity_enabled) << 7) | \
            (((self.z - int(self.z)) >= 0.5) << 6) | \
            ((not self.visible) << 5) | \
            ((not self.solid) << 4) | \
            (int(self.z) & 0b00001111)
        data += b6.to_bytes(1,byteorder='big')

        data += (self.behaviour & 0xff).to_bytes(1,byteorder='big')

        return data

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        if not 0 <= value <= 255:
            raise ValueError("Type must be between 0-255")
        self._type = value

    @property
    def x(self):
        return self._x

    @x.setter 
    def x(self, value):
        if not 0.5 <= value <= 64.0 or value % 0.5 != 0:
            raise ValueError("X must be between 0.5-64.0 in 0.5 increments")  
        self._x = value

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, value):
        if not 0.5 <= value <= 64.0 or value % 0.5 != 0:
            raise ValueError("Y must be between 0.5-64.0 in 0.5 increments")
        self._y = value

    @property
    def z(self):
        return self._z

    @z.setter
    def z(self, value):
        if not 0 <= value <= 15.5 or value % 0.5 != 0:
            raise ValueError("Z must be between 0-15.5 in 0.5 increments")
        self._z = value

    @property
    def facing(self):
        return self._facing

    @facing.setter
    def facing(self, value):
        if value not in tuple(item.value for item in Direction):
            raise ValueError("Facing must be a valid Direction enum")
        self._facing = value

    @property
    def palette(self):
        return self._palette

    @palette.setter 
    def palette(self, value):
        if not 0 <= value <= 3:
            raise ValueError("Palette must be between 0-3")
        self._palette = value

    @property
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, value):
        if not 0 <= value <= 7:
            raise ValueError("Speed must be between 0-7")
        self._speed = value

    @property
    def behaviour(self):
        return self._behaviour

    @behaviour.setter 
    def behaviour(self, value):
        if not 0 <= value <= 1023:
            raise ValueError("Behaviour must be between 0-1023") 
        self._behaviour = value

    @property
    def dialogue(self):
        return self._dialogue

    @dialogue.setter
    def dialogue(self, value):
        if not 0 <= value <= 63: 
            raise ValueError("Dialogue must be between 0-63")
        self._dialogue = value

    @property
    def copy_enabled(self):
        return self._copy_enabled

    @copy_enabled.setter
    def copy_enabled(self, value):
        self._copy_enabled = value

    @property
    def copy_source(self):
        return self._copy_source

    @copy_source.setter
    def copy_source(self, value):
        if not 0 <= value <= 15:
            raise ValueError("Copy source must be between 0-15")
        self._copy_source = value

    @property
    def combat_enabled(self):
        return self._combat_enabled

    @combat_enabled.setter
    def combat_enabled(self, value):
        self._combat_enabled = value

    @property 
    def pickup_enabled(self):
        return self._pickup_enabled

    @pickup_enabled.setter 
    def pickup_enabled(self, value):
        self._pickup_enabled = value

    @property
    def dialogue_enabled(self):
        return self._dialogue_enabled

    @dialogue_enabled.setter
    def dialogue_enabled(self, value):
        self._dialogue_enabled = value

    @property
    def turn_enabled(self):
        return self._turn_enabled

    @turn_enabled.setter
    def turn_enabled(self, value):
        self._turn_enabled = value

    @property
    def friction_enabled(self):
        return self._friction_enabled

    @friction_enabled.setter
    def friction_enabled(self, value):
        self._friction_enabled = value

    @property
    def gravity_enabled(self):
        return self._gravity_enabled

    @gravity_enabled.setter
    def gravity_enabled(self, value):
        self._gravity_enabled = value 

    @property
    def visible(self):
        return self._visible 

    @visible.setter
    def visible(self, value):
        self._visible = value

    @property
    def solid(self):
        return self._solid

    @solid.setter 
    def solid(self, value):
        self._solid = value

    @property
    def reserved(self):
        return self._reserved

    @reserved.setter
    def reserved(self, value):
        self._reserved = value

e = Entity()
print(e)
print(e.pack())
e.unpack(e.pack())
print(e)