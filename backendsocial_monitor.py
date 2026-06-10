# backend/social_monitor.py
import asyncio
import aiohttp
from typing import List, Dict
from bs4 import BeautifulSoup
import re

class SocialMediaMonitor:
    def __init__(self, llm_processor):
        self.llm = llm_processor
        self.keywords = [
            "boko haram", "bandit", "zamfara attack", "katsina", 
            "kidnap", "ransom", "ISWAP", "herder", "fulani attack"
        ]
    
    async def scrape_tiktok(self, keyword: str) -> List[Dict]:
        """Scrape TikTok (using unofficial API or playwright)"""
        # Simplified - in production use TikTok's unofficial API
        url = f"https://www.tiktok.com/search?q={keyword}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                html = await response.text()
                # Parse for video captions
                soup = BeautifulSoup(html, 'html.parser')
                captions = soup.find_all('div', class_='video-caption')
                
                threats = []
                for cap in captions:
                    text = cap.get_text()
                    threat = self.llm.classify_threat(text)
                    if threat['confidence'] > 0.7:
                        threats.append({
                            "platform": "tiktok",
                            "text": text,
                            "threat": threat,
                            "timestamp": datetime.now()
                        })
                return threats
    
    async def monitor_telegram_channels(self, channels: List[str]) -> List[Dict]:
        """Monitor public Telegram channels"""
        # Use Telethon library
        from telethon import TelegramClient
        
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        
        client = TelegramClient('sage_session', api_id, api_hash)
        await client.start()
        
        threats = []
        for channel in channels:
            async for message in client.iter_messages(channel, limit=50):
                if message.text:
                    threat = self.llm.classify_threat(message.text)
                    if threat['confidence'] > 0.7:
                        threats.append({
                            "platform": "telegram",
                            "channel": channel,
                            "text": message.text,
                            "threat": threat
                        })
        return threats