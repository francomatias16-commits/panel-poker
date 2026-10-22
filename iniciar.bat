@echo off
rem Inicia el panel de estudio (necesita Python 3.11 o mas nuevo)
where py >nul 2>nul && (py -3 "%~dp0iniciar.py" %*) || (python "%~dp0iniciar.py" %*)
