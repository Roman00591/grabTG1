from telethon import TelegramClient
import json

with open('config.json', 'r') as f:
    config = json.load(f)

api_id = config["api_id"]
api_hash = config["api_hash"]

client = TelegramClient('myGrab', api_id, api_hash,
                        device_model="Samsung S10 Lite",
                        system_version='4.16.30-vxCUSTOM')

async def main():
    await client.start()
    me = await client.get_me()
    print(f"Сессия создана! Авторизован как: {me.first_name} (ID: {me.id})")

with client:
    client.loop.run_until_complete(main())
