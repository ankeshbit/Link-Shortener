import { BrowserRouter, Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import ShortenerForm from './components/ShortenerForm';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import SignIn from './components/SignIn';
import Dashboard from './components/Dashboard';
import { MagnetLines } from './components/MagnetLines';

function AppContent() {
  const location = useLocation();
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('token'));

  // Sync authentication state on path navigation
  useEffect(() => {
    setIsAuthenticated(!!localStorage.getItem('token'));
  }, [location.pathname]);

  // Smooth scroll and focus logic for active section underlines via IntersectionObserver
  useEffect(() => {
    if (location.pathname !== '/') {
      setActiveSection('');
      return;
    }

    const sections = ['hero', 'features', 'analytics', 'pricing'];
    const observers = sections.map(id => {
      const el = document.getElementById(id);
      if (!el) return null;

      const observer = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) {
          setActiveSection(id);
        }
      }, {
        rootMargin: '-30% 0px -60% 0px' // trigger when section occupies main viewport space
      });
      observer.observe(el);
      return { observer, el };
    }).filter(Boolean);

    return () => {
      observers.forEach(o => o.observer.unobserve(o.el));
    };
  }, [location.pathname]);

  // Handle scrolling when coming from a hash URL
  useEffect(() => {
    const hash = location.hash || window.location.hash;
    if (hash && location.pathname === '/') {
      const id = hash.replace('#', '');
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: id === 'hero-input' ? 'center' : 'start' });
          if (id === 'hero-input') {
            const input = document.getElementById('hero-input');
            const container = document.querySelector('.input-container-outer');
            if (input) {
              input.focus();
              if (container) {
                container.classList.add('pulse-glow');
                setTimeout(() => container.classList.remove('pulse-glow'), 2000);
              }
            }
          }
        }
      }, 300);
    }
  }, [location.pathname, location.hash]);

  const handleNavClick = (e, id) => {
    e.preventDefault();
    if (location.pathname !== '/') {
      navigate(`/#${id}`);
      return;
    }
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const handleGetStartedClick = (e) => {
    e.preventDefault();
    if (location.pathname !== '/') {
      navigate('/#hero-input');
      return;
    }
    const container = document.querySelector('.input-container-outer');
    const input = document.getElementById('hero-input');
    if (input) {
      input.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => {
        input.focus();
        if (container) {
          container.classList.add('pulse-glow');
          setTimeout(() => {
            container.classList.remove('pulse-glow');
          }, 2000);
        }
      }, 500);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    setIsAuthenticated(false);
    navigate('/login');
  };

  return (
    <div className="app-container">
      {/* Interactive Magnet Lines background grid */}
      <div className="bg-magnet-wrapper" aria-hidden="true">
        <MagnetLines 
          rows={12} 
          columns={20} 
          containerSize="100%" 
          lineColor="rgba(62, 207, 142, 0.15)" 
          lineWidth="0.5vmin" 
          lineHeight="3.5vmin" 
        />
      </div>

      <nav className="navbar">
        <Link to={isAuthenticated ? "/dashboard" : "/"} className="logo-container" aria-label="ByteLink Home">
          <div className="logo-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
            </svg>
          </div>
          <span>ByteLink</span>
        </Link>
        
        <div className="nav-links">
          <a href="#features" onClick={(e) => handleNavClick(e, 'features')} className={`nav-link ${activeSection === 'features' ? 'active-nav' : ''}`}>Features</a>
          <a href="#analytics" onClick={(e) => handleNavClick(e, 'analytics')} className={`nav-link ${activeSection === 'analytics' ? 'active-nav' : ''}`}>Analytics</a>
          <a href="#pricing" onClick={(e) => handleNavClick(e, 'pricing')} className={`nav-link ${activeSection === 'pricing' ? 'active-nav' : ''}`}>Pricing</a>
          <a 
            href="https://github.com/ankeshbit/Link-Shortener" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="nav-link"
          >
            GitHub
          </a>
          {isAuthenticated ? (
            <>
              <Link to="/dashboard" className="nav-link">Dashboard</Link>
              <button 
                onClick={handleSignOut} 
                className="nav-link" 
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'inherit' }}
              >
                Sign Out
              </button>
            </>
          ) : (
            <Link to="/login" className="nav-link">Sign In</Link>
          )}
          <a href="#hero-input" onClick={handleGetStartedClick} className="btn-nav-primary">Get Started</a>
        </div>
      </nav>

      <Routes>
        <Route path="/" element={<ShortenerForm />} />
        <Route path="/stats/:id" element={<AnalyticsDashboard />} />
        <Route path="/login" element={<SignIn />} />
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>

      <footer className="footer">
        <div className="footer-left">
          <div className="footer-brand">ByteLink</div>
          <p className="footer-desc">
            Premium URL shortening and real-time analytics designed for developers and product-focused teams.
          </p>
        </div>
        <div className="footer-links-grid">
          <div className="footer-links-col">
            <h4>Product</h4>
            <a href="#features" onClick={(e) => handleNavClick(e, 'features')} className="footer-link">Features</a>
            <a href="#analytics" onClick={(e) => handleNavClick(e, 'analytics')} className="footer-link">Analytics</a>
            <a href="#pricing" onClick={(e) => handleNavClick(e, 'pricing')} className="footer-link">Pricing</a>
          </div>
          <div className="footer-links-col">
            <h4>Resources</h4>
            <a 
              href="https://github.com/ankeshbit/Link-Shortener" 
              target="_blank" 
              rel="noopener noreferrer" 
              className="footer-link"
            >
              GitHub
            </a>
            <a href="#docs" className="footer-link">Docs</a>
            <a href="#privacy" className="footer-link">Privacy</a>
          </div>
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;
