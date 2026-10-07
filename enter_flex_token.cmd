@echo off
cd /d "%~dp0"
python -m scripts.enter_flex_token
if errorlevel 1 pause
