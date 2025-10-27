@echo off
echo Starting Gesture Painting Backend...
cd backend
call ..\..\slide-gesture\venv_py310\Scripts\activate
python painting_server.py
pause

