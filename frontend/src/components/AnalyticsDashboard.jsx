import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler } from 'chart.js';
import { Line } from 'react-chartjs-2';
import { ArrowLeft, MapPin, Clock } from 'lucide-react';
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
      <h2>Loading real-time analytics...</h2>
    </div>
  );

  const countryLabels = Object.keys(stats.countries);
  const countryData = Object.values(stats.countries);

  const chartData = {
    labels: countryLabels.length > 0 ? countryLabels : ['No data'],
    datasets: [
      {
        label: 'Clicks by Country',
        data: countryData.length > 0 ? countryData : [0],
        borderColor: '#3ECF8E',
        backgroundColor: (context) => {
          const chart = context.chart;
          const {ctx, chartArea} = chart;
          if (!chartArea) return 'rgba(62, 207, 142, 0.15)';
          const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          gradient.addColorStop(0, 'rgba(62, 207, 142, 0.15)');
          gradient.addColorStop(1, 'rgba(62, 207, 142, 0)');
          return gradient;
        },
        fill: true,
        tension: 0.4,
        cubicInterpolationMode: 'monotone', // smooth monotone interpolation
        pointBackgroundColor: '#7DD3FC', // Light blue dots
        pointBorderColor: '#070B14',
        pointHoverBackgroundColor: '#fff',
        pointHoverBorderColor: '#7DD3FC',
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    color: '#9CA3AF',
    layout: {
      padding: {
        left: 16,
        right: 32, // Last point remains 32px away from right border
        top: 16,
        bottom: 24 // Leave bottom padding
      }
    },
    animation: {
      duration: 1500, // Animate line drawing over 1.5s
      easing: 'easeInOutQuart'
    },
    plugins: {
      legend: { position: 'top', labels: { color: '#9CA3AF', font: { family: 'Geist' } } },
      tooltip: {
        backgroundColor: '#0D1321',
        titleColor: '#fff',
        bodyColor: '#3ECF8E',
        borderColor: 'rgba(255,255,255,0.08)',
        borderWidth: 1,
        padding: 12,
        boxPadding: 4,
      }
    },
    scales: {
      y: { ticks: { color: '#6B7280', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.04)' } },
      x: { ticks: { color: '#6B7280' }, grid: { color: 'rgba(255,255,255,0.04)' } }
    }
  };

  return (
    <div style={{ animation: 'fadeIn 0.5s ease-out' }}>
      <div className="stats-page-header">
        <Link to="/" className="btn-back" aria-label="Back to link shortener form page">
          <ArrowLeft size={16} aria-hidden="true" /> Back to Shortener
        </Link>
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
            <Line data={chartData} options={chartOptions} />
          </div>
        </div>
      </div>

      <div className="stats-log-card">
        <h3 className="stats-log-title">
          <Clock size={20} color="var(--accent)" aria-hidden="true" /> Recent Clicks Log
        </h3>
        {stats.recent_clicks.length === 0 ? (
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
                    {click.city ? `${click.city}, ${click.country}` : 'Unknown Location'}
                  </span>
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
