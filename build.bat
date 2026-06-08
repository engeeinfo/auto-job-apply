@echo off
echo Building NaukriAutoApply with PyInstaller...
pyinstaller --onefile --windowed --name NaukriAutoApply --collect-all PyQt6 main.py
echo Build complete! The executable is located in the dist/ folder.
pause
