import sys

from scripts import palette, sprite_frame, tilemap_2d, tilemap_iso, lz77, blockset, strings

commands = {
    "palette": palette.main,
    "sprite_frame": sprite_frame.main,
    "tilemap_2d": tilemap_2d.main,
    "tilemap_iso": tilemap_iso.main,
    "lz77": lz77.main,
    "blockset": blockset.main,
    "strings": strings.main
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(f"Please specify a script to execute: [{', '.join([k for k in commands.keys()])}]")
        sys.exit(1)
    script_name = sys.argv[1]
    args = sys.argv[1:]
    if script_name in commands:
        commands[script_name](args)
