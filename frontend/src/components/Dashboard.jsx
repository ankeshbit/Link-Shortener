import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api/axios';
import { 
  BarChart2, Trash2, ExternalLink, Link as LinkIcon, Plus, 
  TrendingUp, Clock, Copy, Check, Power, Edit2, X
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

const Dashboard = () => {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const [editingLink, setEditingLink] = useState(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editForm, setEditForm] = useState({
    target_url: '',
    max_clicks: '',
    expires_at: '',
    is_active: true,
    password: '',
    clear_password: false,
  });
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

    fetchUserLinks();
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

  const handleToggleActive = async (link) => {
    const nextStatus = !link.is_active;
    try {
      const res = await api.patch(`/api/user/links/${link.short_id}`, {
        is_active: nextStatus,
      });
      setLinks(links.map((l) => (l.short_id === link.short_id ? { ...l, is_active: res.data.is_active } : l)));
    } catch {
      alert('Failed to change link status. Please try again.');
    }
  };

  const handleOpenEdit = (link) => {
    setEditingLink(link);
    setEditForm({
      target_url: link.target_url || '',
      max_clicks: link.max_clicks !== null && link.max_clicks !== undefined ? String(link.max_clicks) : '',
      expires_at: link.expires_at ? new Date(link.expires_at).toISOString().slice(0, 16) : '',
      is_active: link.is_active !== undefined ? link.is_active : true,
      password: '',
      clear_password: false,
    });
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingLink) return;
    setSavingEdit(true);
    try {
      const payload = {
        target_url: editForm.target_url,
        is_active: editForm.is_active,
      };

      if (editForm.max_clicks !== '') {
        payload.max_clicks = parseInt(editForm.max_clicks, 10);
      } else {
        payload.clear_max_clicks = true;
      }

      if (editForm.expires_at !== '') {
        payload.expires_at = new Date(editForm.expires_at).toISOString();
      } else {
        payload.clear_expires_at = true;
      }

      if (editForm.clear_password) {
        payload.clear_password = true;
      } else if (editForm.password) {
        payload.password = editForm.password;
      }

      const res = await api.patch(`/api/user/links/${editingLink.short_id}`, payload);
      setLinks(links.map((l) => (l.short_id === editingLink.short_id ? { ...l, ...res.data } : l)));
      setEditingLink(null);
    } catch (err) {
      alert(err.response?.data?.message || err.response?.data?.detail || 'Failed to update link.');
    } finally {
      setSavingEdit(false);
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
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '700px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: '13px' }}>
                  <th style={{ padding: '12px 16px', fontWeight: '600' }}>Short Link</th>
                  <th style={{ padding: '12px 16px', fontWeight: '600' }}>Target Destination</th>
                  <th style={{ padding: '12px 16px', fontWeight: '600', textAlign: 'center' }}>Clicks / Max</th>
                  <th style={{ padding: '12px 16px', fontWeight: '600', textAlign: 'center' }}>Status</th>
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
                    <td style={{ padding: '16px 16px', color: 'var(--text-secondary)', maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <a href={link.target_url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        {link.target_url} <ExternalLink size={12} style={{ opacity: 0.5 }} />
                      </a>
                    </td>
                    <td style={{ padding: '16px 16px', textAlign: 'center', fontWeight: '700', color: 'var(--text-primary)' }}>
                      {link.clicks_count} {link.max_clicks ? `/ ${link.max_clicks}` : ''}
                    </td>
                    <td style={{ padding: '16px 16px', textAlign: 'center' }}>
                      <button
                        onClick={() => handleToggleActive(link)}
                        style={{
                          padding: '4px 10px',
                          borderRadius: '9999px',
                          fontSize: '12px',
                          fontWeight: '600',
                          cursor: 'pointer',
                          border: 'none',
                          backgroundColor: link.is_active ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                          color: link.is_active ? '#22c55e' : '#ef4444',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                        title={link.is_active ? "Click to disable link" : "Click to enable link"}
                      >
                        <Power size={11} /> {link.is_active ? 'Active' : 'Disabled'}
                      </button>
                    </td>
                    <td style={{ padding: '16px 16px', color: 'var(--text-muted)', fontSize: '13px' }}>
                      {link.created_at ? formatDistanceToNow(new Date(link.created_at), { addSuffix: true }) : 'N/A'}
                    </td>
                    <td style={{ padding: '16px 16px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                        <button 
                          onClick={() => handleOpenEdit(link)} 
                          className="btn-action" 
                          style={{ padding: '6px 12px', borderRadius: '8px', fontSize: '12px' }}
                          title="Edit Link Settings"
                        >
                          <Edit2 size={14} /> Edit
                        </button>
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

      {/* Edit Link Modal */}
      {editingLink && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000,
          padding: '16px',
        }}>
          <div style={{
            background: '#1e293b',
            borderRadius: '16px',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            padding: '24px',
            maxWidth: '480px',
            width: '100%',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-primary)' }}>
                Edit Link: <span style={{ color: 'var(--accent)' }}>{editingLink.short_id}</span>
              </h3>
              <button 
                onClick={() => setEditingLink(null)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveEdit}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                  Target Destination URL
                </label>
                <input 
                  type="url"
                  required
                  value={editForm.target_url}
                  onChange={(e) => setEditForm({ ...editForm, target_url: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    background: 'rgba(0,0,0,0.2)',
                    color: 'white',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                    Max Clicks (optional)
                  </label>
                  <input 
                    type="number"
                    min="1"
                    placeholder="Unlimited"
                    value={editForm.max_clicks}
                    onChange={(e) => setEditForm({ ...editForm, max_clicks: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      background: 'rgba(0,0,0,0.2)',
                      color: 'white',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                    Expiration Date
                  </label>
                  <input 
                    type="datetime-local"
                    value={editForm.expires_at}
                    onChange={(e) => setEditForm({ ...editForm, expires_at: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      background: 'rgba(0,0,0,0.2)',
                      color: 'white',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                  Update Password (optional)
                </label>
                <input 
                  type="password"
                  placeholder="Leave blank to keep unchanged"
                  disabled={editForm.clear_password}
                  value={editForm.password}
                  onChange={(e) => setEditForm({ ...editForm, password: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    background: 'rgba(0,0,0,0.2)',
                    color: 'white',
                    boxSizing: 'border-box',
                    opacity: editForm.clear_password ? 0.5 : 1,
                  }}
                />
                {editingLink.has_password && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px', cursor: 'pointer' }}>
                    <input 
                      type="checkbox"
                      checked={editForm.clear_password}
                      onChange={(e) => setEditForm({ ...editForm, clear_password: e.target.checked, password: '' })}
                    />
                    Remove existing password protection
                  </label>
                )}
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text-primary)', cursor: 'pointer' }}>
                  <input 
                    type="checkbox"
                    checked={editForm.is_active}
                    onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                  />
                  Link is active (enabled for redirects)
                </label>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setEditingLink(null)}
                  className="btn-action"
                  style={{ padding: '8px 16px', borderRadius: '8px' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="btn-action primary-action"
                  style={{ padding: '8px 16px', borderRadius: '8px' }}
                >
                  {savingEdit ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
