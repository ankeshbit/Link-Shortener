import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import ShortenerForm from './components/ShortenerForm';
import AnalyticsDashboard from './components/AnalyticsDashboard';


function App() {
  return (
    <BrowserRouter>
      <div className="container">
        <nav className="navbar">
          <Link to="/" className="nav-brand">
            <img src="/logo-nav.png" alt="ByteLink Logo" style={{ width: '52px', height: '52px', objectFit: 'cover', borderRadius: '12px', boxShadow: '0 4px 12px rgba(85, 193, 191, 0.15)' }} />
            <span>ByteLink</span>
          </Link>
        </nav>

        <Routes>
          <Route path="/" element={<ShortenerForm />} />
          <Route path="/stats/:id" element={<AnalyticsDashboard />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
