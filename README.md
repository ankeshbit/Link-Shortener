# ByteLink: Scalable URL Shortener + Analytics Dashboard 🚀

A highly scalable URL shortening service with real-time analytics, geo-location tracking, rate limiting, and premium dynamic aesthetics. This project features a robust Python/FastAPI backend and an ultra-modern React + Vite frontend.

## 🌟 Features

- **Blazing Fast Short Links**: Transform long URLs into concise, readable short links via Base62 encoding.
- **Geo-Location Analytics**: Automatically tracks click data, timestamps, and geographic locations (City/Country) of link visitors without impacting redirect response times (using asynchronous processing).
- **Rate Limiting & Caching**: Smartly limits API abuse to prevent spam requests. Incorporates an automatic "Mock Redis" system so that caching works locally out-of-the-box (with plug-and-play support for a real Redis server).
- **Premium Aesthetics**: Built entirely with Vanilla CSS using dark-mode glassmorphism and subtle structural micro-animations. No boring boilerplates!
- **Interactive Dashboards**: Real-time graphs powered by `Chart.js` tracking click distributions across different countries.
- **Advanced Link Controls**: Features include Custom Vanity URLs, scheduled Link Expiration, and Password-Protection.
- **QR Code Integration**: Automatically generates downloadable QR codes for your shortened links on the fly.

## 🛠 Tech Stack

**Frontend:**
- React 18 + Vite
- React Router DOM (Navigation)
- Chart.js & react-chartjs-2 (Analytics visualizations)
- Lucide React (Icons)
- Custom Vanilla CSS (Glassmorphism & animations)

**Backend:**
- Python 3 + FastAPI
- SQLAlchemy + SQLite3 (Database storage)
- Redis Client (Caching & Rate Limiting)
- Shortuuid (Base62 Generation)
- External IP tracking API (`ip-api.com`)

---

## 🚀 Running the Project Locally

To run this application, you will need to open **two separate terminal windows**—one for the backend and one for the frontend.

### 1. Start the Backend API
Navigate to the `backend` directory from the root project folder:

```bash
cd backend

# Create and activate virtual environment (Windows)
python -m venv venv
.\venv\Scripts\activate

# Install the required Python packages
pip install -r requirements.txt

# Run the FastAPI server
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
*Note: If you do not have Redis installed locally, the backend will automatically fallback gracefully to a mock in-memory version.*

### 2. Start the Frontend App
Open a fresh terminal, navigate to the `frontend` folder, and boot the web application:

```bash
cd frontend

# Install Node dependencies
npm install

# Start the Vite development server
npm run dev
```

### 3. Open the App
Hold `Ctrl` and click the local network link generated in your frontend terminal (usually `http://localhost:5173/` or `5174`). Follow the UI to start shortening links and analyzing the data!