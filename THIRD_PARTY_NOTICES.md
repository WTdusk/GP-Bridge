# Third-party notices

GP Bridge developer: **WTdusk**.

The `licenses/` directory preserves license notices from the Windows build environment, including runtime components and build tools. Inclusion here does not mean every listed development package is bundled into the executables. These notices apply to their respective components; they do not select a license for GP Bridge itself.

| Component | Use | Notice |
| --- | --- | --- |
| CPython 3.12.14 | Packaged Python runtime and standard library | `licenses/Python-LICENSE.txt` |
| Tcl/Tk 8.6 | Desktop interface | `licenses/Tcl-Tk-license.terms` |
| TkinterDnD2 0.7.0 | Drag-and-drop Python wrapper | `licenses/python-packages/tkinterdnd2-0.7.0.dist-info/licenses/LICENSE` |
| TkDND 2.10.3 | Native drag-and-drop extension | `licenses/TkDND-notice.txt`; original notices also remain in bundled Tcl scripts |
| PyInstaller 6.22.3 | Executable packager and bootloader | `licenses/python-packages/pyinstaller-6.22.3.dist-info/licenses/COPYING.txt` |
| Additional Python build dependencies | Packaging support and development | License files under `licenses/python-packages/` |

The GPX container layout was checked against alphaTab's public `GpxFileSystem` / `BitReader` format readers. No alphaTab runtime is shipped. The implementation reference is recorded in `gpx_container.py`.

Guitar Pro, Kontakt, Shreddage and other product names belong to their respective owners. No commercial sample libraries, Kontakt instruments or vendor PDF manuals are included in the release packages.
