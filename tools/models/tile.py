from enum import Enum


class Attr(Enum):
    """Tile attributes that can be masked on/off.

    Attributes:
        HFLIP: Mask for horizontal flip.
        VFLIP: Mask for vertical flip. 
        PRIORITY: Mask for priority attribute.
    """
    HFLIP = 0,
    VFLIP = 1,
    PRIORITY = 2


class Tile:
    """Single 16x16 tile with attributes.

    Attributes:
        idx: Tile index value.
        hflip: Boolean for horizontal flip attribute.
        vflip: Boolean for vertical flip attribute.
        priority: Boolean for priority attribute.
    """
    idx: int = 0
    hflip: bool = False
    vflip: bool = False
    priority: bool = False

    def __init__(self, val: int = 0) -> None:
        self.set_val(val)

    def set_attr(self, attr: Attr) -> None:
        """Set boolean attribute on tile
        
        Args:
            attr: Attribute to set
        Returns:
            None
        """

        if attr == Attr.HFLIP:
            self.hflip = True
        elif attr == Attr.VFLIP:
            self.vflip = True
        elif attr == Attr.PRIORITY:
            self.priority = True
    
    def has_attr(self, attr: Attr) -> bool:
        """Read boolean attribute on tile
        
        Args:
            attr: Attribute to read
        Returns:
            bool: the attribute
        """

        if attr == Attr.HFLIP:
            return self.hflip
        elif attr == Attr.VFLIP:
            return self.vflip
        elif attr == Attr.PRIORITY:
            return self.priority
    
    def set_val(self, val: int) -> None:
        self.idx = val & 0x7FF
        self.hflip = (val & 0x800) > 0
        self.vflip = (val & 0x1000) > 0
        self.priority = (val & 0x8000) > 0

    def __repr__(self):
        """String representation showing index and attributes
        
        Returns:
            Nicely formatted attribute string
        """

        s = f"{self.idx:04X}"
        s += "H" if self.hflip else " "
        s += "V" if self.vflip else " "
        s += "P" if self.priority else " "
        return s
    
    def get_val(self) -> int:
        code = self.idx & 0x7FF
        code |= 0x800 if self.hflip else 0
        code |= 0x1000 if self.vflip else 0
        code |= 0x8000 if self.priority else 0
        return code

    def encode(self) -> str:
        return f"{self.get_val():04X}"
