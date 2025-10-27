@echo off
echo Starting Aura Mode 2 Backend (FastAPI)...
cd backend
call ..\venv_py310\Scripts\activate
python gesture_server.py
pause

