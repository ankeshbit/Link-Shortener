import { useLocation, useNavigate } from 'react-router-dom';

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
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

const AuthPrompt = ({ onContinue, onAuthenticate }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const from = `${location.pathname}${location.search}${location.hash}`;

  const handleContinueWithGoogle = () => {
    onAuthenticate?.();
    navigate('/login', { state: { from } });
  };

  return (
    <div className="auth-prompt" role="dialog" aria-labelledby="auth-prompt-title">
      <div className="auth-prompt-card">
        <h2 id="auth-prompt-title">Authentication required</h2>
        <p>Sign in with your Google account to create and manage custom short links with live analytics.</p>
        <div className="auth-prompt-actions" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <button
            type="button"
            className="btn-login-primary"
            onClick={handleContinueWithGoogle}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '10px',
              padding: '12px 18px',
            }}
          >
            <GoogleIcon /> Continue with Google
          </button>
        </div>
        <button type="button" className="auth-prompt-dismiss" onClick={onContinue} style={{ marginTop: '12px' }}>
          Continue Browsing
        </button>
      </div>
    </div>
  );
};

export default AuthPrompt;
