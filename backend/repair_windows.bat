@echo off
setlocal
cd /d "%~dp0"
echo This will remove only this project's backend .venv and recreate it.
choice /M "Continue"
if errorlevel 2 exit /b 0
if exist ".venv" rmdir /s /q ".venv"
py -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo Environment repaired. The null-byte urllib3/requests import error should be gone.
pause
