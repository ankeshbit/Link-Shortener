import shortuuid
import requests
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models
from redis_client import redis_cache

# Removed drop_all to prevent data wipe on restart
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Scalable URL Shortener API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def rate_limit(request: Request):
    client_ip = request.client.host
    key = f"rate_limit:{client_ip}"
    current = redis_cache.incr(key)
    if current == 1:
        redis_cache.expire(key, 60)
    if current > 20: 
        raise HTTPException(status_code=429, detail="Too many requests")
    return True

def track_click(short_id: str, db: Session, user_agent: str, ip: str):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url: return

    url.clicks_count += 1
    
    country, city, lat, lon = None, None, None, None
    if ip and ip != "127.0.0.1":
        try:
            res = requests.get(f"http://ip-api.com/json/{ip}", timeout=2).json()
            if res.get("status") == "success":
                country = res.get("country")
                city = res.get("city")
                lat = res.get("lat")
                lon = res.get("lon")
        except:
            pass

    click = models.ClickEvent(
        url_id=url.id,
        ip_address=ip,
        country=country,
        city=city,
        lat=lat,
        lon=lon,
        user_agent=user_agent
    )
    db.add(click)
    db.commit()

from pydantic import BaseModel

class URLCreate(BaseModel):
    target_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None
    password: Optional[str] = None

@app.post("/api/shorten", dependencies=[Depends(rate_limit)])
def create_short_url(item: URLCreate, request: Request, db: Session = Depends(get_db)):
    if item.custom_alias:
        existing = db.query(models.URL).filter(models.URL.short_id == item.custom_alias).first()
        if existing:
            raise HTTPException(status_code=400, detail="Use any other name")
        short_id = item.custom_alias
    else:
        short_id = shortuuid.ShortUUID().random(length=7)
    
    new_url = models.URL(
        short_id=short_id, 
        target_url=item.target_url,
        expires_at=item.expires_at,
        password=item.password
    )
    db.add(new_url)
    db.commit()
    db.refresh(new_url)

    cache_data = {
        "target_url": item.target_url,
        "password": bool(item.password),
        "expires_at": item.expires_at.isoformat() if item.expires_at else None
    }
    redis_cache.set(f"url:{short_id}", json.dumps(cache_data))

    return {
        "short_id": short_id,
        "target_url": item.target_url,
        "short_url": f"http://localhost:8000/{short_id}"
    }

def get_html_template(title, body_content):
    return f"""
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{ background-color: #0f172a; color: #f1f5f9; font-family: system-ui, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
            .card {{ background: rgba(255, 255, 255, 0.05); padding: 2.5rem; border-radius: 1rem; backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); text-align: center; max-width: 400px; width: 100%; box-sizing: border-box; }}
            input {{ width: 100%; padding: 0.75rem; margin-top: 1rem; border-radius: 0.5rem; border: 1px solid rgba(255,255,255,0.2); background: rgba(0,0,0,0.2); color: white; box-sizing: border-box; outline: none; }}
            input:focus {{ border-color: #6366f1; }}
            button {{ width: 100%; padding: 0.75rem; margin-top: 1rem; border-radius: 0.5rem; border: none; background: #6366f1; color: white; font-weight: bold; cursor: pointer; transition: 0.2s; }}
            button:hover {{ background: #4f46e5; }}
            .error {{ color: #ef4444; margin-top: 1rem; font-size: 0.9rem; }}
        </style>
    </head>
    <body>
        <div class="card">
            {body_content}
        </div>
    </body>
    </html>
    """

@app.get("/{short_id}")
def redirect_url(short_id: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if short_id in ["api", "favicon.ico"]:
        raise HTTPException(status_code=404)
        
    cache_entry = redis_cache.get(f"url:{short_id}")
    
    password = False
    expires_at = None
    target_url = None
    
    if cache_entry:
        try:
            data = json.loads(cache_entry)
            target_url = data.get("target_url")
            password = data.get("password")
            expires_at = data.get("expires_at")
            if expires_at:
                expires_at = datetime.fromisoformat(expires_at)
        except json.JSONDecodeError:
            target_url = cache_entry
            
    if not cache_entry or not target_url:
        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url:
            raise HTTPException(status_code=404, detail="URL not found")
        target_url = url.target_url
        password = bool(url.password)
        expires_at = url.expires_at
        
        cache_data = {
            "target_url": target_url,
            "password": password,
            "expires_at": expires_at.isoformat() if expires_at else None
        }
        redis_cache.set(f"url:{short_id}", json.dumps(cache_data))

    if expires_at and datetime.utcnow() > expires_at.replace(tzinfo=None):
        return HTMLResponse(get_html_template("Link Expired", "<h2>Link Expired</h2><p>This short URL is no longer active.</p>"))

    if password:
        form = f'''
            <h2>Unlock Link</h2>
            <p style="color: #94a3b8; font-size: 0.9em; margin-bottom: 1.5rem;">This link is password protected.</p>
            <form method="post" action="/{short_id}">
                <input type="password" name="password" placeholder="Enter password" required />
                <button type="submit">Unlock</button>
            </form>
        '''
        return HTMLResponse(get_html_template("Password Required", form))

    user_agent = request.headers.get("user-agent", "Unknown")
    ip = request.client.host
    background_tasks.add_task(track_click, short_id, db, user_agent, ip)

    return RedirectResponse(url=target_url)

@app.post("/{short_id}")
def verify_password_and_redirect(short_id: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db), password: str = Form(...)):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")
        
    if url.expires_at and datetime.utcnow() > url.expires_at.replace(tzinfo=None):
        return HTMLResponse(get_html_template("Link Expired", "<h2>Link Expired</h2><p>This short URL is no longer active.</p>"))

    if url.password and url.password != password:
        form = f'''
            <h2>Unlock Link</h2>
            <p style="color: #94a3b8; font-size: 0.9em; margin-bottom: 1.5rem;">This link is password protected.</p>
            <form method="post" action="/{short_id}">
                <input type="password" name="password" placeholder="Enter password" required />
                <button type="submit">Unlock</button>
                <div class="error">Incorrect password. Please try again.</div>
            </form>
        '''
        return HTMLResponse(get_html_template("Password Required", form))

    user_agent = request.headers.get("user-agent", "Unknown")
    ip = request.client.host
    background_tasks.add_task(track_click, short_id, db, user_agent, ip)

    return RedirectResponse(url=url.target_url, status_code=303)

@app.get("/api/stats/{short_id}")
def get_stats(short_id: str, db: Session = Depends(get_db)):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")
    
    clicks = db.query(models.ClickEvent).filter(models.ClickEvent.url_id == url.id).all()
    
    countries = {}
    last_clicks = []
    for c in clicks:
        if c.country:
            countries[c.country] = countries.get(c.country, 0) + 1
            
    for c in clicks[-20:]:
        last_clicks.append({
            "time": c.clicked_at.isoformat() if c.clicked_at else None,
            "country": c.country,
            "city": c.city,
            "ip": c.ip_address,
            "user_agent": c.user_agent
        })
            
    return {
        "short_id": url.short_id,
        "target_url": url.target_url,
        "total_clicks": url.clicks_count,
        "countries": countries,
        "recent_clicks": last_clicks
    }
