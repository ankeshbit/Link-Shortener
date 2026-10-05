import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Mail, Lock, ArrowLeft, Loader2 } from 'lucide-react';
import api from '../api/axios';
import { useAuth } from '../auth/AuthContext';

const SignIn = () => {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const { setAuthenticated } = useAuth();
  const returnTo = location.state?.from?.pathname
    ? `${location.state.from.pathname}${location.state.from.search || ''}${location.state.from.hash || ''}`
    : typeof location.state?.from === 'string'
      ? location.state.from
      : '/dashboard';

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    setIsRegister(params.get('mode') === 'signup');
  }, [location.search]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError('');

    const endpoint = isRegister ? '/api/auth/register' : '/api/auth/login';

    try {
      const res = await api.post(endpoint, { email, password });
      const { access_token, refresh_token } = res.data;
      
      localStorage.setItem('token', access_token);
      if (refresh_token) {
        localStorage.setItem('refreshToken', refresh_token);
      }
      setAuthenticated(true);
      navigate(returnTo, { replace: true });
    } catch (err) {
      if (err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'string') {
          setError(detail);
        } else if (Array.isArray(detail)) {
          setError(detail.map(d => d.msg || d).join(', '));
        } else {
          setError(JSON.stringify(detail));
        }
      } else {
        setError(`Failed to ${isRegister ? 'register' : 'sign in'}. Please verify your network connections.`);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container" style={{ animation: 'fadeIn 0.5s ease-out' }}>
      <div className="login-card">
        <button 
          onClick={() => navigate('/')} 
          className="btn-action" 
          style={{ width: 'fit-content', padding: '8px 12px', borderRadius: '10px' }}
          aria-label="Back to home"
        >
          <ArrowLeft size={16} /> Back
        </button>

        <div>
          <h2 className="login-title">{isRegister ? 'Create an account' : 'Welcome back'}</h2>
          <p style={{ color: 'var(--text-secondary)', textAlign: 'center', fontSize: '14px', marginTop: '4px' }}>
            {isRegister 
              ? 'Register credentials below to save and track short links' 
              : 'Enter your credentials to access your dashboard'}
          </p>
        </div>

        {error && (
          <div className="error-toast-new" role="alert" style={{ width: '100%' }}>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="advanced-field">
            <label htmlFor="email">Email Address</label>
            <div style={{ position: 'relative' }}>
              <Mail 
                size={16} 
                style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} 
              />
              <input 
                id="email"
                type="email" 
                className="advanced-input" 
                placeholder="you@example.com" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{ paddingLeft: '38px', width: '100%', boxSizing: 'border-box' }}
                required 
              />
            </div>
          </div>

          <div className="advanced-field">
            <label htmlFor="password">Password</label>
            <div style={{ position: 'relative' }}>
              <Lock 
                size={16} 
                style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} 
              />
              <input 
                id="password"
                type="password" 
                className="advanced-input" 
                placeholder="••••••••" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ paddingLeft: '38px', width: '100%', boxSizing: 'border-box' }}
                required 
              />
            </div>
          </div>

          <button type="submit" className="btn-login-primary" disabled={loading}>
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                <Loader2 size={16} className="spinner" />
                <span>Processing...</span>
              </div>
            ) : (
              isRegister ? 'Sign Up' : 'Sign In'
            )}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: '1rem', fontSize: '14px' }}>
          <button 
            type="button" 
            onClick={() => {
              setIsRegister(!isRegister);
              setError('');
            }}
            style={{ background: 'transparent', border: 'none', color: 'var(--accent-secondary)', cursor: 'pointer', fontWeight: '500' }}
          >
            {isRegister ? 'Already have an account? Sign In' : "Don't have an account? Sign Up"}
          </button>
        </div>

      </div>
    </div>
  );
};

export default SignIn;
