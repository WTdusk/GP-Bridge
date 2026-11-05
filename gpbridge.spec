# PyInstaller build definition: pyinstaller gpbridge.spec
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('tkinterdnd2')
a = Analysis(['app.py'], pathex=['.'], hiddenimports=hiddenimports, datas=[('profiles', 'profiles'), ('assets', 'assets')], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='GPBridge', console=False, icon='assets/gpbridge.ico', version='version_info.txt')
