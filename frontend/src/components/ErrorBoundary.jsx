import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          backgroundColor: '#0f172a',
          color: '#f1f5f9',
          fontFamily: 'system-ui, sans-serif',
          textAlign: 'center',
          padding: '2rem',
          boxSizing: 'border-box'
        }}>
          <h1 style={{ color: '#ef4444', marginBottom: '1rem', fontSize: '2.5rem' }}>Something went wrong</h1>
          <p style={{ color: '#94a3b8', marginBottom: '2.5rem', fontSize: '1.1rem', maxWidth: '500px', lineHeight: '1.6' }}>
            We've encountered an unexpected frontend error. Please try refreshing the page or contact support if the issue persists.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '0.75rem 1.5rem',
              borderRadius: '0.5rem',
              border: 'none',
              background: '#3ECF8E',
              color: '#070B14',
              fontWeight: 'bold',
              cursor: 'pointer',
              fontSize: '1rem',
              transition: '0.2s'
            }}
            onMouseOver={(e) => e.target.style.background = '#34be7f'}
            onMouseOut={(e) => e.target.style.background = '#3ECF8E'}
          >
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
