@echo off
REM Windows double-click launcher for mkvis3d
cd /d "%~dp0\.."

if exist "dist\mkvis3d.exe" (
    start "" "dist\mkvis3d.exe" %*
) else if exist "mkvis3d.py" (
    where uv >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        uv run python mkvis3d.py %*
    ) else (
        python mkvis3d.py %*
    )
) else (
    python -m openbiomech.cli gui %*
)
