@echo off
REM Windows executable build script using PyInstaller and uv
cd /d "%~dp0\.."
echo Building mkvis3d Windows Executable (.exe) with vaila.ico...
uv run --with pyinstaller pyinstaller --clean -y mkvis3d.spec
if %ERRORLEVEL% equ 0 (
    echo.
    echo Successfully built dist\mkvis3d.exe
) else (
    echo.
    echo Build failed with error %ERRORLEVEL%
)
pause
