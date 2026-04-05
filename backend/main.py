import shortuuid
import requests
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models
from redis_client import redis_cache

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

from pydantic import BaseModel, HttpUrl

class URLCreate(BaseModel):
    target_url: str

@app.post("/api/shorten", dependencies=[Depends(rate_limit)])
def create_short_url(item: URLCreate, request: Request, db: Session = Depends(get_db)):
    short_id = shortuuid.ShortUUID().random(length=7)
    
    new_url = models.URL(short_id=short_id, target_url=item.target_url)
    db.add(new_url)
    db.commit()
    db.refresh(new_url)

    redis_cache.set(f"url:{short_id}", item.target_url)

    return {
        "short_id": short_id,
        "target_url": item.target_url,
        "short_url": f"http://localhost:8000/{short_id}"
    }

@app.get("/{short_id}")
def redirect_url(short_id: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    target_url = redis_cache.get(f"url:{short_id}")
    
    if not target_url:
        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url:
            raise HTTPException(status_code=404, detail="URL not found")
        target_url = url.target_url
        redis_cache.set(f"url:{short_id}", target_url)

    user_agent = request.headers.get("user-agent", "Unknown")
    ip = request.client.host
    background_tasks.add_task(track_click, short_id, db, user_agent, ip)

    return RedirectResponse(url=target_url)

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
