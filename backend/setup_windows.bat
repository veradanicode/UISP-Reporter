@echo off
setlocal
cd /d "%~dp0"
echo Creating/updating UISP Reporter Python environment...
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo Setup complete.
echo Edit backend\.env and set UISP_API_TOKEN, then run start_windows.bat
pause
