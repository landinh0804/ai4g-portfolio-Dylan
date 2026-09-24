@echo off
rem ---------------------------------------------------------------------------
rem Contract Trap Finder - double-click launcher for Windows.
rem
rem The tool already runs entirely on the machine it is started from; this file
rem removes the four commands standing between a clone of the repository and a
rem window with the app in it. It creates the virtual environment if it is
rem missing, installs the requirements if they are missing or have changed, and
rem starts the app.
rem
rem It never activates the environment. It calls .venv\Scripts\python.exe by
rem full path instead, which is what activation exists to arrange, so the `py`
rem launcher trap described in the README cannot happen here.
rem
rem A .bat rather than a .ps1 on purpose: PowerShell's default execution policy
rem blocks unsigned scripts, and the person we want running this should not have
rem to change a security setting to read their own contract.
rem ---------------------------------------------------------------------------

setlocal EnableExtensions
pushd "%~dp0"
title Contract Trap Finder

set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\requirements.stamp"
set "INSTALL_FAILED="

echo.
echo   Contract Trap Finder
echo   --------------------
echo.

rem --- 1. The virtual environment --------------------------------------------

if not exist "%VPY%" call :create_venv
if not exist "%VPY%" goto :no_python

rem --- 2. Dependencies -------------------------------------------------------
rem The stamp holds the timestamp of requirements.txt as it was when pip last
rem succeeded. Editing or pulling a new requirements.txt changes the timestamp
rem and triggers a reinstall; nothing else does, so the normal start is instant.

set "REQ_TIME="
for %%I in (requirements.txt) do set "REQ_TIME=%%~tI"

set "OLD_TIME="
if exist "%STAMP%" set /p OLD_TIME=<"%STAMP%"

if not "%REQ_TIME%"=="%OLD_TIME%" call :install_requirements
if defined INSTALL_FAILED goto :install_error

rem --- 3. Configuration ------------------------------------------------------
rem Absence of .env is not an error: without a key the app still starts, and the
rem sidebar's local mode (Ollama) needs no key at all.

if not exist ".env" call :create_env

rem --- 4. Go -----------------------------------------------------------------

echo   Starting. Your browser opens at http://localhost:8501
echo   Leave this window open while you use the app - closing it stops the app.
echo.

"%VPY%" -m streamlit run app.py
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo   The app stopped unexpectedly ^(exit code %EXITCODE%^).
    echo   The lines above this message say why.
    echo.
    pause
)

popd
endlocal & exit /b %EXITCODE%


rem --- Subroutines -----------------------------------------------------------

:create_venv
echo   First run: creating the virtual environment in %VENV%
echo.
rem The py launcher is tried first: on a machine with no real Python, `where
rem python` finds the Windows Store stub, which opens the Store instead of
rem failing, and the error that follows makes no sense to anyone.
set "BOOT="
where py >nul 2>&1
if not errorlevel 1 set "BOOT=py -3"
if not defined BOOT (
    where python >nul 2>&1
    if not errorlevel 1 set "BOOT=python"
)
if not defined BOOT goto :eof
%BOOT% -m venv "%VENV%"
goto :eof

:install_requirements
echo   Installing dependencies. This takes a few minutes the first time.
echo.
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    set "INSTALL_FAILED=1"
    goto :eof
)
rem Written only on success, so a failed install is retried on the next start
rem rather than silently skipped.
>"%STAMP%" echo %REQ_TIME%
echo.
goto :eof

:create_env
if not exist ".env.example" goto :eof
copy /y ".env.example" ".env" >nul
echo   Created .env from .env.example.
echo.
echo   For the hosted mode, open .env and set GEMINI_API_KEY.
echo   Without a key, choose "On this computer ^(Ollama^)" in the sidebar,
echo   which needs no key and sends nothing over the internet.
echo.
goto :eof

:no_python
echo   Python was not found on this computer.
echo.
echo   Install Python 3.11 or newer from https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH" in the installer, then run this file
echo   again.
echo.
pause
popd
endlocal & exit /b 1

:install_error
echo.
echo   Installing the dependencies failed. The pip output above says why.
echo   The most common cause is no internet connection.
echo.
pause
popd
endlocal & exit /b 1
