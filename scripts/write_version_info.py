"""生成 PyInstaller Windows 版本资源（版本号来自 config.APP_VERSION）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import APP_VERSION  # noqa: E402


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = []
    for piece in str(version).split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    parts = (parts + [0, 0, 0, 0])[:4]
    return tuple(parts)  # type: ignore[return-value]


def render(version: str) -> str:
    file_version = version_tuple(version)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version},
    prodvers={file_version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', 'Delta'),
         StringStruct('FileDescription', 'Delta Client'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'DeltaClient'),
         StringStruct('OriginalFilename', 'DeltaClient.exe'),
         StringStruct('ProductName', 'Delta Client'),
         StringStruct('ProductVersion', '{version}'),
         StringStruct('LegalCopyright', 'Delta Client')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def main() -> int:
    target = ROOT / "build" / "version_info.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(APP_VERSION), encoding="utf-8")
    print(f"wrote {target} ({APP_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
