"""
webapp_server.py — Flask API сервер для Telegram Mini App
Запускать вместе с основным ботом: python webapp_server.py
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

DB_MAIN = '../base.db'
DB_RSS  = '../autoposter.db'
LOG_FILE = '../logi.txt'

# ─── helpers ──────────────────────────────────────────────
def db_main():
    return sqlite3.connect(DB_MAIN)

def db_rss():
    return sqlite3.connect(DB_RSS)

def _get_status(table):
    with db_main() as c:
        r = c.execute(f"SELECT status FROM {table} WHERE id=1").fetchone()
        return bool(r[0]) if r else False

def _set_status(table, value):
    with db_main() as c:
        c.execute(f"UPDATE {table} SET status=? WHERE id=1", (int(value),))

# ─── Serve index.html ─────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ─── Status ───────────────────────────────────────────────
@app.route('/api/status')
def get_status():
    with db_main() as c:
        prompt = c.execute("SELECT text FROM promt_gpt WHERE id=1").fetchone()
        mapping = c.execute("SELECT source_id, dest_id FROM channel_mapping").fetchall()
        sources = {r[0]: r[1] for r in c.execute("SELECT channel_id, title FROM channels").fetchall()}
        dests   = {r[0]: r[1] for r in c.execute("SELECT channel_id, title FROM destination_channels").fetchall()}
        whitelist = [r[0] for r in c.execute("SELECT word FROM whitelist").fetchall()]
        blacklist = [r[0] for r in c.execute("SELECT word FROM blacklist").fetchall()]
        deleting  = [r[0] for r in c.execute("SELECT word FROM deleting_text").fetchall()]

    with db_rss() as c:
        rss = [{'url': r[0], 'title': r[1]} for r in c.execute("SELECT url, title FROM rss_channels").fetchall()]
        posted = c.execute("SELECT COUNT(*) FROM published_news").fetchone()[0]

    channels = [
        {'src_id': s, 'src_title': sources.get(s,'?'), 'dst_id': d, 'dst_title': dests.get(d,'?')}
        for s, d in mapping
    ]

    return jsonify({
        'moderation':       _get_status('moderation_status'),
        'copywriting':      _get_status('copyrighting_status'),
        'link_replacement': _get_status('link_replacement_status'),
        'rss_scanning':     _get_status('rss_scanning_status'),
        'gpt_mode':         _get_status('gpt_mode'),
        'prompt':           prompt[0] if prompt else '',
        'channels':         channels,
        'whitelist':        whitelist,
        'blacklist':        blacklist,
        'deleting_text':    deleting,
        'rss':              rss,
        'stats':            {'posted': posted},
    })

# ─── Toggle ───────────────────────────────────────────────
TABLE_MAP = {
    'moderation':       'moderation_status',
    'copywriting':      'copyrighting_status',
    'link_replacement': 'link_replacement_status',
    'rss_scanning':     'rss_scanning_status',
    'gpt_mode':         'gpt_mode',
}

@app.route('/api/toggle', methods=['POST'])
def toggle():
    data = request.json
    key, value = data.get('key'), data.get('value')
    table = TABLE_MAP.get(key)
    if not table:
        return jsonify({'ok': False, 'error': 'Unknown key'})
    _set_status(table, value)
    return jsonify({'ok': True})

# ─── Prompt ───────────────────────────────────────────────
@app.route('/api/prompt', methods=['POST'])
def set_prompt():
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'ok': False})
    with db_main() as c:
        c.execute("INSERT OR REPLACE INTO promt_gpt (id, text) VALUES (1, ?)", (text,))
    return jsonify({'ok': True})

# ─── Channels ─────────────────────────────────────────────
@app.route('/api/channels', methods=['POST'])
def add_channel():
    d = request.json
    src_id, src_title = d['src_id'], d.get('src_title', '?')
    dst_id, dst_title = d['dst_id'], d.get('dst_title', '?')
    with db_main() as c:
        c.execute("INSERT OR IGNORE INTO channels (channel_id, title) VALUES (?,?)", (src_id, src_title))
        c.execute("INSERT OR IGNORE INTO destination_channels (channel_id, title) VALUES (?,?)", (dst_id, dst_title))
        c.execute("INSERT OR IGNORE INTO channel_mapping (source_id, dest_id) VALUES (?,?)", (src_id, dst_id))
    return jsonify({'ok': True})

@app.route('/api/channels', methods=['DELETE'])
def remove_channel():
    d = request.json
    with db_main() as c:
        c.execute("DELETE FROM channel_mapping WHERE source_id=? AND dest_id=?", (d['src_id'], d['dst_id']))
    return jsonify({'ok': True})

# ─── Words ────────────────────────────────────────────────
LIST_TABLES = {'whitelist': 'whitelist', 'blacklist': 'blacklist', 'deleting_text': 'deleting_text'}

@app.route('/api/words', methods=['POST'])
def add_word():
    d = request.json
    table = LIST_TABLES.get(d.get('list'))
    if not table:
        return jsonify({'ok': False})
    with db_main() as c:
        c.execute(f"INSERT OR IGNORE INTO {table} (word) VALUES (?)", (d['word'],))
    return jsonify({'ok': True})

@app.route('/api/words', methods=['DELETE'])
def remove_word():
    d = request.json
    table = LIST_TABLES.get(d.get('list'))
    if not table:
        return jsonify({'ok': False})
    with db_main() as c:
        c.execute(f"DELETE FROM {table} WHERE word=?", (d['word'],))
    return jsonify({'ok': True})

# ─── RSS ──────────────────────────────────────────────────
@app.route('/api/rss', methods=['POST'])
def add_rss():
    d = request.json
    with db_rss() as c:
        c.execute("INSERT OR IGNORE INTO rss_channels (url, title) VALUES (?,?)", (d['url'], d['title']))
    return jsonify({'ok': True})

@app.route('/api/rss', methods=['DELETE'])
def remove_rss():
    d = request.json
    with db_rss() as c:
        c.execute("DELETE FROM rss_channels WHERE url=?", (d['url'],))
    return jsonify({'ok': True})

# ─── Logs ─────────────────────────────────────────────────
@app.route('/api/logs')
def get_logs():
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return jsonify({'lines': [l.strip() for l in lines[-100:] if l.strip()]})
    except:
        return jsonify({'lines': []})

if __name__ == '__main__':
    print("🌐 Mini App сервер запущен: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
