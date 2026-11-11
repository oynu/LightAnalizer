@echo off
title LightAnalizer - Premium AI Chess Assistant
echo Starting LightAnalizer...
python main.py
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
