# Wissenschafts-Wissensplattform - Static HTML Version

A completely standalone HTML/CSS/JavaScript version of the scientific knowledge platform with no server dependencies.

## Features

- **Pure HTML/CSS/JavaScript** - No Python, Flask, or server required
- **Multi-language Support** - German, English, French, Spanish
- **Responsive Design** - Works on desktop, tablet, and mobile
- **Interactive Features** - Search, random articles, categories
- **Dark Theme** - Bootstrap-based modern design
- **Rotating Globe Animation** - CSS-animated background
- **Local Storage** - Remembers language preference
- **Performance Optimized** - Lazy loading and smooth animations

## File Structure

```
static-export/
├── index.html          # Main HTML file
├── css/
│   └── custom.css      # All styling and animations
├── js/
│   └── app.js          # Interactive functionality and translations
├── img/
│   └── IMG_5482.jpeg   # Logo and background image
└── README.md           # This file
```

## Installation

### Option 1: Direct Usage
1. Open `index.html` in any modern web browser
2. No server setup required

### Option 2: Local Web Server
For testing with local server features:

```bash
# Python 3
python -m http.server 8000

# Node.js (if you have http-server installed)
npx http-server

# PHP
php -S localhost:8000
```

Then open `http://localhost:8000`

## Customization

### Change Content
Edit the `translations` object in `js/app.js` to modify text content for any language.

### Modify Styling
Edit `css/custom.css` to change colors, animations, or layout.

### Add Languages
1. Add new language object to `translations` in `js/app.js`
2. Add corresponding button in the language selector section of `index.html`

### Replace Images
Replace `img/IMG_5482.jpeg` with your own image (recommended: 500x500px minimum).

## Browser Compatibility

- Chrome/Chromium 60+
- Firefox 60+
- Safari 12+
- Edge 79+

## Deployment Options

### Static Hosting
Upload to any static hosting service:
- GitHub Pages
- Netlify
- Vercel
- AWS S3
- Azure Static Web Apps
- Google Cloud Storage

### CDN Distribution
- Cloudflare Pages
- AWS CloudFront
- Azure CDN

### Traditional Web Server
Upload to any web server that serves static files:
- Apache
- Nginx
- IIS

## Performance Features

- **Lazy Loading** - Images load only when needed
- **CSS Animations** - Hardware-accelerated transforms
- **Local Storage** - Settings persist between visits
- **Optimized Assets** - Minimal external dependencies
- **Responsive Images** - Automatic sizing for different screens

## External Dependencies

The application uses these CDN resources:
- Bootstrap CSS (Replit theme)
- Bootstrap JavaScript
- Font Awesome icons

For offline usage, download these resources and update the links in `index.html`.

## Interactive Features

### Language Switching
Click any language button to instantly change all content. Preference is saved locally.

### Search Functionality
Click "Search Articles" to open search modal. Searches are directed to the appropriate Wikipedia language version.

### Random Articles
"Random Article" button opens a random Wikipedia article in the selected language.

### Categories
"Categories" button opens science portals for each language.

### Globe Animation
- Hover to pause rotation
- Click to reverse direction

## Accessibility

- Semantic HTML structure
- ARIA labels and roles
- Keyboard navigation support
- High contrast color scheme
- Screen reader friendly

## License

This static version maintains the educational purpose of the original Flask application. Please respect Wikipedia's terms of service when linking to their content.