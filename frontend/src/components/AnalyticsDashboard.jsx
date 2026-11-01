import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import api, { API_BASE_URL } from '../api/axios';
import { auth } from '../auth/firebase';
import { 
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, PointElement, 
  LineElement, Title, Tooltip, Legend, Filler 
} from 'chart.js';
import { Bar } from 'react-chartjs-2';
import { ArrowLeft, MapPin, Clock, Info } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

ChartJS.register(
  CategoryScale, LinearScale, BarElement, PointElement, LineElement, 
  Title, Tooltip, Legend, Filler
);

const AnalyticsDashboard = () => {
  const { id } = useParams();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    let ws = null;
    let fallbackInterval = null;
    let reconnectTimeout = null;
    let isMounted = true;

    const fetchStats = async () => {
      try {
        const res = await api.get(`/api/stats/${id}`);
        if (isMounted) {
          setStats(res.data);
          setError('');
        }
      } catch (err) {
        if (isMounted) {
          if (err.response?.status === 404) {
            setError('This short link does not exist or you do not have permission to view its stats.');
          } else {
            setError('Error fetching stats. Please verify your connection.');
          }
        }
      }
    };

    const connectWS = async () => {
      if (!isMounted) return;

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
          if (!isMounted) return;
          // Authenticate via initial frame
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
            if (isMounted && (message.type === 'initial_stats' || message.type === 'click_update')) {
              setStats(message.data);
            }
          } catch (e) {
            console.error('Failed to parse websocket message', e);
          }
        };

        ws.onerror = () => {
          if (ws) ws.close();
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setIsLive(false);

          // Re-establish HTTP polling fallback
          if (!fallbackInterval) {
            fetchStats();
            fallbackInterval = setInterval(fetchStats, 5000);
          }

          // Schedule reconnection attempt
          if (reconnectTimeout) clearTimeout(reconnectTimeout);
          reconnectTimeout = setTimeout(connectWS, 6000);
        };
      } catch (e) {
        console.error('Websocket initialization error', e);
        if (isMounted) {
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
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
      }
      if (fallbackInterval) clearInterval(fallbackInterval);
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
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

      <div className="stats-grid-main">
        <div className="stats-card-main">
          <div className="stats-card-main-title">Total Clicks</div>
          <div className="stats-card-main-number">{stats.total_clicks}</div>
        </div>

        <div className="stats-chart-card">
          <h3 className="stats-chart-title">Geographic Distribution</h3>
          <div className="chart-container">
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
