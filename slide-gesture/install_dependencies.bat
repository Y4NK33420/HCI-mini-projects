@echo off
echo ==========================================
echo  Installing Aura Dependencies
echo ==========================================
echo.

REM Activate virtual environment
call ..\venv_py310\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install requirements
pip install -r requirements-py311.txt

echo.
echo ==========================================
echo  Installation Complete!
echo ==========================================
echo.
echo You can now run:
echo   - Mode 1: run_mode1.bat
echo   - Mode 2: run_mode2_backend.bat and run_mode2_frontend.bat
echo.

pause

