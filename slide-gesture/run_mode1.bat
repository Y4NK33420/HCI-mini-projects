@echo off
echo ==========================================
echo  Aura - Mode 1: Universal Controller
echo ==========================================
echo.

REM Activate virtual environment
call ..\venv_py310\Scripts\activate.bat

REM Run the controller
python gesture_controller.py

pause

