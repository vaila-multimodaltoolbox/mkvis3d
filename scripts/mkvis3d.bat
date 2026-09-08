@echo off
REM Windows double-click launcher for mkvis3d
cd /d "%~dp0\.."

if exist "dist\mkvis3d.exe" (
    start "" "dist\mkvis3d.exe" %*
) else (
    where uv >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        uv run mkvis3d gui %*
    ) else (
        python -m openbiomech.cli gui %*
    )
)
