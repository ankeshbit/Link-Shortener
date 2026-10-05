import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '50vh',
        gap: '16px',
        animation: 'fadeIn 0.3s ease-out'
      }}>
        <span className="spinner" style={{ width: '32px', height: '32px', borderWidth: '3px' }}></span>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Restoring secure session...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children;
};

export default ProtectedRoute;
