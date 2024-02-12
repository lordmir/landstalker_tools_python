import capstone
from pathlib import Path


disasm = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN)

rom = Path(r"C:\PROJECTS\landstalker_disasm\landstalker.bin").read_bytes()

print(list(disasm.disasm(rom[0x9F644:0x9F654], 0)))
