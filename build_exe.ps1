# Builds dist\TruckTMS.exe: a single Windows executable that needs no Python installed.
# Usage (from the project folder):  powershell -ExecutionPolicy Bypass -File build_exe.ps1
#
# Parts of Qt the app does not use (QML, Quick, PDF, network, software OpenGL) are left out,
# which makes the exe smaller and start faster.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path .venv)) { py -m venv .venv }
.\.venv\Scripts\python -m pip install -q -e . pyinstaller

New-Item -ItemType Directory -Force build | Out-Null
$spec = @'
import os
root = os.path.abspath(os.path.join(SPECPATH, ".."))

UNUSED_MODULES = [
    "tkinter", "unittest", "pydoc", "ssl", "_ssl",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtOpenGL",
    "PySide6.QtDBus", "PySide6.QtXml",
]
UNUSED_FILES = (
    "opengl32sw.dll", "qt6quick", "qt6qml", "qt6pdf", "qt6network", "qt6opengl", "qt6virtualkeyboard",
    "libcrypto", "libssl", "qdirect2d", "qoffscreen", "qminimal", "qpdf.dll", "qtuiotouchplugin",
    "qnetworklistmanager", "qschannelbackend", "qcertonlybackend", "qopensslbackend",
)

a = Analysis(
    [os.path.join(root, "truck_tms", "__main__.py")],
    pathex=[root],
    datas=[(os.path.join(root, "truck_tms", "assets"), os.path.join("truck_tms", "assets"))],
    excludes=UNUSED_MODULES,
)

def keep(entry):
    name = entry[0].lower().replace("\\", "/")
    if "/translations/" in name or name.startswith("pyside6/translations"):
        return name.endswith(("qtbase_tr.qm", "qtbase_en.qm"))  # only the languages the app has
    return not any(part in name for part in UNUSED_FILES)

a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="TruckTMS",
    icon=os.path.join(root, "truck_tms", "assets", "truck_tms.ico"),
    console=False,
    upx=False,
)
'@
Set-Content -Path build\TruckTMS.spec -Value $spec -Encoding ascii

.\.venv\Scripts\python -m PyInstaller --noconfirm --clean --workpath build --distpath dist build\TruckTMS.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "Done: dist\TruckTMS.exe"
