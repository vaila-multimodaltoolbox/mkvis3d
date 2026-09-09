@echo off
REM Windows double-click launcher for mkvis3d
cd /d "%~dp0"

if exist "%~dp0dist\mkvis3d.exe" (
    start "" "%~dp0dist\mkvis3d.exe" %*
) else if exist "%~dp0mkvis3d.py" (
    where uv >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        uv run python "%~dp0mkvis3d.py" %*
    ) else (
        python "%~dp0mkvis3d.py" %*
    )
) else (
    python -m openbiomech.cli gui %*
)
