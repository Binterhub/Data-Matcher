from flask import Flask, render_template, g
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# German content
TRANSLATIONS = {
    'title': 'Entdecke die Welt des Wissens',
    'subtitle': 'Wikipedia - Die freie Enzyklopädie',
    'why_title': 'Warum Wikipedia?',
    'why_text': 'In einer Welt, in der Wissen keine Grenzen kennt, steht Wikipedia als Leuchtturm der freien Bildung. Für Wissenschaftsbegeisterte bieten wir:',
    'stats': 'Über 2,7 Millionen Artikel in deutscher Sprache',
    'community': 'Eine aktive Gemeinschaft von Wissenschaftlern und Experten',
    'quality': 'Qualitätsgesicherte wissenschaftliche Artikel',
    'access': 'Zugang zu internationalem Wissen',
    'science_title': 'Wissenschaft für alle',
    'science_text': 'Von Quantenphysik bis Evolutionsbiologie, von Astronomie bis Molekularbiologie – Wikipedia macht komplexes Wissen zugänglich. Jeder Artikel wird von begeisterten und engagierten Menschen geschrieben und geprüft, die ihr Fachwissen teilen möchten.',
    'discover': 'Jetzt entdecken',
    'footer': 'Wikipedia® ist eine eingetragene Marke der Wikimedia Foundation Inc.'
}

@app.before_request
def before_request():
    g.translations = TRANSLATIONS
    logging.debug("Rendering page with English content")

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)