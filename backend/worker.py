import json
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models
from database import SessionLocal

load_dotenv()

try:
    import redis
except ImportError:
    redis = None

STREAM_NAME = os.getenv("CLICK_STREAM_NAME", "stream:clicks")
GROUP_NAME = os.getenv("CLICK_STREAM_GROUP", "clicks_group")
DEAD_LETTER_STREAM = os.getenv("CLICK_DEAD_LETTER_STREAM", "stream:clicks:dead")
CONSUMER_NAME = os.getenv(
    "WORKER_CONSUMER_NAME", f"worker-{socket.gethostname()}-{os.getpid()}"
)
BATCH_SIZE = int(os.getenv("WORKER_BATCH_SIZE", "50"))
BLOCK_MS = int(os.getenv("WORKER_BLOCK_MS", "2000"))
MAX_RETRIES = int(os.getenv("WORKER_MAX_RETRIES", "3"))
STALE_IDLE_MS = int(os.getenv("WORKER_STALE_IDLE_MS", "30000"))

running = True


def handle_signal(sig, frame):
    global running
    logger.info(f"Signal {sig} received. Commencing graceful worker shutdown...")
    running = False


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def get_redis_client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    if redis is None:
        raise RuntimeError("Redis package is not installed.")
    return redis.from_url(
        redis_url,
        decode_responses=True,
        protocol=2,
        socket_connect_timeout=2.0,
        socket_timeout=5.0,
    )


def ensure_consumer_group(r: redis.Redis):
    """Creates consumer group and stream if they do not exist."""
    try:
        r.xgroup_create(STREAM_NAME, GROUP_NAME, id="$", mkstream=True)
        logger.info(f"Created consumer group '{GROUP_NAME}' on stream '{STREAM_NAME}'.")
    except Exception as e:
        if "BUSYGROUP" in str(e):
            pass
        else:
            logger.warning(f"Consumer group init note: {e}")


def parse_user_agent(ua_str: str) -> tuple[str, str, str]:
    """Lightweight user agent parsing returning (browser, os, device)."""
    if not ua_str:
        return "Unknown", "Unknown", "Unknown"
    ua = ua_str.lower()

    # Browser
    browser = "Other"
    if "chrome" in ua and "edg" not in ua and "opr" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "edg" in ua:
        browser = "Edge"
    elif "k6" in ua:
        browser = "k6"

    # Operating System
    operating_system = "Other"
    if "windows" in ua:
        operating_system = "Windows"
    elif "mac" in ua or "darwin" in ua:
        operating_system = "macOS"
    elif "linux" in ua:
        operating_system = "Linux"
    elif "android" in ua:
        operating_system = "Android"
    elif "iphone" in ua or "ipad" in ua:
        operating_system = "iOS"

    # Device
    device = "Desktop"
    if "mobile" in ua or "iphone" in ua or "android" in ua:
        device = "Mobile"
    elif "tablet" in ua or "ipad" in ua:
        device = "Tablet"
    elif "k6" in ua:
        device = "LoadTester"

    return browser, operating_system, device


def lookup_geoip(ip: str) -> tuple[str | None, str | None, float | None, float | None]:
    if not ip or ip in {"127.0.0.1", "localhost", "::1"}:
        return None, None, None, None
    try:
        with httpx.Client(timeout=2.0) as client:
            res = client.get(f"http://ip-api.com/json/{ip}").json()
        if res.get("status") == "success":
            return (
                res.get("country"),
                res.get("city"),
                res.get("lat"),
                res.get("lon"),
            )
    except Exception as e:
        logger.warning(f"GeoIP lookup failed for IP {ip}: {e}")
    return None, None, None, None


def is_duplicate(r: redis.Redis, event_id: str) -> bool:
    """Atomically sets event_id with 24h TTL. Returns True if event was already processed."""
    key = f"processed:click:{event_id}"
    res = r.set(key, "1", ex=86400, nx=True)
    return res is None


def check_and_handle_dead_letter(
    r: redis.Redis, event_id: str, msg_id: str, data: dict
) -> bool:
    """Caps retries and routes poison messages to dead-letter stream. Returns True if routed."""
    retry_key = f"retry:click:{event_id}"
    try:
        retries = r.incr(retry_key)
        r.expire(retry_key, 86400)
        if retries > MAX_RETRIES:
            logger.warning(
                f"Event {event_id} exceeded max retries ({retries}). Moving to {DEAD_LETTER_STREAM}."
            )
            dead_data = {
                **data,
                "dead_letter_reason": "exceeded_max_retries",
                "retries": str(retries),
                "moved_at": datetime.now(timezone.utc).isoformat(),
            }
            r.xadd(DEAD_LETTER_STREAM, dead_data)
            r.xack(STREAM_NAME, GROUP_NAME, msg_id)
            return True
    except Exception as e:
        logger.error(f"Error checking dead letter threshold for {event_id}: {e}")
    return False


def reclaim_pending_messages(
    r: redis.Redis,
    stream: str,
    group: str,
    consumer: str,
    min_idle_ms: int,
    count: int = 20,
) -> list[tuple[str, dict]]:
    """
    Reclaims stale messages from dead consumers.
    Uses XAUTOCLAIM if available (Redis >= 6.2) or falls back to XPENDING + XCLAIM (Redis 5.x).
    """
    try:
        # Try XAUTOCLAIM first
        res = r.xautoclaim(
            stream, group, consumer, min_idle_time=min_idle_ms, count=count
        )
        if isinstance(res, (list, tuple)) and len(res) > 1:
            return res[1]
        return []
    except Exception as e:
        err_msg = str(e).lower()
        if "unknown command" in err_msg or "xautoclaim" in err_msg:
            # Fallback for Redis 5.x
            try:
                pending_entries = r.xpending_range(
                    stream, group, min="-", max="+", count=count
                )
                stale_ids = [
                    p["message_id"]
                    for p in pending_entries
                    if p.get("time_since_delivered", p.get("idle_time", 0))
                    >= min_idle_ms
                ]
                if stale_ids:
                    return r.xclaim(
                        stream,
                        group,
                        consumer,
                        min_idle_time=min_idle_ms,
                        message_ids=stale_ids,
                    )
            except Exception as claim_err:
                logger.warning(f"XCLAIM fallback error: {claim_err}")
            return []
        logger.warning(f"Pending reclaim error: {e}")
        return []


def compile_stats_for_broadcast(url: models.URL, db: Session) -> dict:
    clicks = (
        db.query(models.ClickEvent)
        .filter(models.ClickEvent.url_id == url.id)
        .order_by(models.ClickEvent.clicked_at.desc())
        .limit(10)
        .all()
    )

    countries: dict[str, int] = {}
    country_counts = (
        db.query(models.ClickEvent.country, text("count(*)"))
        .filter(models.ClickEvent.url_id == url.id)
        .group_by(models.ClickEvent.country)
        .all()
    )
    for c_name, count in country_counts:
        if c_name:
            countries[c_name] = count

    recent_clicks = [
        {
            "time": c.clicked_at.isoformat() if c.clicked_at else None,
            "country": c.country,
            "city": c.city,
            "ip": c.ip_address,
            "user_agent": c.user_agent,
        }
        for c in clicks
    ]

    return {
        "short_id": url.short_id,
        "target_url": url.target_url,
        "total_clicks": url.clicks_count,
        "countries": countries,
        "recent_clicks": recent_clicks,
    }


def process_messages_batch(
    r: redis.Redis,
    messages: list[tuple[str, dict]],
    db: Session,
    stream_name: str = STREAM_NAME,
    group_name: str = GROUP_NAME,
) -> int:
    """
    Processes a list of stream messages:
    - deduplicates by event_id
    - resolves GeoIP and user agent
    - batch inserts ClickEvent records
    - atomically increments clicks_count
    - publishes real-time WebSocket update via Redis Pub/Sub
    - XACKs successfully committed messages
    Returns number of newly processed click events.
    """
    if not messages:
        return 0

    ack_ids = []
    events_to_insert = []
    increments_by_short_id: dict[str, int] = {}
    short_ids_to_notify = set()

    for msg_id, data in messages:
        event_id = data.get("event_id")
        short_id = data.get("short_id")
        ip = data.get("ip")
        ua_str = data.get("user_agent", "")
        incr_clicks = data.get("increment_clicks", "1") == "1"

        if not event_id or not short_id:
            ack_ids.append(msg_id)
            continue

        # Check dead-letter retry limit
        if check_and_handle_dead_letter(r, event_id, msg_id, data):
            continue

        # Deduplicate on retry
        if is_duplicate(r, event_id):
            logger.info(f"Duplicate click event ignored: {event_id}")
            ack_ids.append(msg_id)
            continue

        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url:
            logger.warning(f"URL not found for stream event {short_id}.")
            ack_ids.append(msg_id)
            continue

        browser, os_name, device = parse_user_agent(ua_str)
        country, city, lat, lon = lookup_geoip(ip)

        click_event = models.ClickEvent(
            url_id=url.id,
            ip_address=ip,
            country=country,
            city=city,
            lat=lat,
            lon=lon,
            user_agent=ua_str,
            browser=browser,
            os=os_name,
            device=device,
        )
        events_to_insert.append(click_event)
        ack_ids.append(msg_id)
        short_ids_to_notify.add(short_id)

        if incr_clicks:
            increments_by_short_id[short_id] = (
                increments_by_short_id.get(short_id, 0) + 1
            )

    if events_to_insert:
        db.add_all(events_to_insert)

    for s_id, inc in increments_by_short_id.items():
        db.execute(
            text(
                "UPDATE urls SET clicks_count = clicks_count + :inc WHERE short_id = :short_id"
            ),
            {"inc": inc, "short_id": s_id},
        )

    db.commit()

    # XACK all processed messages
    if ack_ids:
        r.xack(stream_name, group_name, *ack_ids)

    # Publish WebSocket notifications
    for s_id in short_ids_to_notify:
        url_obj = db.query(models.URL).filter(models.URL.short_id == s_id).first()
        if url_obj:
            stats = compile_stats_for_broadcast(url_obj, db)
            try:
                r.publish(
                    "channel:ws:clicks",
                    json.dumps({"short_id": s_id, "stats": stats}),
                )
            except Exception as pub_err:
                logger.warning(f"Failed to publish WebSocket stats update: {pub_err}")

    return len(events_to_insert)


def run_worker_loop():
    logger.info(
        f"Starting ByteLink Analytics Worker [{CONSUMER_NAME}] on group '{GROUP_NAME}'..."
    )
    r = get_redis_client()
    ensure_consumer_group(r)

    with SessionLocal() as db:
        while running:
            try:
                # 1. Periodically reclaim stale pending messages
                stale_messages = reclaim_pending_messages(
                    r,
                    STREAM_NAME,
                    GROUP_NAME,
                    CONSUMER_NAME,
                    STALE_IDLE_MS,
                    count=BATCH_SIZE,
                )
                if stale_messages:
                    logger.info(
                        f"Reclaimed {len(stale_messages)} stale pending messages from dead consumers."
                    )
                    process_messages_batch(r, stale_messages, db)

                # 2. Read new messages
                response = r.xreadgroup(
                    GROUP_NAME,
                    CONSUMER_NAME,
                    {STREAM_NAME: ">"},
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )

                if response:
                    for stream, messages in response:
                        if messages:
                            count = process_messages_batch(r, messages, db)
                            if count > 0:
                                logger.info(
                                    f"Processed batch of {count} clicks from {stream}."
                                )
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(1.0)

    logger.info(f"Worker [{CONSUMER_NAME}] shutdown complete.")


if __name__ == "__main__":
    run_worker_loop()
