import aiohttp
import logging
import g4f
import json
from aiohttp_socks import ProxyConnector
from database import get_gpt_mode, get_prompt

with open('config.json', 'r') as f:
    config = json.load(f)

link_gpt = config.get("link_gpt")
openai_api_key_gpt = config.get("openai_api_key_gpt")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def rewrite_text_with_internal_gpt(text):
    prompt = get_prompt() + " " + text
    try:
        response = g4f.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        if isinstance(response, str):
            return response
    except Exception as e:
        logger.error(f"Ошибка внутреннего GPT: {e}")
    return None


async def rewrite_text_with_external_gpt(text, api_key, proxy_url, proxy_user, proxy_pass):
    prompt = get_prompt() + " " + text
    json_data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt}]
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    connector = ProxyConnector.from_url(f'socks5://{proxy_user}:{proxy_pass}@{proxy_url}')
    timeout = aiohttp.ClientTimeout(total=70)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.post(link_gpt, json=json_data, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['choices'][0]['message']['content']
                else:
                    logger.error(f"OpenAI error {resp.status}: {await resp.text()}")
    except Exception as e:
        logger.error(f"Ошибка внешнего GPT: {e}")
    return None


async def rewrite_text(text, proxy_url=None, proxy_user=None, proxy_pass=None):
    if not text:
        return None
    if get_gpt_mode():
        logger.info("Используется внутренний GPT")
        return await rewrite_text_with_internal_gpt(text)
    else:
        logger.info("Используется внешний GPT")
        return await rewrite_text_with_external_gpt(text, openai_api_key_gpt, proxy_url, proxy_user, proxy_pass)
