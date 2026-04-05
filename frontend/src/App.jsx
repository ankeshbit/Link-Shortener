import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import ShortenerForm from './components/ShortenerForm';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import { Layers } from 'lucide-react';

function App() {
  return (
    <BrowserRouter>
      <div className="container">
        <nav className="navbar">
          <Link to="/" className="nav-brand">
            <Layers color="#6366f1" size={32} />
            <span>ByteLink</span>
          </Link>
          <div className="nav-links">
            <Link to="/">Shorten</Link>
          </div>
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
