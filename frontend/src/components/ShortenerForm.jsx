import { useState, useRef, useEffect } from 'react';
import api from '../api/axios';
import { 
  Copy, Check, BarChart2, Settings, Download, ExternalLink, QrCode, Lock, 
  ChevronRight, TrendingUp, Laptop, Globe 
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { QRCodeCanvas } from 'qrcode.react';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip } from 'chart.js';
import { Line } from 'react-chartjs-2';
import { TextRepel } from './TextRepel';

// Register ChartJS modules
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

// Animated Counter Component using requestAnimationFrame for smooth 1s ease-out counting
const AnimatedCounter = ({ value, suffix = "", isFloat = false }) => {
  const [displayVal, setDisplayVal] = useState(0);

  useEffect(() => {
    const numericTarget = parseFloat(value.toString().replace(/,/g, ''));
    if (isNaN(numericTarget)) return;

    const duration = 1000; // 1 second
    const startTime = performance.now();

    const run = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // easeOutQuad curve
      const ease = progress * (2 - progress);
      const current = ease * numericTarget;

      setDisplayVal(current);

      if (progress < 1) {
        requestAnimationFrame(run);
      }
    };

    requestAnimationFrame(run);
  }, [value]);

  if (isFloat) {
    return <span>{displayVal.toFixed(1)}{suffix}</span>;
  }
  return <span>{Math.floor(displayVal).toLocaleString()}{suffix}</span>;
};

const ShortenerForm = () => {
  const [url, setUrl] = useState('');
  const [customAlias, setCustomAlias] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [password, setPassword] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const [toastShow, setToastShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const qrRef = useRef();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;
    setLoading(true);
    setError('');
    
    let formattedUrl = url.trim();
    if (!/^https?:\/\//i.test(formattedUrl)) {
      formattedUrl = `https://${formattedUrl}`;
    }
    
    try {
      const payload = { target_url: formattedUrl };
      if (customAlias) payload.custom_alias = customAlias;
      if (expiresAt) payload.expires_at = new Date(expiresAt).toISOString();
      if (password) payload.password = password;

      const res = await api.post('/api/shorten', payload);
      setResult(res.data);
      setCopied(false);
      setCustomAlias('');
      setExpiresAt('');
      setPassword('');
      setShowAdvanced(false);
    } catch (err) {
      if (err.response?.status === 429) {
        setError("Too many requests! Rate limit exceeded.");
      } else if (err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'string') {
          setError(detail);
        } else if (Array.isArray(detail)) {
          setError(detail.map(d => d.msg || d).join(', '));
        } else {
          setError(JSON.stringify(detail));
        }
      } else {
        setError("Failed to shorten URL. Make sure it's valid.");
      }
    } finally {
      setLoading(false);
    }
  };

  const downloadQR = () => {
    const canvas = qrRef.current.querySelector('canvas');
    if (canvas) {
      const pngUrl = canvas.toDataURL('image/png').replace('image/png', 'image/octet-stream');
      const downloadLink = document.createElement('a');
      downloadLink.href = pngUrl;
      downloadLink.download = `${result.short_id}-qr.png`;
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);
    }
  };

  const handleCopy = () => {
    if (result) {
      navigator.clipboard.writeText(result.short_url);
      setCopied(true);
      setToastShow(true);
      
      setTimeout(() => {
        setToastShow(false);
        setTimeout(() => setCopied(false), 200);
      }, 2000);
    }
  };

  // Chart data and options for mock analytics preview
  const previewChartData = {
    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    datasets: [
      {
        data: [140, 220, 190, 340, 290, 480, 520],
        borderColor: '#3ECF8E',
        backgroundColor: (context) => {
          const chart = context.chart;
          const {ctx, chartArea} = chart;
          if (!chartArea) return 'rgba(62, 207, 142, 0.08)';
          const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          gradient.addColorStop(0, 'rgba(62, 207, 142, 0.08)');
          gradient.addColorStop(1, 'rgba(62, 207, 142, 0)');
          return gradient;
        },
        fill: true,
        tension: 0.4,
        cubicInterpolationMode: 'monotone',
        pointRadius: 0,
        borderWidth: 3, // stroke width 3px
      }
    ]
  };

  const previewChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { 
      legend: { display: false }, // no legends
      tooltip: { 
        enabled: true, // tooltips enabled on hover
        backgroundColor: '#0D1321',
        titleColor: '#fff',
        bodyColor: '#3ECF8E',
        borderColor: 'rgba(255,255,255,0.08)',
        borderWidth: 1,
        padding: 10,
        displayColors: false
      }
    },
    animation: {
      duration: 1500, // duration 1.5s
      easing: 'easeInOutQuart'
    },
    layout: {
      padding: {
        left: 24,
        right: 32, // 32px from right edge
        top: 16,
        bottom: 24 // 24px from bottom
      }
    },
    scales: {
      x: { 
        display: true, // Show Mon, Tue, etc.
        ticks: {
          color: '#6B7280',
          font: { family: 'Geist', size: 11 }
        },
        grid: { display: false }, // Hide heavy grid lines
        border: { color: 'rgba(255, 255, 255, 0.08)' } // subtle baseline axis line
      },
      y: { 
        display: false,
        min: 100, // Limit bottom height to occupy 80% of card height
        max: 600
      }
    }
  };

  return (
    <div>
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

        {/* Right Column: Visual Mock Live Analytics Dashboard Preview */}
        <div className="hero-right">
          <div className="analytics-preview-dashboard">
            <div className="dashboard-header-row">
              <div className="dashboard-header-title">
                <TrendingUp size={18} color="#3ECF8E" aria-hidden="true" />
                <span>Live Analytics Preview</span>
              </div>
              <span className="badge-live">Live</span>
            </div>

            {/* Clicks, Load Time, Active Links, Reliability Grid */}
            <div className="metrics-grid-2x2">
              <div className="metric-card-lite">
                <span className="metric-title">Clicks</span>
                <span className="metric-value"><AnimatedCounter value={12540} /></span>
                <span className="metric-growth">+18.4%</span>
              </div>

              <div className="metric-card-lite">
                <span className="metric-title">Load Time</span>
                <span className="metric-value"><AnimatedCounter value={48} suffix="ms" /></span>
                <span className="metric-growth">-12.0%</span>
              </div>

              <div className="metric-card-lite">
                <span className="metric-title">Active Links</span>
                <span className="metric-value"><AnimatedCounter value={1204} /></span>
                <span className="metric-growth">+8.2%</span>
              </div>

              <div className="metric-card-lite">
                <span className="metric-title">Reliability</span>
                <span className="metric-value"><AnimatedCounter value={99.9} suffix="%" isFloat={true} /></span>
                <span className="metric-growth">Stable</span>
              </div>
            </div>

            {/* Weekly Trend Large Chart Card (Occupies 100% Width) */}
            <div className="mini-chart-card">
              <span className="mini-chart-title">Click Volume Trends (Weekly)</span>
              <div className="mini-chart-content">
                <Line data={previewChartData} options={previewChartOptions} />
              </div>
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
              Built on cloud edge instances with local SQLite read replication to deliver instantaneous redirection.
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
                <Check size={16} aria-hidden="true" /> <span>Dedicated edge instances</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>SSO / SAML authentication</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>99.99% redirect uptime SLA</span>
              </li>
              <li className="pricing-feature-item">
                <Check size={16} aria-hidden="true" /> <span>API key rate limit control</span>
              </li>
            </ul>
            <a href="mailto:sales@bytelink.co" className="btn-pricing-action" aria-label="Contact sales for enterprise plan">Contact Sales</a>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ShortenerForm;
