import sqlite3

DB_MAIN = 'base.db'
DB_RSS = 'autoposter.db'

def initialize_db():
    with sqlite3.connect(DB_MAIN) as conn:
        c = conn.cursor()
        c.executescript('''
            CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE);
            CREATE TABLE IF NOT EXISTS promt_gpt (id INTEGER PRIMARY KEY, text TEXT);
            CREATE TABLE IF NOT EXISTS moderation_status (id INTEGER PRIMARY KEY, status INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS link_replacement_status (id INTEGER PRIMARY KEY, status INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS username_replacement_status (id INTEGER PRIMARY KEY, status INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS rss_scanning_status (id INTEGER PRIMARY KEY, status INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS copyrighting_status (id INTEGER PRIMARY KEY, status INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS translate_status (id INTEGER PRIMARY KEY, status INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS gpt_mode (id INTEGER PRIMARY KEY, status INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS image_generation_method (id INTEGER PRIMARY KEY, method TEXT DEFAULT 'kandinsky');
            CREATE TABLE IF NOT EXISTS whitelist (id INTEGER PRIMARY KEY, word TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS blacklist (id INTEGER PRIMARY KEY, word TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS deleting_text (id INTEGER PRIMARY KEY, word TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS eliminated_words (id INTEGER PRIMARY KEY, word TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, channel_id INTEGER UNIQUE, title TEXT);
            CREATE TABLE IF NOT EXISTS destination_channels (id INTEGER PRIMARY KEY, channel_id INTEGER UNIQUE, title TEXT);
            CREATE TABLE IF NOT EXISTS channel_mapping (id INTEGER PRIMARY KEY, source_id INTEGER, dest_id INTEGER);
            CREATE TABLE IF NOT EXISTS text_ends (id INTEGER PRIMARY KEY, channel_id INTEGER UNIQUE, text TEXT);
            CREATE TABLE IF NOT EXISTS usernames (id INTEGER PRIMARY KEY, old_name TEXT, new_name TEXT);
            CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY, old_link TEXT, new_link TEXT);
        ''')
        # Defaults
        c.execute("INSERT OR IGNORE INTO moderation_status VALUES (1, 0)")
        c.execute("INSERT OR IGNORE INTO link_replacement_status VALUES (1, 0)")
        c.execute("INSERT OR IGNORE INTO username_replacement_status VALUES (1, 0)")
        c.execute("INSERT OR IGNORE INTO rss_scanning_status VALUES (1, 0)")
        c.execute("INSERT OR IGNORE INTO copyrighting_status VALUES (1, 0)")
        c.execute("INSERT OR IGNORE INTO translate_status VALUES (1, 0)")
        c.execute("INSERT OR IGNORE INTO gpt_mode VALUES (1, 1)")
        c.execute("INSERT OR IGNORE INTO image_generation_method VALUES (1, 'kandinsky')")
        c.execute("INSERT OR IGNORE INTO promt_gpt VALUES (1, 'Сделай рерайт этого текста на русском языке и отправь только его:')")
        conn.commit()

    with sqlite3.connect(DB_RSS) as conn:
        c = conn.cursor()
        c.executescript('''
            CREATE TABLE IF NOT EXISTS rss_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS published_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE NOT NULL
            );
        ''')
        conn.commit()

# ─── Admins ───────────────────────────────────────────────
def add_admin(user_id):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))

def remove_admin(user_id):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))

def get_admins():
    with sqlite3.connect(DB_MAIN) as conn:
        return [r[0] for r in conn.execute("SELECT user_id FROM admins").fetchall()]

# ─── Status helpers ───────────────────────────────────────
def _get_status(table):
    with sqlite3.connect(DB_MAIN) as conn:
        r = conn.execute(f"SELECT status FROM {table} WHERE id=1").fetchone()
        return bool(r[0]) if r else False

def _set_status(table, value):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute(f"UPDATE {table} SET status=? WHERE id=1", (int(value),))

def get_moderation(): return _get_status('moderation_status')
def set_moderation(v): _set_status('moderation_status', v)

def get_link_replacement(): return _get_status('link_replacement_status')
def set_link_replacement(v): _set_status('link_replacement_status', v)

def get_username_replacement(): return _get_status('username_replacement_status')
def set_username_replacement(v): _set_status('username_replacement_status', v)

def get_rss_scanning(): return _get_status('rss_scanning_status')
def set_rss_scanning(v): _set_status('rss_scanning_status', v)

def get_copywriting(): return _get_status('copyrighting_status')
def set_copywriting(v): _set_status('copyrighting_status', v)

def get_translate(): return _get_status('translate_status')
def set_translate(v): _set_status('translate_status', v)

def get_gpt_mode(): return _get_status('gpt_mode')
def set_gpt_mode(v): _set_status('gpt_mode', v)

# ─── Prompt ───────────────────────────────────────────────
def get_prompt():
    with sqlite3.connect(DB_MAIN) as conn:
        r = conn.execute("SELECT text FROM promt_gpt WHERE id=1").fetchone()
        return r[0] if r else "Сделай рерайт этого текста на русском языке и отправь только его:"

def set_prompt(text):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("INSERT OR REPLACE INTO promt_gpt (id, text) VALUES (1, ?)", (text,))

# ─── Channels ─────────────────────────────────────────────
def add_source_channel(channel_id, title):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("INSERT OR IGNORE INTO channels (channel_id, title) VALUES (?,?)", (channel_id, title))

def remove_source_channel(channel_id):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))
        conn.execute("DELETE FROM channel_mapping WHERE source_id=?", (channel_id,))

def get_source_channels():
    with sqlite3.connect(DB_MAIN) as conn:
        return conn.execute("SELECT channel_id, title FROM channels").fetchall()

def add_dest_channel(channel_id, title):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("INSERT OR IGNORE INTO destination_channels (channel_id, title) VALUES (?,?)", (channel_id, title))

def remove_dest_channel(channel_id):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("DELETE FROM destination_channels WHERE channel_id=?", (channel_id,))
        conn.execute("DELETE FROM channel_mapping WHERE dest_id=?", (channel_id,))

def get_dest_channels():
    with sqlite3.connect(DB_MAIN) as conn:
        return conn.execute("SELECT channel_id, title FROM destination_channels").fetchall()

def add_channel_mapping(source_id, dest_id):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("INSERT OR IGNORE INTO channel_mapping (source_id, dest_id) VALUES (?,?)", (source_id, dest_id))

def remove_channel_mapping(source_id, dest_id):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("DELETE FROM channel_mapping WHERE source_id=? AND dest_id=?", (source_id, dest_id))

def get_channel_mapping():
    with sqlite3.connect(DB_MAIN) as conn:
        return conn.execute("SELECT source_id, dest_id FROM channel_mapping").fetchall()

# ─── Word lists ───────────────────────────────────────────
def add_word(table, word):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute(f"INSERT OR IGNORE INTO {table} (word) VALUES (?)", (word,))

def remove_word(table, word):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute(f"DELETE FROM {table} WHERE word=?", (word,))

def get_words(table):
    with sqlite3.connect(DB_MAIN) as conn:
        return [r[0] for r in conn.execute(f"SELECT word FROM {table}").fetchall()]

# ─── Text ends ────────────────────────────────────────────
def set_text_end(channel_id, text):
    with sqlite3.connect(DB_MAIN) as conn:
        conn.execute("INSERT OR REPLACE INTO text_ends (channel_id, text) VALUES (?,?)", (channel_id, text))

def get_text_end(channel_id):
    with sqlite3.connect(DB_MAIN) as conn:
        r = conn.execute("SELECT text FROM text_ends WHERE channel_id=?", (channel_id,)).fetchone()
        return r[0] if r else ""

# ─── Usernames / Links ────────────────────────────────────
def get_usernames():
    with sqlite3.connect(DB_MAIN) as conn:
        return conn.execute("SELECT old_name, new_name FROM usernames").fetchall()

def get_links():
    with sqlite3.connect(DB_MAIN) as conn:
        return conn.execute("SELECT old_link, new_link FROM links").fetchall()

# ─── RSS ──────────────────────────────────────────────────
def add_rss_channel_to_db(url, title):
    with sqlite3.connect(DB_RSS) as conn:
        conn.execute("INSERT OR IGNORE INTO rss_channels (url, title) VALUES (?,?)", (url, title))

def remove_rss_channel_from_db(url):
    with sqlite3.connect(DB_RSS) as conn:
        conn.execute("DELETE FROM rss_channels WHERE url=?", (url,))

def get_all_rss_channels():
    with sqlite3.connect(DB_RSS) as conn:
        return conn.execute("SELECT url, title FROM rss_channels").fetchall()

def mark_news_as_published(link):
    with sqlite3.connect(DB_RSS) as conn:
        conn.execute("INSERT OR IGNORE INTO published_news (link) VALUES (?)", (link,))

def is_news_published(link):
    with sqlite3.connect(DB_RSS) as conn:
        return conn.execute("SELECT 1 FROM published_news WHERE link=?", (link,)).fetchone() is not None
