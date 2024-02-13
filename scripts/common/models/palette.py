from colorama import Fore, Style

class Palettes:
    def __init__(self, **kwargs):
        if "data" in kwargs:
            if "entries" in kwargs:
                self.palettes = self.palette_to_rgb(kwargs["data"], kwargs["entries"])
            else:
                self.palettes = self.palette_to_rgb(kwargs["data"])
        elif "palettes" in kwargs:
            self.palettes = kwargs["palettes"]
        else:
            self.palettes = []

    @staticmethod
    def rgb_to_palette_color(rgb_str):
        r = int(rgb_str[1:3], 16) // 36
        g = int(rgb_str[3:5], 16) // 36
        b = int(rgb_str[5:7], 16) // 36
        
        byte1 = (r << 1) | (g << 5)
        byte0 = (b << 1)
        
        return bytes([byte0, byte1])

    @staticmethod
    def palette_color_to_rgb(byte0, byte1):
        r = ((byte1 >> 1) & 0x7) * 36
        g = ((byte1 >> 5) & 0x7) * 36
        b = ((byte0 >> 1) & 0x7) * 36
        
        return f'#{r:02x}{g:02x}{b:02x}'

    @staticmethod
    def palette_to_rgb(bytestr: bytes, palette_size: int | None = None):
        rgb_colors = []
        length = palette_size
        i = 0
        while i < len(bytestr):
            colors = []
            if not palette_size:
                length = int.from_bytes(bytestr[i:i+2], "big") + 1
                i += 2
            for j in range(length):
                byte0 = bytestr[i + j * 2]
                byte1 = bytestr[i + j * 2 + 1]
                colors.append(Palettes.palette_color_to_rgb(byte0, byte1))
            rgb_colors.append(colors)
            i += len(colors) * 2
        return rgb_colors

    def encode(self, variable_width: bool = False):
        bytestr = bytearray()
        for colors in self.palettes:
            if variable_width:
                bytestr.extend(int(len(colors) - 1).to_bytes(2, "big"))
            for color in colors:
                r, g, b = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
                byte0 = (b // 36) << 1
                byte1 = (r // 36) << 1 | (g // 36) << 5
                bytestr += bytes([byte0, byte1])
        return bytestr

    def print_palette_preview(self):
        for i, colors in enumerate(self.palettes):
            print(f"Palette {i:3}: ", end='')
            for color in colors:
                r, g, b = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
                
                # For dark background colors, set white text, else set black text
                # R*0.299 + G*0.587 + B*0.114
                if r*0.299 + g*0.587 + b*0.114 < 128:
                    fore_color = f"{Fore.WHITE}{Style.BRIGHT}"
                else:
                    fore_color = f"{Fore.BLACK}{Style.BRIGHT}"
                    
                color_code = f'\033[48;2;{r};{g};{b}m'    
                hex_code = f'{int.from_bytes(self.rgb_to_palette_color(color), "big"):03X}'
                print(f"{color_code}{fore_color} {hex_code} {Style.RESET_ALL} ", end='')
            print()
