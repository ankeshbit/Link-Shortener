import { LogIn, UserPlus } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

const AuthPrompt = ({ onContinue, onAuthenticate }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const from = `${location.pathname}${location.search}${location.hash}`;

  return (
    <div className="auth-prompt" role="dialog" aria-labelledby="auth-prompt-title">
      <div className="auth-prompt-card">
        <h2 id="auth-prompt-title">Login required</h2>
        <p>Create an account or log in to use this feature and manage your links.</p>
        <div className="auth-prompt-actions">
          <button type="button" className="btn-login-primary" onClick={() => {
            onAuthenticate?.();
            navigate('/login', { state: { from } });
          }}>
            <LogIn size={16} /> Log In
          </button>
          <button type="button" className="btn-action primary-action" onClick={() => {
            onAuthenticate?.();
            navigate('/login?mode=signup', { state: { from } });
          }}>
            <UserPlus size={16} /> Create Account
          </button>
        </div>
        <button type="button" className="auth-prompt-dismiss" onClick={onContinue}>
          Continue Browsing
        </button>
      </div>
    </div>
  );
};

export default AuthPrompt;
