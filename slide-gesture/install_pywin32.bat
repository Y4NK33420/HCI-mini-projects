@echo off
echo ==========================================
echo  Installing pywin32 for Overlay Mode
echo ==========================================
echo.

REM Activate virtual environment
call ..\venv_py310\Scripts\activate.bat

REM Install pywin32
echo Installing pywin32...
pip install pywin32>=306

echo.
echo ==========================================
echo  Installation Complete!
echo ==========================================
echo.
echo You can now run Mode 1 with overlay support.
echo.

pause

