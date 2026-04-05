import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend } from 'chart.js';
import { Line } from 'react-chartjs-2';
import { ArrowLeft, MapPin, MousePointerClick, Clock } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const AnalyticsDashboard = () => {
  const { id } = useParams();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await axios.get(`http://localhost:8000/api/stats/${id}`);
        setStats(res.data);
      } catch (err) {
        setError("Error fetching stats. This URL may not exist.");
      }
    };
    fetchStats();
    
    // Auto-refresh every 5 seconds
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, [id]);

  if (error) return <div className="glass-card" style={{ textAlign: 'center' }}><h2>{error}</h2><br/><Link to="/" style={{ color: 'var(--accent-primary)' }}>Go Back</Link></div>;
  if (!stats) return <div style={{ textAlign: 'center', marginTop: '4rem' }}><h2>Loading real-time analytics...</h2></div>;

  const countryLabels = Object.keys(stats.countries);
  const countryData = Object.values(stats.countries);

  const chartData = {
    labels: countryLabels.length > 0 ? countryLabels : ['No data'],
    datasets: [
      {
        label: 'Clicks by Country',
        data: countryData.length > 0 ? countryData : [0],
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99, 102, 241, 0.5)',
        tension: 0.4,
        pointBackgroundColor: '#ec4899',
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'top' },
      title: { display: true, text: 'Geographic Distribution', color: '#fff' },
    },
    scales: {
      y: { ticks: { color: '#9ca3af', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.1)' } },
      x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(255,255,255,0.1)' } }
    }
  };

  return (
    <div style={{ animation: 'fadeIn 0.5s ease-out' }}>
      <div style={{ marginBottom: '2rem' }}>
        <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', textDecoration: 'none', marginBottom: '1rem' }}>
          <ArrowLeft size={20} /> Back to Shortener
        </Link>
        <h1 style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>Analytics Dashboard</h1>
        <p style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          Tracking links for: <a href={stats.target_url} style={{ color: 'var(--accent-primary)' }}>{stats.target_url}</a>
        </p>
      </div>

      <div className="dashboard-grid">
        <div className="glass-card stat-card">
          <MousePointerClick size={48} color="#ec4899" style={{ marginBottom: '1rem' }} />
          <h3 style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>Total Clicks</h3>
          <div className="stat-number">{stats.total_clicks}</div>
        </div>

        <div className="glass-card stat-card" style={{ flex: 2 }}>
          <div className="chart-container">
            <Line data={chartData} options={chartOptions} />
          </div>
        </div>
      </div>

      <div className="glass-card" style={{ marginTop: '2rem' }}>
        <h3 style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Clock size={20} color="#6366f1" /> Recent Clicks List
        </h3>
        {stats.recent_clicks.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>No clicks yet.</p>
        ) : (
          <ul className="recent-clicks">
            {stats.recent_clicks.slice().reverse().map((click, i) => (
              <li key={i}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  <strong>{click.ip || 'Hidden IP'}</strong>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    <MapPin size={12} style={{ display:'inline', marginRight:'0.2rem' }}/> 
                    {click.city ? `${click.city}, ${click.country}` : 'Unknown Location'}
                  </span>
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
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
