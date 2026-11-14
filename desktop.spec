from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files
root = Path(SPECPATH)
os.environ['QT_API'] = 'pyside6'
data, binaries, hidden = collect_all('playwright')
data += collect_data_files('webview')
for name in ['msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'concrt140.dll']:
    candidate = Path(os.environ['SystemRoot'])/'System32'/name
    if candidate.exists(): binaries.append((str(candidate), '.'))
resources = []
for name in ('ui', 'icons', 'bin'):
    resources.append((str(root/'resources'/name), 'resources/'+name))
if (root/'resources'/'chromium-custom').is_dir():
    resources.append((str(root/'resources'/'chromium-custom'), 'resources/chromium-custom'))
else:
    for folder in (root/'resources'/'browsers').iterdir():
        if folder.is_dir() and folder.name.startswith(('chromium-', 'chromium_headless_shell-', 'ffmpeg-', 'winldd-')):
            resources.append((str(folder), 'resources/browsers/'+folder.name))
a = Analysis([str(root/'run.py')], pathex=[str(root)], binaries=binaries,
    datas=data+resources,
    hiddenimports=hidden+['webview.platforms.qt', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel'],
    excludes=['PyQt5','PyQt6','PySide2','gi','cefpython3','clr','pythonnet','webview.platforms.winforms','webview.platforms.edgechromium','tkinter','numpy','PIL'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='网络ASR', console=False, icon=str(root/'resources'/'icons'/'app.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='网络ASR')
