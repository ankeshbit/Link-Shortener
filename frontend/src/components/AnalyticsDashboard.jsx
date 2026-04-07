import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler } from 'chart.js';
import { Line } from 'react-chartjs-2';
import { ArrowLeft, MapPin, MousePointerClick, Clock } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

// Register Filler for gradient under line chart
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

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
    
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, [id]);

  if (error) return (
    <div className="glass-card" style={{ textAlign: 'center', marginTop: '4rem' }}>
      <h2 style={{ marginBottom: '1rem' }}>{error}</h2>
      <Link to="/" className="btn-primary" style={{ display: 'inline-flex' }}>Go Back</Link>
    </div>
  );
  
  if (!stats) return <div style={{ textAlign: 'center', marginTop: '6rem' }}><h2>Loading real-time analytics...</h2></div>;

  const countryLabels = Object.keys(stats.countries);
  const countryData = Object.values(stats.countries);

  const chartData = {
    labels: countryLabels.length > 0 ? countryLabels : ['No data'],
    datasets: [
      {
        label: 'Clicks by Country',
        data: countryData.length > 0 ? countryData : [0],
        borderColor: '#55C1BF',
        backgroundColor: 'rgba(85, 193, 191, 0.2)', // Light teal gradient for charts
        fill: true,
        tension: 0.4,
        pointBackgroundColor: '#8b5cf6', // Soft purple dots
        pointBorderColor: '#fff',
        pointHoverBackgroundColor: '#fff',
        pointHoverBorderColor: '#8b5cf6',
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    color: '#94A3B8',
    plugins: {
      legend: { position: 'top', labels: { color: '#94A3B8', font: { family: 'Inter' } } },
      tooltip: {
        backgroundColor: 'rgba(2, 4, 10, 0.8)',
        titleColor: '#fff',
        bodyColor: '#55C1BF',
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        padding: 12,
        boxPadding: 4,
      }
    },
    scales: {
      y: { ticks: { color: '#64748b', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' } },
      x: { ticks: { color: '#64748b' }, grid: { color: 'rgba(255,255,255,0.05)' } }
    }
  };

  return (
    <div style={{ animation: 'fadeIn 0.5s ease-out' }}>
      <div style={{ marginBottom: '3rem' }}>
        <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', textDecoration: 'none', marginBottom: '1.5rem', transition: 'color 0.2s', fontWeight: '500' }}>
          <ArrowLeft size={18} /> Back to Shortener
        </Link>
        <h1 style={{ fontSize: '3rem', marginBottom: '0.8rem', letterSpacing: '-1px' }}>Analytics Dashboard</h1>
        <p style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.1rem' }}>
          Tracking links for: <a href={stats.target_url} style={{ color: 'var(--accent-primary)', textDecoration: 'none' }}>{stats.target_url}</a>
        </p>
      </div>

      <div className="dashboard-grid">
        <div className="glass-card stat-card">
          <MousePointerClick size={40} color="var(--accent-primary)" style={{ marginBottom: '1.5rem', opacity: '0.8' }} />
          <h3 className="stat-card-title">Total Clicks</h3>
          <div className="stat-number">{stats.total_clicks}</div>
        </div>

        <div className="glass-card stat-card" style={{ flex: 2, padding: '1.5rem 2rem' }}>
          <h3 className="stat-card-title" style={{ marginBottom: '1rem' }}>Geographic Distribution</h3>
          <div className="chart-container">
            <Line data={chartData} options={chartOptions} />
          </div>
        </div>
      </div>

      <div className="glass-card" style={{ marginTop: '2.5rem' }}>
        <h3 style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '1.25rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--text-primary)' }}>
          <Clock size={20} color="var(--accent-primary)" /> Recent Clicks Log
        </h3>
        {stats.recent_clicks.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontStyle: 'italic', padding: '1rem 0' }}>No clicks yet. Share your short link to gather data!</p>
        ) : (
          <ul className="recent-clicks">
            {stats.recent_clicks.slice().reverse().map((click, i) => (
              <li key={i}>
                <div>
                  <span className="click-ip">{click.ip || 'Hidden IP'}</span>
                  <span className="click-location">
                    <MapPin size={14} style={{ color: 'var(--accent-secondary)' }}/> 
                    {click.city ? `${click.city}, ${click.country}` : 'Unknown Location'}
                  </span>
                </div>
                <div className="click-time">
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
