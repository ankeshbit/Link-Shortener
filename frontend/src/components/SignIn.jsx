import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, ShieldCheck } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

const GoogleIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
    <path
      fill="#4285F4"
      d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.65v3.03h3.88c2.27-2.09 3.665-5.17 3.665-9.12z"
    />
    <path
      fill="#34A853"
      d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.03c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.24v3.13C3.26 21.36 7.34 24 12 24z"
    />
    <path
      fill="#FBBC05"
      d="M5.28 14.29c-.25-.72-.38-1.49-.38-2.29s.13-1.57.38-2.29V6.58H1.24C.45 8.15 0 9.92 0 12s.45 3.85 1.24 5.42l4.04-3.13z"
    />
    <path
      fill="#EA4335"
      d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.34 0 3.26 2.64 1.24 6.58l4.04 3.13c.95-2.83 3.6-4.96 6.72-4.96z"
    />
  </svg>
);

const SignIn = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, loginWithGoogle } = useAuth();

  const returnTo = location.state?.from?.pathname
    ? `${location.state.from.pathname}${location.state.from.search || ''}${location.state.from.hash || ''}`
    : typeof location.state?.from === 'string'
      ? location.state.from
      : '/dashboard';

  useEffect(() => {
    if (isAuthenticated) {
      navigate(returnTo, { replace: true });
    }
  }, [isAuthenticated, navigate, returnTo]);

  const handleGoogleSignIn = async () => {
    setLoading(true);
    setError('');

    try {
      await loginWithGoogle();
      navigate(returnTo, { replace: true });
    } catch (err) {
      console.error('Google Sign-In failed:', err);
      if (err.code === 'auth/popup-closed-by-user') {
        setError('Sign-in cancelled. Please complete authentication via the Google popup.');
      } else if (err.code === 'auth/popup-blocked') {
        setError('Google sign-in popup was blocked by your browser. Please allow popups for this site.');
      } else if (err.code === 'auth/cancelled-popup-request') {
        // Ignored duplicate popup
      } else if (err.message) {
        setError(err.message);
      } else {
        setError('Authentication failed. Please verify your connection and try again.');
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
          <h2 className="login-title">Welcome to ByteLink</h2>
          <p
            style={{
              color: 'var(--text-secondary)',
              textAlign: 'center',
              fontSize: '14px',
              marginTop: '6px',
              lineHeight: '1.5',
            }}
          >
            Authenticate securely using your Google account to create, manage, and track real-time URL analytics.
          </p>
        </div>

        {error && (
          <div className="error-toast-new" role="alert" style={{ width: '100%' }}>
            <span>{error}</span>
          </div>
        )}

        <div style={{ marginTop: '1rem', width: '100%' }}>
          <button
            type="button"
            className="btn-login-primary"
            onClick={handleGoogleSignIn}
            disabled={loading}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '12px',
              width: '100%',
              padding: '14px 20px',
              fontSize: '15px',
              fontWeight: '600',
              borderRadius: '12px',
              cursor: loading ? 'not-allowed' : 'pointer',
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: 'var(--text-primary)',
              transition: 'all 0.2s ease',
            }}
          >
            {loading ? (
              <>
                <Loader2 size={18} className="spinner" />
                <span>Authenticating with Google...</span>
              </>
            ) : (
              <>
                <GoogleIcon />
                <span>Continue with Google</span>
              </>
            )}
          </button>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            marginTop: '1.5rem',
            color: 'var(--text-muted)',
            fontSize: '12px',
          }}
        >
          <ShieldCheck size={14} color="var(--accent)" />
          <span>Secured by Firebase Authentication & OAuth 2.0</span>
        </div>
      </div>
    </div>
  );
};

export default SignIn;
