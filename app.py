"""
Simple URL Shortener — single-file Flask app + SQLite

(Instructions omitted for brevity — same as before)
"""

from flask import Flask, request, redirect, jsonify, g, render_template_string
import sqlite3
import secrets
import string
from urllib.parse import urlparse
import os
from datetime import datetime

# Configuration
DB_PATH = os.path.join(os.path.dirname(__file__), "urls.db")
SHORT_CODE_LENGTH = 6
ALPHABET = string.ascii_letters + string.digits

app = Flask(__name__)
app.config.update(PROPAGATE_EXCEPTIONS=True)

# -----------------
# Database helpers
# -----------------

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS urls (
            code TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            clicks INTEGER DEFAULT 0
        )
        """
    )
    db.commit()

# Ensure DB exists on startup
with app.app_context():
    init_db()

# -----------------
# Utility functions
# -----------------

def generate_code(length=SHORT_CODE_LENGTH):
    while True:
        code = ''.join(secrets.choice(ALPHABET) for _ in range(length))
        db = get_db()
        cur = db.execute('SELECT 1 FROM urls WHERE code = ?', (code,))
        if cur.fetchone() is None:
            return code

def validate_and_normalize_url(url: str):
    if not url:
        return None
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = 'http://' + url
        parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return None
    if not parsed.netloc:
        return None
    return url

# -----------------
# Routes
# -----------------

INDEX_HTML = """
<!doctype html>
<html>
<head>
<title>Tiny Shortener</title>
</head>
<body>
<h1>Tiny URL Shortener</h1>
<form id="shortenForm" method="post" action="/shorten">
  <input name="url" placeholder="https://example.com" required />
  <input name="custom" placeholder="custom (optional)" />
  <button type="submit">Shorten</button>
</form>
<div id="result" style="display:none"></div>
<script>
const form = document.getElementById('shortenForm');
const result = document.getElementById('result');
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(form);
  const body = {};
  fd.forEach((v,k)=> body[k]=v);
  const resp = await fetch('/shorten', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const data = await resp.json();
  if (resp.ok) {
    result.style.display='block';
    result.innerHTML = `Short URL: <a href="${data.short_url}" target="_blank">${data.short_url}</a>`;
  } else {
    result.style.display='block';
    result.innerText = data.error || 'Error';
  }
});
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/shorten', methods=['POST'])
def shorten():
    payload = request.get_json() if request.is_json else request.form.to_dict()
    original = payload.get('url')
    custom = payload.get('custom')
    url = validate_and_normalize_url(original)
    if not url:
        return jsonify({'error':'Invalid URL'}), 400
    db = get_db()
    if custom:
        if not all(c.isalnum() or c in ('-','_') for c in custom):
            return jsonify({'error':'Invalid characters in custom code'}), 400
        cur = db.execute('SELECT url FROM urls WHERE code = ?', (custom,))
        if cur.fetchone():
            return jsonify({'error':'Custom code in use'}), 409
        code = custom
    else:
        code = generate_code()
    db.execute('INSERT INTO urls (code, url, created_at, clicks) VALUES (?, ?, ?, ?)', (code, url, datetime.utcnow(), 0))
    db.commit()
    short_url = request.host_url.rstrip('/') + '/' + code
    return jsonify({'short_url': short_url}), 201

@app.route('/<code>')
def redirect_code(code):
    db = get_db()
    cur = db.execute('SELECT url FROM urls WHERE code = ?', (code,))
    row = cur.fetchone()
    if not row:
        return "Not found", 404
    db.execute('UPDATE urls SET clicks = clicks + 1 WHERE code = ?', (code,))
    db.commit()
    return redirect(row['url'])

@app.route('/stats/<code>')
def stats(code):
    db = get_db()
    cur = db.execute('SELECT code, url, created_at, clicks FROM urls WHERE code = ?', (code,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error':'Not found'}), 404
    return jsonify(dict(row))

if __name__ == '__main__':
    app.run(debug=True)
