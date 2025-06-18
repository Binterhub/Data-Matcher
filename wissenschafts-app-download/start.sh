#!/bin/bash

# Wissenschafts-Wissensplattform Starter Script

echo "🌍 Starte Wissenschafts-Wissensplattform..."

# Prüfe ob Python installiert ist
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 ist nicht installiert. Bitte installieren Sie Python 3.11 oder höher."
    exit 1
fi

# Prüfe Python Version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.11"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo "❌ Python $required_version oder höher erforderlich. Gefunden: $python_version"
    exit 1
fi

# Erstelle Virtual Environment falls nicht vorhanden
if [ ! -d "venv" ]; then
    echo "📦 Erstelle Virtual Environment..."
    python3 -m venv venv
fi

# Aktiviere Virtual Environment
echo "🔧 Aktiviere Virtual Environment..."
source venv/bin/activate

# Installiere Abhängigkeiten
echo "📚 Installiere Abhängigkeiten..."
pip install -r app_requirements.txt

# Starte die Anwendung
echo "🚀 Starte die Anwendung auf http://localhost:5000"
echo "   Drücken Sie Ctrl+C zum Beenden"
python main.py