// Wissenschafts-Wissensplattform - Static Application JavaScript
// Multi-language support and interactive features

class WissensApp {
    constructor() {
        this.currentLanguage = 'de';
        this.searchModal = null;
        this.init();
    }

    // Translation data
    translations = {
        de: {
            title: 'Entdecke die Welt des Wissens',
            subtitle: 'Wikipedia - Die freie Enzyklopädie',
            whyTitle: 'Warum Wikipedia?',
            whyText: 'In einer Welt, in der Wissen keine Grenzen kennt, steht Wikipedia als Leuchtturm der freien Bildung. Für Wissenschaftsbegeisterte bieten wir:',
            statsText: 'Über 2,7 Millionen Artikel in deutscher Sprache',
            communityText: 'Eine aktive Gemeinschaft von Wissenschaftlern und Experten',
            qualityText: 'Qualitätsgesicherte wissenschaftliche Artikel',
            accessText: 'Zugang zu internationalem Wissen',
            scienceTitle: 'Wissenschaft für alle',
            scienceText: 'Von Quantenphysik bis Evolutionsbiologie, von Astronomie bis Molekularbiologie – Wikipedia macht komplexes Wissen zugänglich. Jeder Artikel wird von begeisterten und engagierten Menschen geschrieben und geprüft, die ihr Fachwissen teilen möchten.',
            discoverText: 'Jetzt entdecken',
            footerText: 'Wikipedia® ist eine eingetragene Marke der Wikimedia Foundation Inc.',
            searchBtn: 'Artikel suchen',
            randomBtn: 'Zufälliger Artikel',
            categoriesBtn: 'Kategorien',
            searchPlaceholder: 'Suchbegriff eingeben...',
            searchModalTitle: 'Artikel suchen',
            searchHint: 'Drücken Sie Enter oder klicken Sie auf das Suchsymbol',
            wikipediaUrl: 'https://de.wikipedia.org'
        },
        en: {
            title: 'Discover the World of Knowledge',
            subtitle: 'Wikipedia - The Free Encyclopedia',
            whyTitle: 'Why Wikipedia?',
            whyText: 'In a world where knowledge knows no boundaries, Wikipedia stands as a beacon of free education. For science enthusiasts, we offer:',
            statsText: 'Over 6.7 million articles in English',
            communityText: 'An active community of scientists and experts',
            qualityText: 'Quality-assured scientific articles',
            accessText: 'Access to international knowledge',
            scienceTitle: 'Science for Everyone',
            scienceText: 'From quantum physics to evolutionary biology, from astronomy to molecular biology – Wikipedia makes complex knowledge accessible. Every article is written and reviewed by dedicated people who want to share their expertise.',
            discoverText: 'Discover Now',
            footerText: 'Wikipedia® is a registered trademark of the Wikimedia Foundation Inc.',
            searchBtn: 'Search Articles',
            randomBtn: 'Random Article',
            categoriesBtn: 'Categories',
            searchPlaceholder: 'Enter search term...',
            searchModalTitle: 'Search Articles',
            searchHint: 'Press Enter or click the search icon',
            wikipediaUrl: 'https://en.wikipedia.org'
        },
        fr: {
            title: 'Découvrez le Monde du Savoir',
            subtitle: 'Wikipédia - L\'Encyclopédie Libre',
            whyTitle: 'Pourquoi Wikipédia?',
            whyText: 'Dans un monde où le savoir ne connaît pas de frontières, Wikipédia se dresse comme un phare de l\'éducation libre. Pour les passionnés de science, nous offrons:',
            statsText: 'Plus de 2,4 millions d\'articles en français',
            communityText: 'Une communauté active de scientifiques et d\'experts',
            qualityText: 'Articles scientifiques de qualité assurée',
            accessText: 'Accès au savoir international',
            scienceTitle: 'La Science pour Tous',
            scienceText: 'De la physique quantique à la biologie évolutive, de l\'astronomie à la biologie moléculaire – Wikipédia rend accessible le savoir complexe. Chaque article est écrit et vérifié par des personnes dévouées qui souhaitent partager leur expertise.',
            discoverText: 'Découvrir Maintenant',
            footerText: 'Wikipedia® est une marque déposée de la Wikimedia Foundation Inc.',
            searchBtn: 'Rechercher des Articles',
            randomBtn: 'Article Aléatoire',
            categoriesBtn: 'Catégories',
            searchPlaceholder: 'Entrez le terme de recherche...',
            searchModalTitle: 'Rechercher des Articles',
            searchHint: 'Appuyez sur Entrée ou cliquez sur l\'icône de recherche',
            wikipediaUrl: 'https://fr.wikipedia.org'
        },
        es: {
            title: 'Descubre el Mundo del Conocimiento',
            subtitle: 'Wikipedia - La Enciclopedia Libre',
            whyTitle: '¿Por qué Wikipedia?',
            whyText: 'En un mundo donde el conocimiento no conoce fronteras, Wikipedia se erige como un faro de la educación libre. Para los entusiastas de la ciencia, ofrecemos:',
            statsText: 'Más de 1,7 millones de artículos en español',
            communityText: 'Una comunidad activa de científicos y expertos',
            qualityText: 'Artículos científicos de calidad asegurada',
            accessText: 'Acceso al conocimiento internacional',
            scienceTitle: 'Ciencia para Todos',
            scienceText: 'Desde la física cuántica hasta la biología evolutiva, desde la astronomía hasta la biología molecular – Wikipedia hace accesible el conocimiento complejo. Cada artículo es escrito y revisado por personas dedicadas que quieren compartir su experiencia.',
            discoverText: 'Descubrir Ahora',
            footerText: 'Wikipedia® es una marca registrada de Wikimedia Foundation Inc.',
            searchBtn: 'Buscar Artículos',
            randomBtn: 'Artículo Aleatorio',
            categoriesBtn: 'Categorías',
            searchPlaceholder: 'Ingrese término de búsqueda...',
            searchModalTitle: 'Buscar Artículos',
            searchHint: 'Presione Enter o haga clic en el ícono de búsqueda',
            wikipediaUrl: 'https://es.wikipedia.org'
        }
    };

    init() {
        this.initializeModal();
        this.bindEvents();
        this.loadLanguageFromStorage();
        this.updateContent();
        this.initializeAnimations();
    }

    initializeModal() {
        this.searchModal = new bootstrap.Modal(document.getElementById('searchModal'));
    }

    bindEvents() {
        // Language selector events
        document.querySelectorAll('[data-lang]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const lang = e.currentTarget.getAttribute('data-lang');
                this.changeLanguage(lang);
            });
        });

        // Interactive feature buttons
        document.getElementById('searchBtn').addEventListener('click', () => {
            this.openSearch();
        });

        document.getElementById('randomBtn').addEventListener('click', () => {
            this.openRandomArticle();
        });

        document.getElementById('categoriesBtn').addEventListener('click', () => {
            this.openCategories();
        });

        // Search functionality
        document.getElementById('executeSearch').addEventListener('click', () => {
            this.executeSearch();
        });

        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.executeSearch();
            }
        });

        // Globe animation control
        this.bindGlobeEvents();
    }

    loadLanguageFromStorage() {
        const saved = localStorage.getItem('wissensapp-language');
        if (saved && this.translations[saved]) {
            this.currentLanguage = saved;
        }
    }

    saveLanguageToStorage() {
        localStorage.setItem('wissensapp-language', this.currentLanguage);
    }

    changeLanguage(lang) {
        if (!this.translations[lang]) return;
        
        this.currentLanguage = lang;
        this.saveLanguageToStorage();
        
        // Update active button
        document.querySelectorAll('[data-lang]').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-lang="${lang}"]`).classList.add('active');
        
        // Animate content change
        this.animateContentChange(() => {
            this.updateContent();
        });
    }

    updateContent() {
        const t = this.translations[this.currentLanguage];
        
        // Update main content
        document.getElementById('mainTitle').textContent = t.title;
        document.getElementById('subtitle').textContent = t.subtitle;
        document.getElementById('whyTitle').textContent = t.whyTitle;
        document.getElementById('whyText').textContent = t.whyText;
        document.getElementById('statsText').textContent = t.statsText;
        document.getElementById('communityText').textContent = t.communityText;
        document.getElementById('qualityText').textContent = t.qualityText;
        document.getElementById('accessText').textContent = t.accessText;
        document.getElementById('scienceTitle').textContent = t.scienceTitle;
        document.getElementById('scienceText').textContent = t.scienceText;
        document.getElementById('discoverText').textContent = t.discoverText;
        document.getElementById('footerText').textContent = t.footerText;
        
        // Update interactive buttons
        document.getElementById('searchBtn').innerHTML = `<i class="fas fa-search mb-2 d-block"></i>${t.searchBtn}`;
        document.getElementById('randomBtn').innerHTML = `<i class="fas fa-random mb-2 d-block"></i>${t.randomBtn}`;
        document.getElementById('categoriesBtn').innerHTML = `<i class="fas fa-th-large mb-2 d-block"></i>${t.categoriesBtn}`;
        
        // Update search modal
        document.querySelector('#searchModal .modal-title').textContent = t.searchModalTitle;
        document.getElementById('searchInput').placeholder = t.searchPlaceholder;
        document.querySelector('#searchModal small').textContent = t.searchHint;
        
        // Update discover button link
        document.getElementById('discoverBtn').href = t.wikipediaUrl;
        
        // Update document title and language
        document.title = t.title + ' - ' + t.subtitle;
        document.documentElement.lang = this.currentLanguage;
    }

    animateContentChange(callback) {
        const contentWrapper = document.querySelector('.content-wrapper');
        contentWrapper.style.opacity = '0.7';
        contentWrapper.style.transform = 'translateY(10px)';
        
        setTimeout(() => {
            callback();
            contentWrapper.style.opacity = '1';
            contentWrapper.style.transform = 'translateY(0)';
        }, 150);
    }

    openSearch() {
        this.searchModal.show();
        setTimeout(() => {
            document.getElementById('searchInput').focus();
        }, 300);
    }

    executeSearch() {
        const query = document.getElementById('searchInput').value.trim();
        if (!query) return;
        
        const searchUrl = `${this.translations[this.currentLanguage].wikipediaUrl}/w/index.php?search=${encodeURIComponent(query)}`;
        window.open(searchUrl, '_blank', 'noopener,noreferrer');
        
        this.searchModal.hide();
        document.getElementById('searchInput').value = '';
    }

    openRandomArticle() {
        const randomUrl = `${this.translations[this.currentLanguage].wikipediaUrl}/wiki/Special:Random`;
        window.open(randomUrl, '_blank', 'noopener,noreferrer');
    }

    openCategories() {
        const categoriesUrls = {
            de: 'https://de.wikipedia.org/wiki/Portal:Wissenschaft',
            en: 'https://en.wikipedia.org/wiki/Portal:Science',
            fr: 'https://fr.wikipedia.org/wiki/Portail:Sciences',
            es: 'https://es.wikipedia.org/wiki/Portal:Ciencia'
        };
        
        const url = categoriesUrls[this.currentLanguage] || categoriesUrls.en;
        window.open(url, '_blank', 'noopener,noreferrer');
    }

    bindGlobeEvents() {
        const globe = document.getElementById('backgroundGlobe');
        
        // Pause animation on hover
        globe.addEventListener('mouseenter', () => {
            globe.style.animationPlayState = 'paused';
        });
        
        globe.addEventListener('mouseleave', () => {
            globe.style.animationPlayState = 'running';
        });
        
        // Click to change rotation direction
        globe.addEventListener('click', () => {
            const currentDirection = globe.style.animationDirection || 'normal';
            globe.style.animationDirection = currentDirection === 'normal' ? 'reverse' : 'normal';
        });
    }

    initializeAnimations() {
        // Fade in content on load
        const contentWrapper = document.querySelector('.content-wrapper');
        contentWrapper.style.opacity = '0';
        contentWrapper.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            contentWrapper.style.transition = 'all 0.8s ease';
            contentWrapper.style.opacity = '1';
            contentWrapper.style.transform = 'translateY(0)';
        }, 100);
        
        // Stagger card animations
        const cards = document.querySelectorAll('.card');
        cards.forEach((card, index) => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(30px)';
            
            setTimeout(() => {
                card.style.transition = 'all 0.6s ease';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 200 + (index * 100));
        });
    }
}

// Utility functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Theme management
class ThemeManager {
    constructor() {
        this.init();
    }
    
    init() {
        this.loadTheme();
        this.bindThemeToggle();
    }
    
    loadTheme() {
        const savedTheme = localStorage.getItem('wissensapp-theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-bs-theme', savedTheme);
        }
    }
    
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-bs-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('wissensapp-theme', newTheme);
    }
    
    bindThemeToggle() {
        // Add theme toggle if needed
        const themeBtn = document.getElementById('themeToggle');
        if (themeBtn) {
            themeBtn.addEventListener('click', () => this.toggleTheme());
        }
    }
}

// Performance optimization
class PerformanceOptimizer {
    constructor() {
        this.init();
    }
    
    init() {
        this.optimizeImages();
        this.enableServiceWorker();
    }
    
    optimizeImages() {
        const images = document.querySelectorAll('img');
        images.forEach(img => {
            if (img.loading !== 'lazy') {
                img.loading = 'lazy';
            }
        });
    }
    
    enableServiceWorker() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js')
                .then(registration => {
                    console.log('SW registered successfully');
                })
                .catch(error => {
                    console.log('SW registration failed');
                });
        }
    }
}

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.wissensApp = new WissensApp();
    window.themeManager = new ThemeManager();
    window.performanceOptimizer = new PerformanceOptimizer();
    
    // Add loading complete indicator
    document.body.classList.add('loaded');
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    const globe = document.getElementById('backgroundGlobe');
    if (document.hidden) {
        globe.style.animationPlayState = 'paused';
    } else {
        globe.style.animationPlayState = 'running';
    }
});

// Export for potential module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WissensApp, ThemeManager, PerformanceOptimizer };
}