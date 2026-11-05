from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('tkinterdnd2')
a = Analysis(['mcp_server.py'], pathex=['.'], hiddenimports=hiddenimports, datas=[('profiles', 'profiles')], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='GPBridgeMCP', console=True, icon='assets/gpbridge.ico', version='version_info.txt')
