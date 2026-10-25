@echo off
echo Устанавливаю PyInstaller...
pip install pyinstaller

echo.
echo Собираю .exe...
pyinstaller --onefile --windowed --name "TG Channel Manager" channel_manager.py

echo.
echo Готово! Файл: dist\TG Channel Manager.exe
pause
