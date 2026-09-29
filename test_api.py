import asyncio
import httpx
from core.config import TELEGRAM_TOKEN

async def main():
    async with httpx.AsyncClient() as client:
        # Get bot info
        print("Obteniendo información del bot...")
        res = await client.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe")
        print("Bot info:", res.json())
        
        # Get updates
        print("\nBuscando mensajes (Updates)...")
        res2 = await client.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates")
        print("Updates:", res2.json())

if __name__ == "__main__":
    asyncio.run(main())
