#!/usr/bin/env python3
"""
Produktions-Deployment-Skript für die Wissenschafts-Wissensplattform
"""

import os
import sys
import subprocess
from pathlib import Path

def run_command(cmd, description):
    """Führt einen Befehl aus und gibt Feedback"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} erfolgreich")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Fehler bei {description}: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return False

def check_requirements():
    """Prüft Systemvoraussetzungen"""
    print("🔍 Prüfe Systemvoraussetzungen...")
    
    # Python Version prüfen
    if sys.version_info < (3, 11):
        print(f"❌ Python 3.11+ erforderlich. Gefunden: {sys.version}")
        return False
    
    # Pip verfügbar?
    if not run_command("pip --version", "Pip-Verfügbarkeit"):
        return False
    
    print("✅ Systemvoraussetzungen erfüllt")
    return True

def setup_production():
    """Richtet Produktionsumgebung ein"""
    print("\n🚀 Richte Produktionsumgebung ein...")
    
    # Virtual Environment erstellen
    if not os.path.exists("venv"):
        if not run_command("python -m venv venv", "Virtual Environment erstellen"):
            return False
    
    # Aktivierung je nach OS
    if os.name == 'nt':  # Windows
        activate_cmd = "venv\\Scripts\\activate && "
    else:  # Unix/Linux
        activate_cmd = "source venv/bin/activate && "
    
    # Abhängigkeiten installieren
    install_cmd = f"{activate_cmd}pip install -r app_requirements.txt"
    if not run_command(install_cmd, "Abhängigkeiten installieren"):
        return False
    
    # Gunicorn für Produktion installieren
    gunicorn_cmd = f"{activate_cmd}pip install gunicorn"
    if not run_command(gunicorn_cmd, "Gunicorn installieren"):
        return False
    
    return True

def create_systemd_service():
    """Erstellt systemd Service für Linux"""
    service_content = f"""[Unit]
Description=Wissenschafts-Wissensplattform
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory={os.getcwd()}
Environment=PATH={os.getcwd()}/venv/bin
ExecStart={os.getcwd()}/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
"""
    
    with open("wissenschafts-plattform.service", "w") as f:
        f.write(service_content)
    
    print("📝 systemd Service-Datei erstellt: wissenschafts-plattform.service")
    print("   Kopieren Sie diese nach /etc/systemd/system/ für automatischen Start")

def main():
    """Hauptfunktion"""
    print("🌍 Wissenschafts-Wissensplattform Deployment")
    print("=" * 50)
    
    if not check_requirements():
        sys.exit(1)
    
    if not setup_production():
        sys.exit(1)
    
    create_systemd_service()
    
    print("\n✅ Deployment erfolgreich abgeschlossen!")
    print("\n📋 Nächste Schritte:")
    print("1. Entwicklung: python main.py")
    print("2. Produktion: venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 main:app")
    print("3. Reverse Proxy (Nginx/Apache) für Domain-Weiterleitung einrichten")
    print("4. SSL-Zertifikat installieren")

if __name__ == "__main__":
    main()