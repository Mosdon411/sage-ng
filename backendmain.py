# backend/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Optional
import asyncpg
import redis
import json
import os

app = FastAPI(title="SAGE-NG Intelligence API", version="1.0.0")

# CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
db_pool = None
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(
        user="sage_user",
        password="secure_password",
        database="sage_ng",
        host="localhost"
    )
    print("✅ Database connected")

# Threat model
class Threat(BaseModel):
    id: Optional[str]
    region: str  # North East, North West, etc.
    threat_type: str  # bandit, terrorist, herder-conflict
    severity: str  # critical, high, medium, low
    title: str
    description: str
    source: str  # tiktok, twitter, telegram, news
    timestamp: datetime
    latitude: Optional[float]
    longitude: Optional[float]

# API endpoints
@app.get("/api/threats/active")
async def get_active_threats():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM threats 
            WHERE status = 'active' 
            AND timestamp > NOW() - INTERVAL '24 hours'
            ORDER BY severity_score DESC
        """)
        return [dict(row) for row in rows]

@app.get("/api/instability-index/{region}")
async def get_instability_index(region: str):
    # Calculate based on threat density + severity
    async with db_pool.acquire() as conn:
        result = await conn.fetchval("""
            SELECT AVG(severity_score * frequency) 
            FROM threats 
            WHERE region = $1 AND timestamp > NOW() - INTERVAL '7 days'
        """, region)
        return {"region": region, "index": float(result) if result else 0}

# WebSocket for real-time updates
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Send latest threats every 5 seconds
            async with db_pool.acquire() as conn:
                latest = await conn.fetch("""
                    SELECT * FROM threats 
                    ORDER BY timestamp DESC LIMIT 5
                """)
                await websocket.send_json([dict(row) for row in latest])
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        print("Client disconnected")