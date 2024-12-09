from flask import Flask, render_template, g
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# English content
TRANSLATIONS = {
    'title': 'Discover the World of Knowledge',
    'subtitle': 'Wikipedia - The Free Encyclopedia',
    'why_title': 'Why Wikipedia?',
    'why_text': 'In a world where knowledge knows no bounds, Wikipedia stands as a beacon of free education. For science enthusiasts, we offer:',
    'stats': 'Over 6 million articles in English language',
    'community': 'An active community of scientists and experts',
    'quality': 'Quality-assured scientific articles',
    'access': 'Access to international knowledge',
    'science_title': 'Science for Everyone',
    'science_text': 'From quantum physics to evolutionary biology, from astronomy to molecular biology – Wikipedia makes complex knowledge accessible. Each article is written and reviewed by dedicated individuals who want to share their expertise.',
    'discover': 'Discover Now',
    'footer': 'Wikipedia® is a registered trademark of the Wikimedia Foundation Inc.'
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