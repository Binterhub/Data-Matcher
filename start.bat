@echo off
echo 🌍 Starte Wissenschafts-Wissensplattform...

:: Prüfe ob Python installiert ist
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python ist nicht installiert. Bitte installieren Sie Python 3.11 oder höher.
    pause
    exit /b 1
)

:: Erstelle Virtual Environment falls nicht vorhanden
if not exist "venv" (
    echo 📦 Erstelle Virtual Environment...
    python -m venv venv
)

:: Aktiviere Virtual Environment
echo 🔧 Aktiviere Virtual Environment...
call venv\Scripts\activate.bat

:: Installiere Abhängigkeiten
echo 📚 Installiere Abhängigkeiten...
pip install -r app_requirements.txt

:: Starte die Anwendung
echo 🚀 Starte die Anwendung auf http://localhost:5000
echo    Drücken Sie Ctrl+C zum Beenden
python main.py

pause