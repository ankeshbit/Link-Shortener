import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api/axios';
import { 
  BarChart2, Trash2, Link as LinkIcon, Plus, 
  TrendingUp, Clock, Copy, Check 
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { copyText } from '../utils/clipboard';
import { useAuth } from '../auth/AuthContext';

const Dashboard = () => {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const { signOut } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    let isMounted = true;
    const fetchUserLinks = async () => {
      try {
        const res = await api.get('/api/user/links');
        if (isMounted) {
          setLinks(res.data);
        }
      } catch (err) {
        if (!isMounted) return;
        if (err.response?.status === 401) {
          await signOut();
          navigate('/login', { state: { sessionExpired: true } });
        } else {
          setError('Failed to load your shortened URLs. Please try again.');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchUserLinks();
    return () => {
      isMounted = false;
    };
  }, [navigate, signOut]);

  const handleDelete = async (shortId) => {
    if (!window.confirm('Are you sure you want to delete this short URL?')) return;
    try {
      await api.delete(`/api/user/links/${shortId}`);
      setLinks((prev) => prev.filter((link) => link.short_id !== shortId));
    } catch {
      alert('Failed to delete the link. Please try again.');
    }
  };

  const handleCopy = async (shortUrl, shortId) => {
    const ok = await copyText(shortUrl);
    if (ok) {
      setCopiedId(shortId);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  const totalClicks = links.reduce((sum, link) => sum + (link.clicks_count || 0), 0);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', marginTop: '8rem', gap: '16px' }}>
        <span className="spinner" style={{ width: '28px', height: '28px', borderWidth: '3px' }}></span>
        <h2>Loading your dashboard...</h2>
      </div>
    );
  }

  return (
    <div className="dashboard-container" style={{ animation: 'fadeIn 0.5s ease-out', maxWidth: '1200px', margin: '2rem auto', padding: '0 1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: '700', color: 'var(--text-primary)' }}>Your Links</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Manage and track performance for your shortened URLs</p>
        </div>
        <Link to="/#hero-input" className="btn-nav-primary" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 18px' }}>
          <Plus size={18} />
          <span>Shorten New URL</span>
        </Link>
      </div>

      {error && (
        <div className="error-toast-new" role="alert" style={{ marginBottom: '1.5rem' }}>
          <span>{error}</span>
          <button type="button" onClick={() => setError('')} className="error-close-new">&times;</button>
        </div>
      )}

      {/* Aggregate Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div className="card-glass" style={{ padding: '1.5rem', borderRadius: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
            <span>Total Links</span>
            <LinkIcon size={20} color="var(--accent)" />
          </div>
          <div style={{ fontSize: '2rem', fontWeight: '700', color: 'var(--text-primary)' }}>{links.length}</div>
        </div>
        <div className="card-glass" style={{ padding: '1.5rem', borderRadius: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
            <span>Total Clicks</span>
            <TrendingUp size={20} color="#38bdf8" />
          </div>
          <div style={{ fontSize: '2rem', fontWeight: '700', color: 'var(--text-primary)' }}>{totalClicks}</div>
        </div>
      </div>

      {/* Links List */}
      {links.length === 0 ? (
        <div className="card-glass" style={{ padding: '3rem', textAlign: 'center', borderRadius: '16px' }}>
          <LinkIcon size={40} color="var(--text-muted)" style={{ margin: '0 auto 1rem auto' }} />
          <h3 style={{ color: 'var(--text-primary)', marginBottom: '0.5rem' }}>No links shortened yet</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>Create your first shortened link to view performance analytics.</p>
          <Link to="/#hero-input" className="btn-nav-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <Plus size={16} /> Shorten a link
          </Link>
        </div>
      ) : (
        <div className="card-glass" style={{ borderRadius: '16px', overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '700px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', background: 'rgba(255, 255, 255, 0.02)' }}>
                  <th style={{ padding: '1rem 1.5rem', color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600' }}>SHORT LINK</th>
                  <th style={{ padding: '1rem 1.5rem', color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600' }}>ORIGINAL URL</th>
                  <th style={{ padding: '1rem 1.5rem', color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600', textAlign: 'center' }}>CLICKS</th>
                  <th style={{ padding: '1rem 1.5rem', color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600' }}>CREATED</th>
                  <th style={{ padding: '1rem 1.5rem', color: 'var(--text-muted)', fontSize: '13px', fontWeight: '600', textAlign: 'right' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {links.map((link) => (
                  <tr key={link.short_id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                    <td style={{ padding: '1rem 1.5rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <a href={link.short_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', fontWeight: '600', textDecoration: 'none' }}>
                          {link.short_url}
                        </a>
                        <button
                          type="button"
                          onClick={() => handleCopy(link.short_url, link.short_id)}
                          style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: copiedId === link.short_id ? '#34d399' : 'var(--text-muted)', padding: '2px' }}
                          title="Copy to clipboard"
                        >
                          {copiedId === link.short_id ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                      </div>
                    </td>
                    <td style={{ padding: '1rem 1.5rem' }}>
                      <span style={{ color: 'var(--text-secondary)', display: 'block', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={link.original_url}>
                        {link.original_url}
                      </span>
                    </td>
                    <td style={{ padding: '1rem 1.5rem', textAlign: 'center', fontWeight: '600', color: 'var(--text-primary)' }}>
                      {link.clicks_count}
                    </td>
                    <td style={{ padding: '1rem 1.5rem', color: 'var(--text-muted)', fontSize: '13px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Clock size={13} />
                        <span>{link.created_at ? formatDistanceToNow(new Date(link.created_at), { addSuffix: true }) : 'Recently'}</span>
                      </div>
                    </td>
                    <td style={{ padding: '1rem 1.5rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                        <Link to={`/stats/${link.short_id}`} className="btn-action" style={{ padding: '6px 12px', fontSize: '13px' }}>
                          <BarChart2 size={14} /> Analytics
                        </Link>
                        <button onClick={() => handleDelete(link.short_id)} className="btn-action" style={{ padding: '6px 10px', color: '#f87171' }} title="Delete link">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
