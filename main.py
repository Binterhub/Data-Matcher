from flask import Flask, render_template, request, g, session, redirect, url_for
from flask_session import Session
import os
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# Configure session
app.config.update(
    SECRET_KEY=os.urandom(24),
    SESSION_TYPE='filesystem',
    SESSION_FILE_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session'),
    SESSION_PERMANENT=False,
    PERMANENT_SESSION_LIFETIME=1800  # 30 minutes
)

Session(app)

# Translations
TRANSLATIONS = {
    'en': {
        'title': 'Discover the World of Knowledge',
        'subtitle': 'English Wikipedia - The Free Encyclopedia',
        'why_title': 'Why Wikipedia?',
        'why_text': 'In a world where knowledge knows no bounds, Wikipedia stands as a beacon of free education. For science enthusiasts, we offer:',
        'stats': 'Over 2.7 million articles in German language',
        'community': 'An active community of scientists and experts',
        'quality': 'Quality-assured scientific articles',
        'access': 'Access to international knowledge',
        'science_title': 'Science for Everyone',
        'science_text': 'From quantum physics to evolutionary biology, from astronomy to molecular biology – Wikipedia makes complex knowledge accessible. Each article is written and reviewed by dedicated individuals who want to share their expertise.',
        'discover': 'Discover Now',
        'footer': 'Wikipedia® is a registered trademark of the Wikimedia Foundation Inc.'
    },
    'de': {
        'title': 'Entdecke die Welt des Wissens',
        'subtitle': 'Deutsche Wikipedia - Die freie Enzyklopädie',
        'why_title': 'Warum Wikipedia?',
        'why_text': 'In einer Welt, in der Wissen grenzenlos ist, steht Wikipedia als Leuchtturm der freien Bildung. Für Wissenschaftsbegeisterte bieten wir:',
        'stats': 'Über 2,7 Millionen Artikel in deutscher Sprache',
        'community': 'Eine aktive Community von Wissenschaftlern und Experten',
        'quality': 'Qualitätsgesicherte wissenschaftliche Artikel',
        'access': 'Zugang zu internationalem Wissen',
        'science_title': 'Wissenschaft für alle',
        'science_text': 'Von Quantenphysik bis zur Evolutionsbiologie, von der Astronomie bis zur Molekularbiologie – Wikipedia macht komplexes Wissen zugänglich. Jeder Artikel wird von engagierten Menschen geschrieben und geprüft, die ihre Expertise teilen möchten.',
        'discover': 'Jetzt entdecken',
        'footer': 'Wikipedia® ist eine eingetragene Marke der Wikimedia Foundation Inc.'
    }
}

@app.before_request
def before_request():
    g.lang = session.get('lang', 'de')
    g.translations = TRANSLATIONS[g.lang]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/switch-language')
def switch_language():
    session['lang'] = 'en' if session.get('lang', 'de') == 'de' else 'de'
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
