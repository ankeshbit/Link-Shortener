import { useState } from 'react';
import axios from 'axios';
import { Copy, Check, ArrowRight, BarChart2 } from 'lucide-react';
import { Link } from 'react-router-dom';

const ShortenerForm = () => {
  const [url, setUrl] = useState('');
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;
    setLoading(true);
    setError('');
    
    try {
      // In production, configure exact BASE_URL or use proxy
      const res = await axios.post('http://localhost:8000/api/shorten', {
        target_url: url
      });
      setResult(res.data);
      setCopied(false);
    } catch (err) {
      if (err.response?.status === 429) {
        setError("Too many requests! Rate limit exceeded.");
      } else {
        setError("Failed to shorten URL. Make sure it's valid.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (result) {
      navigator.clipboard.writeText(result.short_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="hero">
      <h1>Shorten Your Links. <br/> Expand Your Reach.</h1>
      <p>
        A scalable, lightning-fast URL shortener with real-time analytics. 
        Paste your long URL below to get started.
      </p>

      <div className="glass-card" style={{ marginTop: '3rem', textAlign: 'left' }}>
        <form onSubmit={handleSubmit} className="input-group">
          <input 
            type="url" 
            className="url-input" 
            placeholder="https://your-long-url.com/very/long/path" 
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Shortening...' : 'Generate Link'}
          </button>
        </form>
        {error && <p style={{ color: '#ef4444', marginTop: '1rem' }}>{error}</p>}

        {result && (
          <div className="result-box">
            <div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.3rem' }}>
                Your short URL is ready:
              </p>
              <a href={result.short_url} target="_blank" rel="noreferrer" className="result-url">
                {result.short_url}
              </a>
            </div>
            
            <div style={{ display: 'flex', gap: '1rem' }}>
              <Link to={`/stats/${result.short_id}`} className="btn-primary" style={{ padding: '0.6rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', textDecoration: 'none' }}>
                <BarChart2 size={18} /> Analytics
              </Link>
              <button onClick={handleCopy} className="copy-btn" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {copied ? <><Check size={18} /> Copied</> : <><Copy size={18} /> Copy</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ShortenerForm;
