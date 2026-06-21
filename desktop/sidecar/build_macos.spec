# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec —— Mac sidecar(yts-sidecar)。
# 铁律:模型权重绝不打包(Candle 在 Rust 侧)。产物需 codesign + notarize(见 wiki Platform-Split)。
# 构建:`uv run pyinstaller desktop/sidecar/build_macos.spec`(在仓库根)。

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'aiosqlite',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='yts-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,  # 由当前架构决定;通用包需分别构建 arm64/x86_64
)
