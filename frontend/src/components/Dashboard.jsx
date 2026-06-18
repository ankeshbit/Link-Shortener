import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api/axios';
import { 
  BarChart2, Trash2, ExternalLink, Link as LinkIcon, Plus, 
  TrendingUp, Clock, Copy, Check, LogOut 
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

const Dashboard = () => {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchUserLinks = async () => {
      try {
        const res = await api.get('/api/user/links');
        setLinks(res.data);
      } catch (err) {
        if (err.response?.status === 401) {
          localStorage.removeItem('token');
          navigate('/login');
        } else {
          setError('Failed to load your shortened URLs. Please try again.');
        }
      } finally {
        setLoading(false);
      }
    };

    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
    } else {
      fetchUserLinks();
    }
  }, [navigate]);

  const handleDelete = async (shortId) => {
    if (!window.confirm('Are you sure you want to delete this short URL?')) return;
    try {
      await api.delete(`/api/user/links/${shortId}`);
      setLinks(links.filter((link) => link.short_id !== shortId));
    } catch {
      alert('Failed to delete the link. Please try again.');
    }
  };

  const handleCopy = (shortUrl, shortId) => {
    navigator.clipboard.writeText(shortUrl);
    setCopiedId(shortId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const totalClicks = links.reduce((sum, link) => sum + link.clicks_count, 0);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', marginTop: '8rem', gap: '16px' }}>
        <span className="spinner" style={{ width: '28px', height: '28px', borderWidth: '3px' }}></span>
        <h2>Loading your dashboard...</h2>
      </div>
    );
  }

  return (
    <div style={{ animation: 'fadeIn 0.5s ease-out' }}>
      <div className="stats-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h1 className="stats-title">User Dashboard</h1>
          <p style={{ color: 'var(--text-secondary)' }}>Manage your shortened links and track audience analytics.</p>
        </div>
        <Link to="/" className="btn-action primary-action" style={{ borderRadius: '12px', padding: '10px 20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Plus size={16} /> Shorten New Link
        </Link>
      </div>

      {/* Stats Summary Cards */}
      <div className="stats-grid-main" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '24px', marginBottom: '2.5rem' }}>
        <div className="stats-card-main">
          <div className="stats-card-main-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
            <LinkIcon size={18} color="var(--accent)" />
            Total Links
          </div>
          <div className="stats-card-main-number">{links.length}</div>
        </div>

        <div className="stats-card-main">
          <div className="stats-card-main-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
            <TrendingUp size={18} color="var(--accent-secondary)" />
            Accumulated Clicks
          </div>
          <div className="stats-card-main-number">{totalClicks}</div>
        </div>
      </div>

      {error && (
        <div className="error-toast-new" role="alert" style={{ marginBottom: '2rem' }}>
          <span>{error}</span>
          <button type="button" className="error-close-new" onClick={() => setError('')}>&times;</button>
        </div>
      )}

      {/* Links List Card */}
      <div className="stats-log-card" style={{ padding: '32px' }}>
        <h3 className="stats-log-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1.5rem', color: 'var(--text-primary)' }}>
          <Clock size={20} color="var(--accent)" /> Shortened Links History
        </h3>

        {links.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '48px 0', border: '1px dashed var(--border)', borderRadius: '16px' }}>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>You haven't shortened any URLs yet.</p>
            <Link to="/" className="btn-action" style={{ display: 'inline-flex' }}>
              Create Your First Link
            </Link>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '600px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: '13px' }}>
                  <th style={{ padding: '12px 16px', fontWeight: '600' }}>Short Link</th>
                  <th style={{ padding: '12px 16px', fontWeight: '600' }}>Target Destination</th>
                  <th style={{ padding: '12px 16px', fontWeight: '600', textAlign: 'center' }}>Clicks</th>
                  <th style={{ padding: '12px 16px', fontWeight: '600' }}>Created</th>
                  <th style={{ padding: '12px 16px', fontWeight: '600', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {links.map((link) => (
                  <tr key={link.id} style={{ borderBottom: '1px solid var(--border)', transition: 'background-color 0.2s' }} className="table-row-hover">
                    <td style={{ padding: '16px 16px', fontWeight: '600' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ color: 'var(--accent-secondary)' }}>{link.short_id}</span>
                        <button 
                          onClick={() => handleCopy(link.short_url, link.id)}
                          style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', padding: '2px' }}
                          title="Copy Link"
                        >
                          {copiedId === link.id ? <Check size={14} color="var(--accent)" /> : <Copy size={14} />}
                        </button>
                      </div>
                    </td>
                    <td style={{ padding: '16px 16px', color: 'var(--text-secondary)', maxWidth: '250px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <a href={link.target_url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        {link.target_url} <ExternalLink size={12} style={{ opacity: 0.5 }} />
                      </a>
                    </td>
                    <td style={{ padding: '16px 16px', textAlign: 'center', fontWeight: '700', color: 'var(--text-primary)' }}>
                      {link.clicks_count}
                    </td>
                    <td style={{ padding: '16px 16px', color: 'var(--text-muted)', fontSize: '13px' }}>
                      {link.created_at ? formatDistanceToNow(new Date(link.created_at), { addSuffix: true }) : 'N/A'}
                    </td>
                    <td style={{ padding: '16px 16px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                        <Link 
                          to={`/stats/${link.short_id}`} 
                          className="btn-action" 
                          style={{ padding: '6px 12px', borderRadius: '8px', fontSize: '12px' }}
                          title="View Live Analytics"
                        >
                          <BarChart2 size={14} /> Stats
                        </Link>
                        <button 
                          onClick={() => handleDelete(link.short_id)} 
                          className="btn-action" 
                          style={{ padding: '6px 12px', borderRadius: '8px', fontSize: '12px', color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.2)' }}
                          title="Delete Link"
                        >
                          <Trash2 size={14} /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
