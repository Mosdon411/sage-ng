# sage_server.py - Complete SAGE-NG Server for Windows with Real-Time WebSockets

from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import uvicorn
import random
import json
import asyncio
import os
import sys
import math
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import uuid4

# Ensure backend package is importable
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

try:
    from backend.connectors.api_connectors import TwitterConnector, TelegramConnector
except Exception:
    TwitterConnector = None
    TelegramConnector = None

# Threat data
THREAT_KEYWORDS = [
    "bandit", "kidnap", "terrorist", "boko haram", "zamfara",
    "katsina", "borno", "attack", "ransom", "armed", "shooting"
]

REGIONS = ["North East", "North West", "North Central", "South West", "South East", "South South"]

# Database
class Database:
    def __init__(self):
        self.threats = []
    
    def add(self, threat):
        threat['id'] = len(self.threats) + 1
        threat['timestamp'] = datetime.now().isoformat()
        self.threats.append(threat)
        return threat
    
    def get_recent(self, limit=50):
        return self.threats[-limit:]
    
    def get_summary(self):
        critical = len([t for t in self.threats if t.get('severity') == 'critical'])
        high = len([t for t in self.threats if t.get('severity') == 'high'])
        return {
            'total': len(self.threats),
            'critical': critical,
            'high': high,
            'instability_index': min(100, critical * 10 + high * 5)
        }

db = Database()

social_media_feed = []
registered_devices = {}
field_alerts = []

SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4
}

SOCIAL_MEDIA_SAMPLES = [
    {
        "platform": "TikTok",
        "text": "Drone footage shows possible bandit movement near Zamfara highway.",
        "location": "Zamfara",
        "severity": "critical"
    },
    {
        "platform": "Twitter",
        "text": "Confirmed report: suspicious convoy seen close to Kaduna-Kano road.",
        "location": "Kaduna",
        "severity": "high"
    },
    {
        "platform": "Telegram",
        "text": "Alert: multiple armed men spotted around Makurdi bridge.",
        "location": "Benue",
        "severity": "high"
    },
    {
        "platform": "Facebook",
        "text": "Community post: checkpoint attack near Maiduguri, urgent response needed.",
        "location": "Borno",
        "severity": "critical"
    },
    {
        "platform": "X",
        "text": "Local source reports kidnappers moving through Katsina forest.",
        "location": "Katsina",
        "severity": "high"
    }
]

drone_telemetry = {}

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WS] WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


class MobileConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id] = websocket
        if device_id in registered_devices:
            registered_devices[device_id]["status"] = "online"
            registered_devices[device_id]["last_seen"] = datetime.now().isoformat()
        print(f"[MOBILE] Device connected: {device_id}. Total mobile clients: {len(self.active_connections)}")

    def disconnect(self, device_id: str):
        self.active_connections.pop(device_id, None)
        if device_id in registered_devices:
            registered_devices[device_id]["status"] = "offline"
            registered_devices[device_id]["last_seen"] = datetime.now().isoformat()
        print(f"[MOBILE] Device disconnected: {device_id}. Total mobile clients: {len(self.active_connections)}")

    async def send_to_device(self, device_id: str, message: dict):
        connection = self.active_connections.get(device_id)
        if not connection:
            return
        try:
            await connection.send_json(message)
        except Exception:
            self.disconnect(device_id)

    async def broadcast_alert(self, alert: dict):
        for device_id, device in list(registered_devices.items()):
            if should_deliver_alert(device, alert):
                await self.send_to_device(device_id, {
                    "type": "mobile_alert",
                    "alert": alert
                })


mobile_manager = MobileConnectionManager()

# Create app
app = FastAPI(title="SAGE-NG")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Optional social media connectors
twitter_connector = TwitterConnector() if TwitterConnector else None
telegram_connector = TelegramConnector() if TelegramConnector else None

@app.on_event("startup")
async def start_services():
    if not social_media_feed:
        for sample in SOCIAL_MEDIA_SAMPLES[:3]:
            add_social_post(sample["platform"], sample["text"], location=sample.get("location"), severity=sample.get("severity", "high"))

    if connectors_available():
        asyncio.create_task(poll_social_media_feed())
    else:
        asyncio.create_task(simulate_social_media_feed())
    
    # Start high-frequency real-time WebSocket simulator
    asyncio.create_task(continuous_websocket_simulation())


def connectors_available():
    return (
        (twitter_connector is not None and getattr(twitter_connector, 'bearer_token', None)) or
        (telegram_connector is not None and getattr(telegram_connector, 'api_id', None) and getattr(telegram_connector, 'api_hash', None))
    )


def generate_source_url(platform, platform_id, text):
    """Generate a verifiable source URL for social media posts"""
    platform_lower = platform.lower()
    
    if platform_lower == "twitter" or platform_lower == "x":
        if platform_id:
            return f"https://twitter.com/i/web/status/{platform_id}"
        return f"https://twitter.com/search?q={text[:30].replace(' ', '%20')}"
    
    elif platform_lower == "facebook":
        if platform_id:
            return f"https://www.facebook.com/{platform_id}"
        return f"https://www.facebook.com/search/?q={text[:30].replace(' ', '%20')}"
    
    elif platform_lower == "telegram":
        if platform_id:
            return f"https://t.me/s/{platform_id}"
        return "https://telegram.org"
    
    elif platform_lower == "tiktok":
        if platform_id:
            return f"https://www.tiktok.com/@security/video/{platform_id}"
        return f"https://www.tiktok.com/search?q={text[:30].replace(' ', '%20')}"
    
    elif platform_lower == "instagram":
        if platform_id:
            return f"https://www.instagram.com/p/{platform_id}"
        return "https://www.instagram.com"
    
    else:
        return f"https://search.google.com/search?q={text[:30].replace(' ', '%20')}"

def social_post_exists(platform, platform_id):
    return any(
        p.get("platform") == platform and p.get("platform_id") == platform_id
        for p in social_media_feed
    )


def add_social_post(platform, text, location=None, severity="high", platform_id=None):
    if platform_id and social_post_exists(platform, platform_id):
        return None

    # Generate source URL based on platform
    source_url = generate_source_url(platform, platform_id, text)

    post = {
        "id": len(social_media_feed) + 1,
        "platform": platform,
        "platform_id": platform_id,
        "text": text,
        "location": location or "Unknown",
        "severity": severity,
        "timestamp": datetime.now().isoformat(),
        "source": platform.lower(),
        "source_url": source_url
    }
    social_media_feed.append(post)
    if len(social_media_feed) > 100:
        social_media_feed.pop(0)

    if any(kw in text.lower() for kw in THREAT_KEYWORDS):
        threat_type, confidence, threat_severity = analyze_threat(text)
        region = random.choice(REGIONS)
        db.add({
            "text": text,
            "threat_type": threat_type,
            "confidence": confidence,
            "severity": threat_severity,
            "region": region,
            "source": platform.lower()
        })

    return post


async def fetch_twitter_posts():
    if not twitter_connector or not getattr(twitter_connector, 'bearer_token', None):
        return

    tweets = await twitter_connector.fetch_tweets()
    for tweet in tweets:
        text = tweet.get("text", "")
        if not text.strip():
            continue
        post = add_social_post(
            "X",
            text,
            location=tweet.get("geo", {}).get("place_id") if isinstance(tweet.get("geo"), dict) else "Unknown",
            severity="high",
            platform_id=tweet.get("id")
        )
        if post and tweet.get("id"):
            post["source_url"] = f"https://twitter.com/i/web/status/{tweet.get('id')}"


async def fetch_telegram_posts():
    if not telegram_connector or not getattr(telegram_connector, 'api_id', None) or not getattr(telegram_connector, 'api_hash', None):
        return

    channels = [c.strip() for c in os.getenv("TELEGRAM_CHANNELS", "#security,#nigeria").split(",") if c.strip()]
    if not channels:
        return

    messages = await telegram_connector.fetch_messages(channels)
    for msg in messages:
        if not msg.get("text"):
            continue
        post = add_social_post(
            "Telegram",
            msg["text"],
            location=msg.get("channel", "Telegram"),
            severity="high",
            platform_id=f"{msg.get('channel')}_{msg.get('date')}"
        )
        if post and msg.get("channel"):
            post["source_url"] = f"https://t.me/s/{msg.get('channel')}"


async def poll_social_media_feed():
    while True:
        try:
            await fetch_twitter_posts()
            await fetch_telegram_posts()
        except Exception:
            pass
        await asyncio.sleep(30)


async def simulate_social_media_feed():
    while True:
        await asyncio.sleep(12)
        sample = random.choice(SOCIAL_MEDIA_SAMPLES)
        add_social_post(
            sample["platform"],
            sample["text"],
            location=sample.get("location"),
            severity=sample.get("severity", "high"),
            platform_id=None
        )

def analyze_threat(text):
    threat_words = ["bandit", "attack", "kidnap", "terrorist", "boko", "haram"]
    matches = sum(1 for w in threat_words if w in text.lower())
    if matches >= 2:
        severity = "critical"
        threat_type = "threat detected"
    elif matches >= 1:
        severity = "high"
        threat_type = "suspicious activity"
    else:
        severity = "low"
        threat_type = "normal"
    confidence = matches / len(threat_words) if matches > 0 else 0.1
    return threat_type, confidence, severity


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate approximate distance between two coordinates."""
    radius_km = 6371
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def should_deliver_alert(device, alert):
    min_severity = device.get("min_severity", "medium")
    alert_severity = alert.get("severity", "medium")
    if SEVERITY_RANK.get(alert_severity, 0) < SEVERITY_RANK.get(min_severity, 2):
        return False

    device_sectors = set(device.get("sectors") or ["all"])
    alert_sector = alert.get("sector", "intelligence")
    if "all" not in device_sectors and alert_sector not in device_sectors:
        return False

    if alert_severity == "critical":
        return True

    device_lat = device.get("latitude")
    device_lon = device.get("longitude")
    alert_lat = alert.get("latitude")
    alert_lon = alert.get("longitude")
    if None in [device_lat, device_lon, alert_lat, alert_lon]:
        return True

    distance = haversine_km(device_lat, device_lon, alert_lat, alert_lon)
    return distance <= float(device.get("radius_km", 50))


def register_or_update_device(data):
    device_id = data.get("device_id") or f"SAGE-MOB-{uuid4().hex[:8].upper()}"
    existing = registered_devices.get(device_id, {})
    sectors = data.get("sectors", existing.get("sectors", ["all"]))
    if isinstance(sectors, str):
        sectors = [s.strip() for s in sectors.split(",") if s.strip()]

    device = {
        **existing,
        "device_id": device_id,
        "label": data.get("label", existing.get("label", "Field Device")),
        "role": data.get("role", existing.get("role", "public")),
        "phone": data.get("phone", existing.get("phone")),
        "push_token": data.get("push_token", existing.get("push_token")),
        "latitude": data.get("latitude", existing.get("latitude")),
        "longitude": data.get("longitude", existing.get("longitude")),
        "radius_km": float(data.get("radius_km", existing.get("radius_km", 50))),
        "sectors": sectors or ["all"],
        "min_severity": data.get("min_severity", existing.get("min_severity", "medium")),
        "status": existing.get("status", "registered"),
        "created_at": existing.get("created_at", datetime.now().isoformat()),
        "last_seen": datetime.now().isoformat()
    }
    registered_devices[device_id] = device
    return device


def create_field_alert(sector, title, description, severity, lat=None, lon=None, source="system", threat_id=None, confidence=0.9, verification_status="unverified", audience=None, recommended_action=None):
    alert = {
        "alert_id": f"ALERT-{uuid4().hex[:10].upper()}",
        "threat_id": threat_id,
        "sector": sector,
        "title": title,
        "description": description,
        "severity": severity,
        "confidence": confidence,
        "verification_status": verification_status,
        "audience": audience or ["command", "field"],
        "recommended_action": recommended_action or default_recommended_action(sector, severity),
        "latitude": lat,
        "longitude": lon,
        "region": determine_region_from_coords(float(lat), float(lon)) if lat is not None and lon is not None else "Nigeria",
        "source": source,
        "timestamp": datetime.now().isoformat()
    }
    field_alerts.append(alert)
    if len(field_alerts) > 500:
        field_alerts.pop(0)
    return alert


def default_recommended_action(sector, severity):
    if severity == "critical":
        return "Escalate immediately, verify source, notify nearby responders, and keep civilians away from the affected area."
    if sector == "traffic":
        return "Flag plate record, notify enforcement desk, and preserve camera evidence."
    if sector == "agriculture":
        return "Notify local extension team and monitor affected farm coordinates."
    if sector == "mining":
        return "Dispatch site security and verify machinery or perimeter breach."
    return "Monitor closely, verify with a second source, and prepare response assets."


def incident_to_alert(sector, incident):
    title = (incident.get("threat_type") or "INCIDENT_ALERT").replace("_", " ").title()
    return create_field_alert(
        sector=sector,
        title=title,
        description=incident.get("text", "Incident reported"),
        severity=incident.get("severity", "high"),
        lat=incident.get("latitude"),
        lon=incident.get("longitude"),
        source=incident.get("source", "sensor"),
        threat_id=incident.get("id"),
        confidence=float(incident.get("confidence", 0.8)),
        verification_status="verified" if incident.get("source") in ["drone", "traffic_camera", "uav_recon"] else "pending_review"
    )


async def publish_incident(sector, incident):
    alert = incident_to_alert(sector, incident)
    await manager.broadcast({
        "type": "incident",
        "sector": sector,
        "incident": incident,
        "field_alert": alert
    })
    await mobile_manager.broadcast_alert(alert)
    return alert

# ==================== WEB SYSTEM SIMULATORS (REAL-TIME) ====================

# Simulated UAV flight loops around conflict hotspots in Nigeria
DRONE_PATHS = {
    "SAGE_DRONE_001": {"lat": 10.5105, "lon": 7.4165, "radius": 0.05, "angle": 0.0, "battery": 98, "name": "Patrol Alpha (Kaduna)"},
    "SAGE_DRONE_002": {"lat": 11.8311, "lon": 13.1510, "radius": 0.04, "angle": 1.5, "battery": 94, "name": "Strike Eagle (Borno)"},
    "SAGE_DRONE_003": {"lat": 12.1550, "lon": 6.6530, "radius": 0.03, "angle": 3.0, "battery": 88, "name": "Recon Vanguard (Zamfara)"}
}

# Simulated Heavy Mining Machinery (Resource Guard Sector)
MINING_TELEMETRY = [
    {"id": "EXCAVATOR_01", "lat": 12.1580, "lon": 6.6550, "type": "Excavator", "status": "active", "load": "82%", "fuel": "64%"},
    {"id": "HAUL_TRUCK_08", "lat": 12.1640, "lon": 6.6620, "type": "Hauler", "status": "idle", "load": "0%", "fuel": "89%"},
    {"id": "DRILL_RIG_02", "lat": 12.1460, "lon": 6.6470, "type": "Driller", "status": "active", "load": "95%", "fuel": "45%"}
]

# Speed cameras and location triggers (Traffic Surveillance)
ALPR_CAMERAS = [
    {"id": "CAM_ABJ_INTER", "lat": 9.0579, "lon": 7.4890, "location": "Abuja Outer Expressway", "limit": 100},
    {"id": "CAM_LAG_EXPR", "lat": 6.5244, "lon": 3.3792, "location": "Ikeja Outer Expressway", "limit": 100},
    {"id": "CAM_KAN_RING", "lat": 11.9964, "lon": 8.5167, "location": "Kano Ring Flyover", "limit": 80},
    {"id": "CAM_PHC_LINK", "lat": 4.8156, "lon": 7.0498, "location": "Port Harcourt Express", "limit": 90}
]

# Random license plate generator
def generate_plate():
    states = ["ABJ", "LAG", "KAN", "KAD", "ZMF", "BOR", "PHC"]
    prefix = random.choice(states)
    num = random.randint(100, 999)
    suffix = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=2))
    return f"{prefix}-{num}{suffix}"

async def continuous_websocket_simulation():
    tick = 0
    while True:
        try:
            tick += 1
            
            # 1. Update Drones (Security Sector)
            drones_list = []
            for drone_id, path in DRONE_PATHS.items():
                path["angle"] += 0.04
                lat = path["lat"] + path["radius"] * math.cos(path["angle"])
                lon = path["lon"] + path["radius"] * math.sin(path["angle"])
                
                # Slowly deplete battery
                if tick % 8 == 0:
                    path["battery"] = max(5, path["battery"] - 1)
                
                if path["battery"] <= 5:
                    path["battery"] = 100 # Simulated quick battery hot-swap / launch new drone
                
                drone_telemetry[drone_id] = {
                    "drone_id": drone_id,
                    "name": path["name"],
                    "status": "patrolling" if path["battery"] > 25 else "returning",
                    "battery": int(path["battery"]),
                    "altitude": int(120 + 30 * math.sin(path["angle"] * 2.5)),
                    "latitude": lat,
                    "longitude": lon,
                    "last_update": datetime.now().isoformat()
                }
                drones_list.append(drone_telemetry[drone_id])

            # 2. Update Mining Machinery Telemetry (Mining Sector)
            mining_list = []
            for gear in MINING_TELEMETRY:
                # Add minor movement jitter
                gear["lat"] += random.uniform(-0.0001, 0.0001)
                gear["lon"] += random.uniform(-0.0001, 0.0001)
                if tick % 6 == 0:
                    gear["status"] = random.choice(["active", "active", "idle"])
                mining_list.append(gear.copy())

            # 3. Simulate Traffic ALPR Scan logs (Traffic Surveillance Sector)
            traffic_scan = None
            if tick % 2 == 0: # Scan every 2 seconds
                cam = random.choice(ALPR_CAMERAS)
                plate = generate_plate()
                speed = random.randint(55, 160)
                is_offender = speed > cam["limit"]
                is_stolen = random.random() < 0.03 # 3% chance
                
                traffic_scan = {
                    "camera_id": cam["id"],
                    "location": cam["location"],
                    "latitude": cam["lat"] + random.uniform(-0.0005, 0.0005),
                    "longitude": cam["lon"] + random.uniform(-0.0005, 0.0005),
                    "plate": plate,
                    "speed": speed,
                    "limit": cam["limit"],
                    "is_offender": is_offender,
                    "is_stolen": is_stolen,
                    "timestamp": datetime.now().isoformat()
                }
                
                # If traffic violation/offence, add to active threats DB
                if is_offender or is_stolen:
                    threat_type = "TRAFFIC_VIOLATION"
                    severity = "high" if is_stolen else "medium"
                    desc = f"🚨 STOLEN VEHICLE DETECTED: License Plate {plate} scanned by {cam['id']} at {cam['location']}" if is_stolen else f"⚠️ SPEED VIOLATION: Plate {plate} clocked at {speed} km/h (Limit: {cam['limit']}) at {cam['location']}"
                    
                    threat = db.add({
                        "text": desc,
                        "threat_type": threat_type,
                        "confidence": 0.98,
                        "severity": severity,
                        "region": determine_region_from_coords(cam["lat"], cam["lon"]),
                        "source": "traffic_camera",
                        "latitude": cam["lat"],
                        "longitude": cam["lon"]
                    })
                    await publish_incident("traffic", threat)

            # 4. Simulate Agriculture Sensors (Agriculture Sector)
            agri_sensor = {
                "sensor_id": f"AGRI_NODE_0{random.randint(1, 4)}",
                "lat": 7.3364 + random.uniform(-0.15, 0.15),
                "lon": 8.9860 + random.uniform(-0.15, 0.15),
                "ndvi": round(random.uniform(0.58, 0.84), 2),
                "moisture": f"{random.randint(28, 62)}%",
                "temperature": round(random.uniform(27.5, 34.8), 1),
                "timestamp": datetime.now().isoformat()
            }

            # 5. Simulate Live Intelligence Feed updates
            intel_feed = None
            if tick % 8 == 0:
                sample = random.choice(SOCIAL_MEDIA_SAMPLES)
                intel_feed = {
                    "platform": sample["platform"],
                    "text": sample["text"],
                    "location": sample["location"],
                    "severity": sample["severity"],
                    "timestamp": datetime.now().isoformat()
                }

            # Broadcast general telemetry updates
            payload = {
                "type": "telemetry",
                "timestamp": datetime.now().isoformat(),
                "drones": drones_list,
                "mining": mining_list,
                "traffic": traffic_scan,
                "agri": agri_sensor,
                "intel": intel_feed,
                "summary": db.get_summary()
            }
            await manager.broadcast(payload)

            # 6. Periodic automated high-severity alert simulation (every 30 seconds)
            if tick % 30 == 0:
                alerts = [
                    {
                        "sector": "security",
                        "title": "Bandit Gathering Spotted",
                        "description": "UAV Alpha spotted group of 15 armed riders moving near Zamfara border.",
                        "severity": "critical",
                        "lat": 12.1550,
                        "lon": 6.6530,
                        "source": "drone_uav"
                    },
                    {
                        "sector": "agriculture",
                        "title": "Brush Fire Outbreak",
                        "description": "Satellite thermal scanner flags critical wildfire signature in Benue Crop Zone.",
                        "severity": "critical",
                        "lat": 7.3364 + random.uniform(-0.02, 0.02),
                        "lon": 8.9860 + random.uniform(-0.02, 0.02),
                        "source": "satellite_modis"
                    },
                    {
                        "sector": "mining",
                        "title": "Illegal Mining Breach",
                        "description": "Excavator activity detected outside designated boundary near Kaduna mine site.",
                        "severity": "high",
                        "lat": 10.5500,
                        "lon": 7.4200,
                        "source": "uav_recon"
                    },
                    {
                        "sector": "intelligence",
                        "title": "TikTok Propaganda Spike",
                        "description": "Sentiment metrics flag sudden surge in recruitment-oriented video uploads in Hausa.",
                        "severity": "high",
                        "lat": 12.0000,
                        "lon": 8.5000,
                        "source": "tiktok_monitor"
                    }
                ]
                
                selected = random.choice(alerts)
                threat = db.add({
                    "text": f"{selected['title']}: {selected['description']}",
                    "threat_type": selected["title"].upper().replace(" ", "_"),
                    "confidence": round(random.uniform(0.85, 0.99), 2),
                    "severity": selected["severity"],
                    "region": determine_region_from_coords(selected["lat"], selected["lon"]),
                    "source": selected["source"],
                    "latitude": selected["lat"],
                    "longitude": selected["lon"]
                })
                
                await publish_incident(selected["sector"], threat)

        except Exception as e:
            print(f"Error in telemetry loop: {e}")
        
        await asyncio.sleep(1)


# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    return JSONResponse({
        "system": "SAGE-NG",
        "tagline": "Real-time national intelligence and field operations network",
        "status": "online",
        "threats": len(db.threats),
        "field_alerts": len(field_alerts),
        "registered_devices": len(registered_devices),
        "mobile_clients_online": len(mobile_manager.active_connections)
    })

@app.get("/api/platform")
async def platform_status():
    return JSONResponse({
        "name": "SAGE-NG",
        "positioning": "A real-time national intelligence and field operations network",
        "sectors": ["intelligence", "security", "agriculture", "mining", "traffic"],
        "realtime": {
            "command_center_ws": "/ws/live",
            "mobile_ws": "/ws/mobile/{device_id}",
            "telemetry_frequency_seconds": 1
        },
        "safety_controls": [
            "confidence scoring",
            "verification status",
            "source traceability",
            "severity filtering",
            "geo-radius alert delivery"
        ]
    })

@app.post("/api/analyze/text")
async def analyze_text(text: str = Form(...), source: str = Form("api")):
    is_threat = any(kw in text.lower() for kw in THREAT_KEYWORDS)
    if not is_threat:
        return JSONResponse({"threat_detected": False, "message": "No threat detected"})
    
    threat_type, confidence, severity = analyze_threat(text)
    region = random.choice(REGIONS)
    
    threat = {
        "text": text[:300],
        "threat_type": threat_type,
        "confidence": confidence,
        "severity": severity,
        "region": region,
        "source": source
    }
    db.add(threat)
    
    return JSONResponse({
        "threat_detected": True,
        "analysis": threat,
        "action": "Immediate" if severity == "critical" else "Monitor"
    })

@app.get("/api/threats")
async def get_threats():
    return JSONResponse(db.get_recent())

@app.get("/api/social-media")
async def get_social_media_feed(limit: int = 15):
    latest = sorted(social_media_feed, key=lambda p: p["timestamp"], reverse=True)[:limit]
    return JSONResponse(latest)

@app.get("/api/dashboard/summary")
async def summary():
    return JSONResponse(db.get_summary())

@app.post("/api/devices/register")
async def register_device(request: Request):
    data = await request.json()
    device = register_or_update_device(data)
    return JSONResponse({
        "status": "registered",
        "device": device,
        "mobile_ws": f"/ws/mobile/{device['device_id']}"
    })

@app.get("/api/devices")
async def get_devices():
    return JSONResponse({
        "count": len(registered_devices),
        "online": len(mobile_manager.active_connections),
        "devices": list(registered_devices.values())
    })

@app.get("/api/alerts")
async def get_alerts(limit: int = 50, severity: str = None, sector: str = None):
    alerts = list(reversed(field_alerts))
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]
    if sector:
        alerts = [a for a in alerts if a.get("sector") == sector]
    return JSONResponse({
        "count": min(len(alerts), limit),
        "alerts": alerts[:limit]
    })

@app.get("/api/alerts/nearby")
async def get_nearby_alerts(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = 50,
    min_severity: str = "medium",
    limit: int = 50
):
    nearby = []
    for alert in reversed(field_alerts):
        if SEVERITY_RANK.get(alert.get("severity", "medium"), 0) < SEVERITY_RANK.get(min_severity, 2):
            continue
        if alert.get("latitude") is None or alert.get("longitude") is None:
            continue
        distance = haversine_km(lat, lon, alert["latitude"], alert["longitude"])
        if distance <= radius_km:
            nearby.append({**alert, "distance_km": round(distance, 2)})
        if len(nearby) >= limit:
            break
    return JSONResponse({
        "origin": {"latitude": lat, "longitude": lon},
        "radius_km": radius_km,
        "count": len(nearby),
        "alerts": nearby
    })

@app.post("/api/alerts")
async def create_alert(request: Request):
    data = await request.json()
    sector = data.get("sector", "intelligence")
    title = data.get("title", "Field Alert")
    description = data.get("description", data.get("text", "Field alert created"))
    severity = data.get("severity", "high")
    lat = data.get("latitude")
    lon = data.get("longitude")

    threat = db.add({
        "text": f"{title}: {description}",
        "threat_type": title.upper().replace(" ", "_"),
        "confidence": float(data.get("confidence", 0.9)),
        "severity": severity,
        "region": data.get("region") or (determine_region_from_coords(float(lat), float(lon)) if lat is not None and lon is not None else "Nigeria"),
        "source": data.get("source", "field_ops_api"),
        "latitude": lat,
        "longitude": lon
    })

    alert = create_field_alert(
        sector=sector,
        title=title,
        description=description,
        severity=severity,
        lat=lat,
        lon=lon,
        source=data.get("source", "field_ops_api"),
        threat_id=threat["id"],
        confidence=float(data.get("confidence", 0.9)),
        verification_status=data.get("verification_status", "pending_review"),
        audience=data.get("audience"),
        recommended_action=data.get("recommended_action")
    )

    await manager.broadcast({
        "type": "incident",
        "sector": sector,
        "incident": threat,
        "field_alert": alert
    })
    await mobile_manager.broadcast_alert(alert)

    return JSONResponse({
        "status": "created",
        "incident": threat,
        "field_alert": alert
    })

@app.post("/api/drone/telemetry")
async def receive_drone_telemetry(request: Request):
    """Receive telemetry from external drones"""
    try:
        data = await request.json()
        drone_id = data.get("drone_id", "unknown")
        
        drone_telemetry[drone_id] = {
            **data,
            "last_update": datetime.now().isoformat()
        }
        
        if "detection" in data:
            detection = data["detection"]
            threat = {
                "text": f"Drone {drone_id} detected {detection['type']} at {data['latitude']}, {data['longitude']}",
                "threat_type": detection["type"],
                "confidence": detection["confidence"],
                "severity": "critical" if detection["confidence"] > 0.85 else "high",
                "region": determine_region_from_coords(data["latitude"], data["longitude"]),
                "source": "drone",
                "timestamp": datetime.now().isoformat(),
                "latitude": data["latitude"],
                "longitude": data["longitude"]
            }
            threat = db.add(threat)
            
            # Broadcast this incident instantly over command-center and mobile WebSockets
            await publish_incident("security", threat)
            print(f"[ALERT] New threat detected by drone: {detection['type']}")
        
        return JSONResponse({"status": "ok", "message": "Telemetry received"})
    except Exception as e:
        print(f"Error processing drone telemetry: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/drone/status")
async def get_drone_status():
    drones_list = []
    for drone_id, data in drone_telemetry.items():
        drones_list.append({
            "id": drone_id,
            "name": data.get("name", f"UAV {drone_id}"),
            "status": data.get("status", "unknown"),
            "battery": data.get("battery", 0),
            "altitude": data.get("altitude", 0),
            "latitude": data.get("latitude", 0),
            "longitude": data.get("longitude", 0),
            "last_update": data.get("last_update", ""),
            "has_detection": "detection" in data
        })
    
    return JSONResponse({
        "active_drones": len(drones_list),
        "drones": drones_list,
        "timestamp": datetime.now().isoformat()
    })

# API to manually trigger/simulate an incident from the Control Panel UI
@app.post("/api/simulate")
async def manual_simulate(request: Request):
    try:
        data = await request.json()
        sector = data.get("sector", "security")
        title = data.get("title", "Manual Event")
        description = data.get("description", "A custom simulated event triggered by supervisor.")
        severity = data.get("severity", "high")
        lat = float(data.get("latitude", 9.0820))
        lon = float(data.get("longitude", 8.6753))
        region = data.get("region") or determine_region_from_coords(lat, lon)
        source = data.get("source", "dashboard_console")

        # Save to threats
        threat = db.add({
            "text": f"{title}: {description}",
            "threat_type": title.upper().replace(" ", "_"),
            "confidence": 1.0,
            "severity": severity,
            "region": region,
            "source": source,
            "latitude": lat,
            "longitude": lon
        })

        # Broadcast immediately to command-center and mobile clients
        alert = await publish_incident(sector, threat)

        return JSONResponse({"status": "ok", "message": "Manual event broadcasted", "incident": threat, "field_alert": alert})
    except Exception as e:
        print(f"Error in manual simulation: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


def determine_region_from_coords(lat, lon):
    """Simple region determination from coordinates in Nigeria"""
    if lat > 10 and lon > 10:
        return "North East"
    elif lat > 10 and lon < 8:
        return "North West"
    elif lat > 8 and lat < 10:
        return "North Central"
    elif lat < 8 and lon > 5:
        return "South East"
    elif lat < 8 and lon <= 5:
        return "South West"
    else:
        return "North Central"


# Serve HTML Dashboard
@app.get("/dashboard")
async def dashboard():
    html_path = Path(__file__).resolve().parent / "sage-ng-dashboard.html"
    if not html_path.exists():
        return HTMLResponse(content="<h1>Dashboard file not found</h1>", status_code=404)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"), media_type="text/html")


@app.get("/mobile")
async def mobile_client():
    html_path = Path(__file__).resolve().parent / "mobile-field-client.html"
    if not html_path.exists():
        return HTMLResponse(content="<h1>Mobile client file not found</h1>", status_code=404)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"), media_type="text/html")


# WebSocket connection route
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Send initial database snapshot on connect
    await websocket.send_json({
        "type": "init",
        "threats": db.get_recent(20),
        "summary": db.get_summary(),
        "drones": list(drone_telemetry.values()),
        "field_alerts": list(reversed(field_alerts[-20:])),
        "registered_devices": len(registered_devices)
    })
    try:
        while True:
            # Keep connection open, handle pings if client sends them
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/mobile/{device_id}")
async def mobile_websocket_endpoint(device_id: str, websocket: WebSocket):
    if device_id not in registered_devices:
        register_or_update_device({
            "device_id": device_id,
            "label": "Unverified Mobile Client",
            "role": "field",
            "sectors": ["all"],
            "min_severity": "medium",
            "radius_km": 50
        })

    await mobile_manager.connect(device_id, websocket)
    device = registered_devices[device_id]
    matching_alerts = [a for a in reversed(field_alerts[-50:]) if should_deliver_alert(device, a)]
    await websocket.send_json({
        "type": "mobile_init",
        "device": device,
        "alerts": matching_alerts[:20],
        "message": "SAGE-NG mobile live alert channel active"
    })

    try:
        while True:
            raw = await websocket.receive_text()
            if raw.lower() in ["ping", "heartbeat"]:
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
                continue

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Expected JSON payload or ping"})
                continue

            if payload.get("type") in ["location_update", "device_update"]:
                updated = register_or_update_device({
                    **registered_devices.get(device_id, {}),
                    **payload,
                    "device_id": device_id
                })
                await websocket.send_json({
                    "type": "device_updated",
                    "device": updated,
                    "timestamp": datetime.now().isoformat()
                })
    except WebSocketDisconnect:
        mobile_manager.disconnect(device_id)


# Add seed sample threat data
seed_threats = [
    {"text": "Bandits attacked village in Zamfara, kidnapped 15 people", "lat": 12.1550, "lon": 6.6530, "type": "BANDIT_ATTACK", "sev": "critical"},
    {"text": "Suspected Boko Haram movement near Maiduguri, Borno", "lat": 11.8311, "lon": 13.1510, "type": "TERRORISM", "sev": "high"},
    {"text": "Farmer-herder clash in Benue leaves 7 dead", "lat": 7.3364, "lon": 8.9860, "type": "COMMUNAL_CONFLICT", "sev": "high"},
    {"text": "ISWAP claims responsibility for checkpoint attack near Katsina", "lat": 12.9850, "lon": 7.6000, "type": "TERRORISM", "sev": "critical"}
]

for seed in seed_threats:
    threat = db.add({
        "text": seed["text"],
        "threat_type": seed["type"],
        "confidence": 0.85,
        "severity": seed["sev"],
        "region": determine_region_from_coords(seed["lat"], seed["lon"]),
        "source": "intel_seed",
        "latitude": seed["lat"],
        "longitude": seed["lon"]
    })
    create_field_alert(
        sector="security" if seed["type"] != "COMMUNAL_CONFLICT" else "intelligence",
        title=seed["type"].replace("_", " ").title(),
        description=seed["text"],
        severity=seed["sev"],
        lat=seed["lat"],
        lon=seed["lon"],
        source="intel_seed",
        threat_id=threat["id"],
        confidence=0.85,
        verification_status="historical_seed",
        audience=["command", "field"]
    )

register_or_update_device({
    "device_id": "SAGE-MOB-KADUNA-01",
    "label": "Kaduna Field Response",
    "role": "field_agent",
    "latitude": 10.5105,
    "longitude": 7.4165,
    "radius_km": 120,
    "sectors": ["security", "traffic"],
    "min_severity": "medium"
})
register_or_update_device({
    "device_id": "SAGE-MOB-BENUE-01",
    "label": "Benue Agri Watch",
    "role": "agri_extension",
    "latitude": 7.3364,
    "longitude": 8.9860,
    "radius_km": 90,
    "sectors": ["agriculture", "intelligence"],
    "min_severity": "high"
})
register_or_update_device({
    "device_id": "SAGE-MOB-NATIONAL-OPS",
    "label": "National Operations Desk",
    "role": "command",
    "radius_km": 1000,
    "sectors": ["all"],
    "min_severity": "high"
})

print(f"\n[OK] Loaded {len(db.threats)} sample threats, {len(field_alerts)} field alerts, {len(registered_devices)} mobile devices")

# Run server
if __name__ == "__main__":
    print("\n" + "="*50)
    print("SAGE-NG FIELD OPERATIONS NETWORK RUNNING")
    print("="*50)
    print("\nDASHBOARD: http://localhost:8000/dashboard")
    print("API:       http://localhost:8000")
    print("MOBILE:    ws://localhost:8000/ws/mobile/SAGE-MOB-NATIONAL-OPS")
    print("\nPress CTRL+C to stop")
    print("="*50 + "\n")
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
