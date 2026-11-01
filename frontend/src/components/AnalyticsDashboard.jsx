import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import api, { API_BASE_URL } from '../api/axios';
import { auth } from '../auth/firebase';
import { 
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, PointElement, 
  LineElement, Title, Tooltip, Legend, Filler 
} from 'chart.js';
import { Bar } from 'react-chartjs-2';
import { ArrowLeft, MapPin, Clock, Info, AlertCircle } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

ChartJS.register(
  CategoryScale, LinearScale, BarElement, PointElement, LineElement, 
  Title, Tooltip, Legend, Filler
);

const AnalyticsDashboard = () => {
  const { id } = useParams();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    // Reset state when id changes
    setStats(null);
    setError('');
    setPollError('');
    setIsLive(false);

    let ws = null;
    let fallbackInterval = null;
    let reconnectTimeout = null;
    let isMounted = true;
    let isTerminal = false;

    const stopAll = () => {
      isTerminal = true;
      if (fallbackInterval) {
        clearInterval(fallbackInterval);
        fallbackInterval = null;
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
        ws = null;
      }
    };

    const fetchStats = async () => {
      if (!isMounted || isTerminal) return;
      try {
        const res = await api.get(`/api/stats/${id}`);
        if (isMounted && !isTerminal) {
          setStats(res.data);
          setError('');
          setPollError('');
        }
      } catch (err) {
        if (!isMounted) return;
        const status = err.response?.status;
        if (status === 404 || status === 403) {
          stopAll();
          setError(
            status === 404
              ? 'This short link does not exist.'
              : 'You do not have permission to view stats for this link.'
          );
          setStats(null);
          return;
        }

        // Non-terminal error: If stats already present, keep them visible with banner
        setStats((prevStats) => {
          if (prevStats) {
            setPollError('Unable to refresh live stats. Showing cached metrics.');
            return prevStats;
          }
          setError('Error fetching stats. Please verify your connection.');
          return null;
        });
      }
    };

    const connectWS = async () => {
      if (!isMounted || isTerminal) return;

      let token = '';
      try {
        if (auth.currentUser) {
          token = await auth.currentUser.getIdToken();
          localStorage.setItem('token', token);
        } else {
          token = localStorage.getItem('token') || '';
        }
      } catch {
        token = localStorage.getItem('token') || '';
      }

      try {
        const apiURL = new URL(API_BASE_URL);
        apiURL.protocol = apiURL.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsURL = `${apiURL.origin}/api/ws/stats/${id}`;

        ws = new WebSocket(wsURL);

        ws.onopen = () => {
          if (!isMounted || isTerminal) {
            if (ws) ws.close();
            return;
          }
          ws.send(JSON.stringify({ type: 'auth', token }));
          setIsLive(true);
          if (fallbackInterval) {
            clearInterval(fallbackInterval);
            fallbackInterval = null;
          }
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            if (isMounted && !isTerminal && (message.type === 'initial_stats' || message.type === 'click_update')) {
              setStats(message.data);
              setPollError('');
            }
          } catch (e) {
            console.error('Failed to parse websocket message', e);
          }
        };

        ws.onerror = () => {
          if (ws) ws.close();
        };

        ws.onclose = () => {
          if (!isMounted || isTerminal) return;
          setIsLive(false);

          // Re-establish HTTP polling fallback if not terminal
          if (!fallbackInterval && !isTerminal) {
            fetchStats();
            fallbackInterval = setInterval(fetchStats, 5000);
          }

          if (reconnectTimeout) clearTimeout(reconnectTimeout);
          if (!isTerminal) {
            reconnectTimeout = setTimeout(connectWS, 6000);
          }
        };
      } catch (e) {
        console.error('Websocket initialization error', e);
        if (isMounted && !isTerminal) {
          setIsLive(false);
          if (!fallbackInterval) {
            fetchStats();
            fallbackInterval = setInterval(fetchStats, 5000);
          }
        }
      }
    };

    // Initial fetch and start connection
    fetchStats();
    connectWS();

    return () => {
      isMounted = false;
      stopAll();
    };
  }, [id]);

  if (error) return (
    <div className="stats-card-main" style={{ textAlign: 'center', marginTop: '4rem', padding: '48px' }}>
      <h2 style={{ marginBottom: '1.5rem', fontWeight: '700' }}>{error}</h2>
      <Link to="/" className="btn-action primary-action" style={{ display: 'inline-flex', width: 'fit-content', margin: '0 auto' }} role="button">
        Go Back
      </Link>
    </div>
  );

  if (!stats) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', marginTop: '8rem', gap: '16px' }}>
      <span className="spinner" style={{ width: '28px', height: '28px', borderWidth: '3px' }}></span>
      <h2>Loading analytics...</h2>
    </div>
  );

  const countryLabels = Object.keys(stats.countries || {});
  const countryData = Object.values(stats.countries || {});

  const chartData = {
    labels: countryLabels.length > 0 ? countryLabels : ['No data'],
    datasets: [
      {
        label: 'Clicks by Country',
        data: countryData.length > 0 ? countryData : [0],
        backgroundColor: 'rgba(62, 207, 142, 0.4)',
        borderColor: '#3ECF8E',
        borderWidth: 1.5,
        borderRadius: 8,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    color: '#9CA3AF',
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0D1321',
        titleColor: '#fff',
        bodyColor: '#3ECF8E',
        borderColor: 'rgba(255,255,255,0.08)',
        borderWidth: 1,
        padding: 12,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { color: '#6B7280', stepSize: 1 },
        grid: { color: 'rgba(255,255,255,0.04)' },
      },
      x: {
        ticks: { color: '#6B7280' },
        grid: { display: false },
      },
    },
  };

  return (
    <div style={{ animation: 'fadeIn 0.5s ease-out' }}>
      <div className="stats-page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', marginBottom: '1rem' }}>
          <Link to={localStorage.getItem('token') ? "/dashboard" : "/"} className="btn-back" aria-label="Back to dashboard or home page">
            <ArrowLeft size={16} aria-hidden="true" /> Back
          </Link>
          {isLive ? (
            <span className="badge-live" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span className="spinner" style={{ width: '8px', height: '8px', border: 'none', background: 'var(--accent)', animation: 'pulse-glow 1s infinite alternate' }}></span>
              Live WebSocket Stream
            </span>
          ) : (
            <span className="badge-live" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B' }}>
              <Info size={12} /> Auto-Refreshing (Polling)
            </span>
          )}
        </div>
        <h1 className="stats-title">Analytics Dashboard</h1>
        <p className="stats-target">
          Tracking links for: <a href={stats.target_url} target="_blank" rel="noopener noreferrer">{stats.target_url}</a>
        </p>
      </div>

      {pollError && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            borderRadius: '10px',
            padding: '10px 14px',
            color: '#fbbf24',
            fontSize: '14px',
            marginBottom: '1.5rem',
          }}
        >
          <AlertCircle size={16} style={{ flexShrink: 0 }} />
          <span>{pollError}</span>
        </div>
      )}

      <div className="stats-grid-main">
        <div className="stats-card-main">
          <div className="stats-card-main-title">Total Clicks</div>
          <div className="stats-card-main-number">{stats.total_clicks}</div>
        </div>

        <div className="stats-chart-card">
          <h3 className="stats-chart-title">Geographic Distribution</h3>
          <div className="chart-container" style={{ height: '320px', position: 'relative', width: '100%' }}>
            <Bar data={chartData} options={chartOptions} />
          </div>
        </div>
      </div>

      <div className="stats-log-card">
        <h3 className="stats-log-title">
          <Clock size={20} color="var(--accent)" aria-hidden="true" /> Recent Clicks Log
        </h3>
        {!stats.recent_clicks || stats.recent_clicks.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontStyle: 'italic', padding: '1rem 0' }}>
            No clicks yet. Share your short link to gather data!
          </p>
        ) : (
          <ul className="stats-log-list">
            {stats.recent_clicks.slice().reverse().map((click, i) => (
              <li key={i} className="stats-log-item">
                <div className="log-item-details">
                  <span className="log-item-ip">{click.ip || 'Hidden IP'}</span>
                  <span className="log-item-geo">
                    <MapPin size={12} style={{ color: 'var(--accent-secondary)', marginRight: '4px' }} aria-hidden="true" /> 
                    {click.city ? `${click.city}, ${click.country}` : (click.country || 'Unknown Location')}
                  </span>
                  {click.device && (
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', background: 'rgba(255,255,255,0.06)', padding: '2px 6px', borderRadius: '4px' }}>
                      {click.device} ({click.browser || click.os || 'Browser'})
                    </span>
                  )}
                </div>
                <div className="log-item-time">
                  {click.time ? formatDistanceToNow(new Date(click.time), { addSuffix: true }) : 'Just now'}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default AnalyticsDashboard;
