
import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")


async def main():
    async with TelegramClient(
        "magician_telegram", api_id, api_hash
    ) as client:
        me = await client.get_me()

        print("¡Conectado a Telegram!")
        print(f"Usuario: {me.first_name}")

        print("\nBuscando canales de novelas...")

        async for dialog in client.iter_dialogs():
            if dialog.is_channel:
                if "novelas" in dialog.name.lower():
                    print(
                        f"ENCONTRADO: {dialog.name} | ID: {dialog.id}"
                    )


asyncio.run(main())
