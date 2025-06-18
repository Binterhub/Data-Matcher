# Wissenschafts-Wissensplattform

Eine digitale wissenschaftliche Wissensplattform mit deutscher Sprachunterstützung, basierend auf Flask.

## Projektstruktur

```
├── main.py                 # Haupt-Flask-Anwendung
├── requirements.txt        # Python-Abhängigkeiten
├── static/                 # Statische Dateien
│   ├── css/               
│   │   └── custom.css     # Benutzerdefinierte Styles
│   └── img/               
│       └── IMG_5482.jpeg  # Logo/Hintergrundbild
├── templates/              # HTML-Templates
│   ├── base.html          # Basis-Template
│   └── index.html         # Hauptseite
└── flask_session/          # Session-Daten (automatisch erstellt)
```

## Installation

### Voraussetzungen
- Python 3.11 oder höher
- pip (Python Package Manager)

### 1. Projekt herunterladen
Laden Sie alle Dateien in einen Ordner auf Ihrem Webserver herunter.

### 2. Virtual Environment erstellen (empfohlen)
```bash
python -m venv venv
source venv/bin/activate  # Auf Linux/Mac
# oder
venv\Scripts\activate     # Auf Windows
```

### 3. Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 4. Anwendung starten
```bash
python main.py
```

Die Anwendung läuft dann auf `http://localhost:5000`

## Produktions-Deployment

### Mit Gunicorn (empfohlen)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 main:app
```

### Mit Apache/Nginx
Konfigurieren Sie Ihren Webserver so, dass er die Flask-Anwendung über WSGI bedient.

## Anpassungen

### Inhalte ändern
Die deutschen Texte befinden sich in `main.py` im `TRANSLATIONS` Dictionary.

### Styling anpassen
Benutzerdefinierte Styles können in `static/css/custom.css` geändert werden.

### Logo/Bilder austauschen
Ersetzen Sie `static/img/IMG_5482.jpeg` mit Ihrem eigenen Bild.

## Features

- Responsive Design mit Bootstrap
- Dunkles Theme
- Rotierende Globus-Animation
- Deutsche Lokalisierung
- Optimiert für wissenschaftliche Inhalte

## Browser-Unterstützung

- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Lizenz

Dieses Projekt ist für Bildungszwecke erstellt. Bitte beachten Sie die entsprechenden Lizenzen für verwendete Bibliotheken.