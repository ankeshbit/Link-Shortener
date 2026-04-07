import { useState, useRef } from 'react';
import axios from 'axios';
import { Copy, Check, BarChart2, Settings, Download } from 'lucide-react';
import { Link } from 'react-router-dom';
import { QRCodeCanvas } from 'qrcode.react';

const ShortenerForm = () => {
  const [url, setUrl] = useState('');
  const [customAlias, setCustomAlias] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [password, setPassword] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const qrRef = useRef();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;
    setLoading(true);
    setError('');
    
    try {
      const payload = { target_url: url };
      if (customAlias) payload.custom_alias = customAlias;
      if (expiresAt) payload.expires_at = new Date(expiresAt).toISOString();
      if (password) payload.password = password;

      const res = await axios.post('http://localhost:8000/api/shorten', payload);
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
        setError(err.response.data.detail);
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
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="hero">
      <h1>Shorten Your Links.<br/>Expand Your <span className="accent-text">Reach.</span></h1>
      <p>
        A scalable, lightning-fast URL shortener with real-time analytics. 
        Paste your long URL below to get started.
      </p>

      <div className="glass-card" style={{ marginTop: '3.5rem', textAlign: 'left' }}>
        <form onSubmit={handleSubmit}>
          <div className="input-group">
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
          </div>
          
          <button type="button" className="advanced-toggle" onClick={() => setShowAdvanced(!showAdvanced)}>
            <Settings size={16} /> {showAdvanced ? 'Hide Advanced Options' : 'Show Advanced Options'}
          </button>

          {showAdvanced && (
            <div className="advanced-options">
              <div>
                <label>Custom Alias (Optional)</label>
                <input type="text" className="url-input" placeholder="e.g. my-portfolio" value={customAlias} onChange={(e) => setCustomAlias(e.target.value)} />
              </div>
              <div>
                <label>Expiration (Optional)</label>
                <input type="datetime-local" className="url-input" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
              </div>
              <div>
                <label>Password (Optional)</label>
                <input type="password" className="url-input" placeholder="Secret pin/password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
            </div>
          )}
        </form>
        
        {error && (
          <div className="error-toast">
            <span>{error}</span>
            <button type="button" className="toast-close" onClick={() => setError('')}>&times;</button>
          </div>
        )}

        {result && (
          <div className="result-box">
            <div className="result-header">
              <div>
                <div className="result-label">Your short URL is ready:</div>
                <a href={result.short_url} target="_blank" rel="noreferrer" className="result-url">
                  {result.short_url}
                </a>
              </div>
              
              <div className="result-actions">
                <Link to={`/stats/${result.short_id}`} className="btn-primary">
                  <BarChart2 size={18} /> Analytics
                </Link>
                <button onClick={handleCopy} className="copy-btn">
                  {copied ? <><Check size={18} /> Copied</> : <><Copy size={18} /> Copy</>}
                </button>
              </div>
            </div>

            <div className="qr-section">
               <div ref={qrRef} className="qr-box">
                 <QRCodeCanvas value={result.short_url} size={90} />
               </div>
               <div className="qr-info">
                 <h4>Share via QR Code</h4>
                 <p>Download and print the QR code or share it online.</p>
                 <button onClick={downloadQR} className="copy-btn">
                    <Download size={18} /> Download QR
                 </button>
               </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ShortenerForm;
