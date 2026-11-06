import re

version = re.search(r'VERSION = "(.+?)"', open("main.py", encoding="utf-8").read()).group(1)
parts = [int(p) for p in version.split(".")] + [0, 0, 0]
numbers = tuple(parts[:4])

with open("version_info.txt", "w", encoding="utf-8") as f:
    f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Elias'),
      StringStruct('FileDescription', 'LiteRGB'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'LiteRGB'),
      StringStruct('OriginalFilename', 'LiteRGB.exe'),
      StringStruct('ProductName', 'LiteRGB'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""")
