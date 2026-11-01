import { useState, useRef } from 'react';
import api from '../api/axios';
import { 
  Copy, Check, BarChart2, Settings, Download, ExternalLink, QrCode, 
  ChevronRight, TrendingUp 
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { QRCodeCanvas } from 'qrcode.react';
import { TextRepel } from './TextRepel';
import AuthPrompt from './AuthPrompt';
import { useAuth } from '../auth/AuthContext';
import { copyText } from '../utils/clipboard';

const ShortenerForm = () => {
  const { isAuthenticated } = useAuth();
  const [url, setUrl] = useState(() => sessionStorage.getItem('shortenerDraftUrl') || '');
  const [customAlias, setCustomAlias] = useState(() => sessionStorage.getItem('shortenerDraftAlias') || '');
  const [expiresAt, setExpiresAt] = useState(() => sessionStorage.getItem('shortenerDraftExpiry') || '');
  const [password, setPassword] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const [toastShow, setToastShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showAuthPrompt, setShowAuthPrompt] = useState(false);
  const qrRef = useRef();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;
    if (!isAuthenticated) {
      setShowAuthPrompt(true);
      return;
    }
    setLoading(true);
    setError('');
    
    let formattedUrl = url.trim();
    if (!/^https?:\/\//i.test(formattedUrl)) {
      formattedUrl = `https://${formattedUrl}`;
    }
    
    try {
      const payload = { target_url: formattedUrl };
      if (customAlias.trim()) payload.custom_alias = customAlias.trim();
      if (expiresAt) payload.expires_at = new Date(expiresAt).toISOString();
      if (password.trim()) payload.password = password.trim();

      const res = await api.post('/api/shorten', payload);
      setResult(res.data);
      sessionStorage.removeItem('shortenerDraftUrl');
      sessionStorage.removeItem('shortenerDraftAlias');
      sessionStorage.removeItem('shortenerDraftExpiry');
      setCopied(false);
      setCustomAlias('');
      setExpiresAt('');
      setPassword('');
      setShowAdvanced(false);
    } catch (err) {
      console.error('URL shortening error:', err);

      if (!err.response) {
        if (err.code === 'ERR_NETWORK' || err.message?.includes('Network Error')) {
          setError('Network error: Unable to connect to backend server. Please verify backend is running on http://localhost:8000.');
        } else {
          setError(err.message || 'Unable to connect to the server. Please check your network connection.');
        }
        return;
      }

      const status = err.response.status;
      const data = err.response.data;

      let serverMessage = '';
      if (data) {
        if (typeof data.message === 'string' && data.message.trim()) {
          serverMessage = data.message.trim();
        } else if (typeof data.detail === 'string' && data.detail.trim()) {
          serverMessage = data.detail.trim();
        } else if (Array.isArray(data.detail)) {
          serverMessage = data.detail
            .map((d) => d.msg || (typeof d === 'string' ? d : JSON.stringify(d)))
            .join(', ');
        } else if (Array.isArray(data.errors)) {
          serverMessage = data.errors
            .map((d) => d.msg || (typeof d === 'string' ? d : JSON.stringify(d)))
            .join(', ');
        }
      }

      if (serverMessage) {
        setError(serverMessage);
        if (status === 401) setShowAuthPrompt(true);
      } else {
        switch (status) {
          case 400:
            setError('Bad request. Please verify the URL and parameters.');
            break;
          case 401:
            setError('Authentication required. Please sign in with Google to shorten links.');
            setShowAuthPrompt(true);
            break;
          case 403:
            setError('Permission denied. You do not have access to create this link.');
            break;
          case 409:
            setError('This custom alias is already in use. Please choose another alias.');
            break;
          case 422:
            setError('Invalid URL format. Please enter a valid HTTP or HTTPS address.');
            break;
          case 429:
            setError('Too many requests. Rate limit is 20 requests per minute.');
            break;
          default:
            setError('Failed to shorten URL. Make sure it\'s valid.');
            break;
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const downloadQR = () => {
    if (!result?.short_url) return;
    const sourceCanvas = qrRef.current?.querySelector('canvas');
    if (!sourceCanvas) return;

    const offscreen = document.createElement('canvas');
    offscreen.width = 512;
    offscreen.height = 512;
    const ctx = offscreen.getContext('2d');

    // Fill clean white background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 512, 512);

    // Render QR code with padding (432x432 inside 512x512)
    ctx.drawImage(sourceCanvas, 40, 40, 432, 432);

    const pngUrl = offscreen.toDataURL('image/png');
    const downloadLink = document.createElement('a');
    downloadLink.href = pngUrl;
    downloadLink.download = `${result.short_id || 'bytelink'}-qr-512px.png`;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
  };

  const handleCopy = async () => {
    if (result?.short_url) {
      const ok = await copyText(result.short_url);
      if (ok) {
        setCopied(true);
        setToastShow(true);
        setTimeout(() => {
          setToastShow(false);
          setTimeout(() => setCopied(false), 200);
        }, 2000);
      }
    }
  };

  return (
    <div>
      {showAuthPrompt && <AuthPrompt
        onContinue={() => setShowAuthPrompt(false)}
        onAuthenticate={() => {
          sessionStorage.setItem('shortenerDraftUrl', url);
          sessionStorage.setItem('shortenerDraftAlias', customAlias);
          sessionStorage.setItem('shortenerDraftExpiry', expiresAt);
        }}
      />}
      {/* Hero Section (Asymmetrical Split Grid Layout) */}
      <section className="hero-grid" id="hero">
        {/* Left Column: Input Form & Setup */}
        <div className="hero-left">
          <h1 className="hero-title">
            <TextRepel text="Beautiful links with analytics built in." />
          </h1>
          <p className="hero-desc">
            Shorten URLs, generate QR codes, and track clicks with real-time insights—all from one simple dashboard.
          </p>

          <form onSubmit={handleSubmit}>
            <div className="input-container-outer">
              <input 
                id="hero-input"
                type="url" 
                inputMode="url"
                className="url-input-new" 
                placeholder="https://your-long-url.com/very/long/path" 
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
                aria-label="Long URL to shorten"
              />
              <button 
                type="submit" 
                className="btn-generate" 
                disabled={loading}
                aria-label={loading ? "Generating short link" : "Generate short link"}
              >
                {loading ? (
                  <>
                    <span className="spinner" aria-hidden="true"></span>
                    <span>Generating...</span>
                  </>
                ) : (
                  'Generate Link'
                )}
              </button>
            </div>
          </form>

          {error && (
            <div className="error-toast-new" role="alert">
              <span>{error}</span>
              <button 
                type="button" 
                className="error-close-new" 
                onClick={() => setError('')}
                aria-label="Close error message"
              >
                &times;
              </button>
            </div>
          )}

          {/* Advanced Options Accordion */}
          <div className="accordion-wrapper">
            <button 
              type="button" 
              className="accordion-trigger" 
              onClick={() => setShowAdvanced(!showAdvanced)}
              aria-expanded={showAdvanced}
              aria-controls="advanced-panel"
            >
              <ChevronRight className={`accordion-icon ${showAdvanced ? 'open' : ''}`} size={16} aria-hidden="true" />
              <span>Advanced Options</span>
            </button>
            
            <div 
              id="advanced-panel"
              className={`accordion-body-grid ${showAdvanced ? 'open' : ''}`}
              role="region"
            >
              <div className="accordion-body-content">
                <div className="advanced-options-grid">
                  <div className="advanced-field">
                    <label htmlFor="custom-alias">Custom Alias (Optional)</label>
                    <input 
                      id="custom-alias"
                      type="text" 
                      className="advanced-input" 
                      placeholder="e.g. my-portfolio" 
                      value={customAlias} 
                      onChange={(e) => setCustomAlias(e.target.value)} 
                      autoComplete="off"
                    />
                  </div>
                  <div className="advanced-field">
                    <label htmlFor="expiry-date">Expiration Date (Optional)</label>
                    <input 
                      id="expiry-date"
                      type="datetime-local" 
                      className="advanced-input" 
                      value={expiresAt} 
                      onChange={(e) => setExpiresAt(e.target.value)} 
                    />
                  </div>
                  <div className="advanced-field">
                    <label htmlFor="password-opt">Password Protection (Optional)</label>
                    <input 
                      id="password-opt"
                      type="password" 
                      className="advanced-input" 
                      placeholder="Secret key" 
                      value={password} 
                      onChange={(e) => setPassword(e.target.value)} 
                      autoComplete="new-password"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Result Card (Smoothly revealed under input area) */}
          {result && (
            <div className="result-card-container">
              <div className="result-card">
                <div className="result-left">
                  <div className="result-header-label">Short link created</div>
                  <a href={result.short_url} target="_blank" rel="noreferrer" className="result-short-url">
                    {result.short_url}
                  </a>
                  <div className="result-target-url" title={result.target_url}>
                    {result.target_url}
                  </div>
                  
                  <div className="result-actions-row">
                    <button 
                      onClick={handleCopy} 
                      className="btn-action primary-action"
                      aria-label="Copy short link to clipboard"
                    >
                      {copied ? <><Check size={16} aria-hidden="true" /> Copied</> : <><Copy size={16} aria-hidden="true" /> Copy Link</>}
                    </button>
                    <a 
                      href={result.short_url} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="btn-action"
                      role="button"
                    >
                      <ExternalLink size={16} aria-hidden="true" /> Open Link
                    </a>
                    <Link to={`/stats/${result.short_id}`} className="btn-action" role="button">
                      <BarChart2 size={16} aria-hidden="true" /> Analytics
                    </Link>
                  </div>
                </div>

                <div className="result-right">
                  <div className="result-qr-wrapper">
                    <div ref={qrRef} className="qr-canvas-box">
                      <QRCodeCanvas value={result.short_url} size={80} />
                    </div>
                    <div className="qr-actions-box">
                      <h4>QR Code</h4>
                      <p>Scan to redirect instantly</p>
                      <button 
                        onClick={downloadQR} 
                        className="btn-qr-download"
                        aria-label="Download QR code image"
                      >
                        <Download size={14} aria-hidden="true" /> Download QR
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Analytics overview */}
        <div className="hero-right">
          <div className="analytics-preview-dashboard">
            <div className="dashboard-header-row">
              <div className="dashboard-header-title">
                <TrendingUp size={18} color="#3ECF8E" aria-hidden="true" />
                <span>Real Analytics</span>
              </div>
              <span className="badge-live">From your links</span>
            </div>
            <div className="mini-chart-card" aria-label="Analytics preview">
              <span className="mini-chart-title">Your analytics appear here</span>
              <p className="mini-chart-description">
                Create a link and share it to collect real click events. Dashboard
                metrics are calculated from your stored links and visits.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Copy Success Toast */}
      <div 
        className={`toast-success ${toastShow ? 'show' : ''}`}
        role="status"
        aria-live="polite"
      >
        <Check size={16} aria-hidden="true" />
        <span>Copied to clipboard</span>
      </div>

      {/* Features Grid Section */}
      <section className="features-section" id="features">
        <h2 className="features-section-title">Designed for modern product workflows.</h2>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <TrendingUp size={24} aria-hidden="true" />
            </div>
            <h3>Real-Time Analytics</h3>
            <p>Track clicks and audience insights instantly. See where your visitors come from, their devices, and when they click.</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <QrCode size={24} aria-hidden="true" />
            </div>
            <h3>QR Code Sharing</h3>
            <p>Generate high-resolution QR codes for easy offline sharing. Perfect for marketing campaigns, physical banners, and business cards.</p>
          </div>

          <div className="feature-card">
            <div className="feature-icon-wrapper">
              <Settings size={24} aria-hidden="true" />
            </div>
            <h3>Custom URLs</h3>
            <p>Create memorable branded links and custom vanity aliases to increase click-through rates and build trust with your audience.</p>
          </div>
        </div>
      </section>

      {/* Analytics Info Section */}
      <section className="analytics-section" id="analytics">
        <h2 className="analytics-section-title">Deep analytics for every link.</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '48px', alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <p style={{ color: 'var(--text-secondary)', fontSize: '16px', lineHeight: '1.7' }}>
              ByteLink tracks every click asynchronously to prevent adding latency to your redirects. Instantly understand who is clicking your links and optimize your distribution channels.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <h4 style={{ color: '#F3F4F6', fontSize: '15px', fontWeight: '600' }}>Geo-Location Tracking</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Understand country and city distribution logs instantly on every redirect.</p>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <h4 style={{ color: '#F3F4F6', fontSize: '15px', fontWeight: '600' }}>Device Detection</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Identify whether your users are browsing on mobile, desktop, or tablet devices.</p>
              </div>
            </div>
          </div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '24px', padding: '32px', display: 'flex', flexDirection: 'column', gap: '16px', boxShadow: 'var(--shadow)' }}>
            <h4 style={{ fontSize: '15px', fontWeight: '600', color: 'var(--text-primary)' }}>Redirect Speed</h4>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '48px', fontWeight: '800', color: 'var(--accent)' }}>&lt; 12ms</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Avg latency</span>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
              Built with PostgreSQL and Redis caching for high-throughput, low-latency URL resolution.
            </p>
          </div>
        </div>
      </section>

      {/* Pricing Grid Section */}
      <section className="pricing-section" id="pricing">
        <div className="pricing-header">
          <h2>Simple, developer-friendly pricing.</h2>
          <p>Start for free and scale as you grow.</p>
        </div>
        <div className="pricing-grid">
          <div className="pricing-card">
            <div className="pricing-tier">Hobby</div>
            <div className="pricing-price">
              <span className="pricing-amount">$0</span>
              <span className="pricing-period">/ month</span>
            </div>
            <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>For personal side projects and testing.</p>
            <ul className="pricing-features-list">
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>100 links / month</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>Basic analytics logs</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>QR Code generator</span>
              </li>
            </ul>
            <a href="#hero-input" className="btn-pricing-action" aria-label="Get started for free on Hobby plan">Get Started</a>
          </div>

          <div className="pricing-card popular">
            <div className="pricing-badge">Popular</div>
            <div className="pricing-tier">Pro</div>
            <div className="pricing-price">
              <span className="pricing-amount">$9</span>
              <span className="pricing-period">/ month</span>
            </div>
            <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>For growing products and marketing campaigns.</p>
            <ul className="pricing-features-list">
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>Unlimited links</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>Detailed geo-location analytics</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>Custom vanity aliases</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>Password link protection</span>
              </li>
            </ul>
            <a href="#hero-input" className="btn-pricing-action primary-pricing" aria-label="Upgrade to Pro plan for 9 dollars a month">Upgrade to Pro</a>
          </div>

          <div className="pricing-card">
            <div className="pricing-tier">Enterprise</div>
            <div className="pricing-price">
              <span className="pricing-amount">Custom</span>
            </div>
            <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>For secure, large-scale APIs and corporate teams.</p>
            <ul className="pricing-features-list">
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>Dedicated instances</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>SSO / OAuth authentication</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>Reliable public redirects</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>API rate limit control</span>
              </li>
            </ul>
            <a href="#hero-input" className="btn-pricing-action" aria-label="Contact for enterprise plan">Contact Us</a>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ShortenerForm;
