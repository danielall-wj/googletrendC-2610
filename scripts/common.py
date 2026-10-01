"""Shared HTTP and JSON helpers. No remote JavaScript is executed."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = 'https://trends.google.co.kr'
GEOS = {'KR': ('ko', 'ko-KR', '대한민국'), 'US': ('en', 'en-US', '미국'), 'JP': ('ja', 'ja-JP', '일본')}
HOURS = (4, 24, 48, 168)
ROOT = Path(__file__).resolve().parents[1] / 'public' / 'data'


def utcnow():
    return datetime.now(timezone.utc)


def stamp(dt=None):
    return (dt or utcnow()).isoformat(timespec='seconds').replace('+00:00', 'Z')


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
    temp.replace(path)


def decode_json(text):
    text = text.lstrip()
    if text.startswith(")]}'"):
        text = text[4:].lstrip('\r\n ,')
    return json.loads(text)


class Client:
    def __init__(self, delay=1.5):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'})
        self.delay = delay
        self.last = 0

    def request(self, method, url, **kwargs):
        for attempt in range(3):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
            try:
                response = self.session.request(method, url, timeout=(10, 30), **kwargs)
                self.last = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        retry = response.headers.get('Retry-After', '')
                        # Do not retry earlier than a server's long requested delay.
                        if retry.isdigit() and int(retry) > 60:
                            response.raise_for_status()
                        time.sleep(int(retry) if retry.isdigit() else 3 * 2 ** attempt)
                        continue
                response.raise_for_status()
                return response.text
            except (requests.ConnectionError, requests.Timeout):
                self.last = time.monotonic()
                if attempt == 2:
                    raise
                time.sleep(3 * 2 ** attempt)
        raise RuntimeError('HTTP retry exhausted')

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)
