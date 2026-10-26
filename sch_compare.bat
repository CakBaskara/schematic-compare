@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [setup] creating .venv in %ROOT% ...
    py -3.12 -m venv "%ROOT%.venv" || python -m venv "%ROOT%.venv" || exit /b 1
    "%PY%" -m pip install --disable-pip-version-check -q -r "%ROOT%requirements.txt" || exit /b 1
)
set "PYTHONPATH=%ROOT%"
"%PY%" -m sch_compare %*
exit /b %ERRORLEVEL%
