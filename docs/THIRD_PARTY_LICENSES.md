# Third-party software

Truck TMS itself is released under the [MIT license](../LICENSE). It uses the components below. The
source code only needs Python and PySide6; the Windows `TruckTMS.exe` bundles all of them.

| Component | Used for | License |
|---|---|---|
| [Python](https://www.python.org/) | Runtime (bundled in the exe) | [PSF License](https://docs.python.org/3/license.html) |
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython/) | User interface | [LGPL v3](https://www.gnu.org/licenses/lgpl-3.0.html) |
| [Qt 6](https://www.qt.io/) libraries (Core, Gui, Widgets, Svg, PrintSupport) | User interface, PDF output | [LGPL v3](https://doc.qt.io/qt-6/lgpl.html) |
| [SQLite](https://sqlite.org/) (via Python's `sqlite3`) | Data file | [Public domain](https://sqlite.org/copyright.html) |
| [PyInstaller](https://pyinstaller.org/) | Building the exe (bootloader in the exe) | [GPL v2 with a bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) that allows distributing the exe under any license |

**Not used, on purpose:** the *Qt Charts* module is licensed under the GPL (not the LGPL) in its open-source
edition, so it would not fit an MIT project. Truck TMS draws its own charts with `QPainter`
(`truck_tms/ui/charts.py`). Excel files are read with Python's standard library (`truck_tms/importer.py`),
without any extra package.

## LGPL notes for the Windows exe

- Qt and PySide6 are used unmodified, as dynamically loaded libraries. Inside the exe they are
  unpacked to a temporary folder at start-up.
- You can replace them with your own (modified) builds of Qt/PySide6 in two ways: run Truck TMS from source
  (`pip install -e .` then `truck-tms`), or rebuild the exe with `build_exe.ps1`.
- The source code of Qt and PySide6 is available at <https://code.qt.io/> and
  <https://download.qt.io/official_releases/QtForPython/>.

## Assets

The logo, icons, start-up animation and screenshots were made for this project and are covered by the
project's MIT license. No third-party fonts or images are included; the app uses the fonts installed on
the computer.
