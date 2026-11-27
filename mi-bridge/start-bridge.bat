@echo off
rem Запуск мостика «Планы» + Mi Fitness.
rem Останавливается закрытием окна. Автозапуск при входе в Windows —
rem ярлык на этот файл лежит в папке «Автозагрузка».
title Планы - Mi Fitness мостик
cd /d "%~dp0"
"%APPDATA%\uv\tools\mifit\Scripts\python.exe" bridge.py
echo.
echo Мостик остановлен. Нажмите любую клавишу, чтобы закрыть окно...
pause >nul
