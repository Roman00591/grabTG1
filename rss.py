import asyncio
import logging
import feedparser
from database import get_all_rss_channels, mark_news_as_published, is_news_published

logger = logging.getLogger(__name__)


async def scan_and_post_rss_news(client, dest_channel_id, max_entries=10):
    channels = get_all_rss_channels()
    if not channels:
        return

    for url, title in channels:
        try:
            feed = feedparser.parse(url)
            entries = feed.entries[:max_entries]
            for entry in reversed(entries):
                link = entry.get('link', '')
                if not link or is_news_published(link):
                    continue
                text = f"📰 <b>{entry.get('title', '')}</b>\n\n{entry.get('summary', '')}\n\n🔗 {link}"
                await client.send_message(dest_channel_id, text, parse_mode='html')
                mark_news_as_published(link)
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Ошибка RSS {url}: {e}")
