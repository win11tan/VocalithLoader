@echo off
chcp 936 >nul
cd /d "%~dp0"

if exist "%~dp0VocalithLoader.exe" (
    start "" "%~dp0VocalithLoader.exe"
    exit /b 0
)

rem 没有 exe 就走源码启动
where python >nul 2>&1
if errorlevel 1 (
    echo 没有找到 Python。先装 Python 3.9 或更高版本，安装时勾选 Add Python to PATH。
    pause
    exit /b 1
)

python -c "import webview, requests" >nul 2>&1
if errorlevel 1 (
    echo 依赖还没装，正在执行 pip install -r requirements.txt ...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo 依赖安装失败。请手动执行: python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

python "%~dp0app.py"
if errorlevel 1 pause
