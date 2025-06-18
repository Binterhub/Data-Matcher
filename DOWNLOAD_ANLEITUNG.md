# Download und Installation - Wissenschafts-Wissensplattform

## Was Sie herunterladen müssen

Kopieren Sie folgende Dateien und Ordner auf Ihren Webserver:

### Erforderliche Dateien:
```
📁 Ihr-Projekt-Ordner/
├── 📄 main.py                    # Haupt-Anwendung
├── 📄 app_requirements.txt       # Python-Pakete
├── 📄 README.md                  # Dokumentation
├── 📄 start.sh                   # Linux/Mac Start-Skript
├── 📄 start.bat                  # Windows Start-Skript
├── 📄 deploy.py                  # Produktions-Deployment
├── 📁 templates/                 # HTML-Vorlagen
│   ├── 📄 base.html
│   └── 📄 index.html
├── 📁 static/                    # Statische Dateien
│   ├── 📁 css/
│   │   └── 📄 custom.css
│   └── 📁 img/
│       └── 📄 IMG_5482.jpeg
```

### NICHT erforderlich (automatisch erstellt):
- `flask_session/` (wird automatisch erstellt)
- `pyproject.toml` (nur für Replit)
- `.replit` (nur für Replit)
- `replit.nix` (nur für Replit)

## Schnellstart

### Option 1: Automatisches Setup (empfohlen)

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```cmd
start.bat
```

### Option 2: Manuelles Setup

1. **Virtual Environment erstellen:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\Scripts\activate     # Windows
```

2. **Pakete installieren:**
```bash
pip install -r app_requirements.txt
```

3. **Anwendung starten:**
```bash
python main.py
```

## Produktions-Deployment

### Automatisches Produktions-Setup:
```bash
python deploy.py
```

### Manuell mit Gunicorn:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 main:app
```

## Webserver-Konfiguration

### Nginx Beispiel-Konfiguration:
```nginx
server {
    listen 80;
    server_name ihre-domain.de;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Apache Beispiel-Konfiguration:
```apache
<VirtualHost *:80>
    ServerName ihre-domain.de
    ProxyPass / http://127.0.0.1:5000/
    ProxyPassReverse / http://127.0.0.1:5000/
</VirtualHost>
```

## Anpassungen

### Texte ändern:
Bearbeiten Sie das `TRANSLATIONS` Dictionary in `main.py`

### Design anpassen:
Ändern Sie `static/css/custom.css`

### Logo austauschen:
Ersetzen Sie `static/img/IMG_5482.jpeg` mit Ihrem Bild

## Fehlerbehebung

### Port bereits belegt:
```bash
# Anderen Port verwenden
python main.py  # Dann in main.py Port ändern
# oder
gunicorn -b 0.0.0.0:8000 main:app
```

### Permission-Fehler:
```bash
chmod +x start.sh deploy.py
```

### Python nicht gefunden:
- Installieren Sie Python 3.11+
- Stellen Sie sicher, dass Python im PATH ist

## Support

Bei Problemen prüfen Sie:
1. Python Version (3.11+)
2. Alle Dateien korrekt kopiert
3. Virtual Environment aktiviert
4. Firewall-Einstellungen