"""Prefer Trends-linked news, fill missing keywords from Google News RSS."""
import time
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from common import BASE, GEOS, load_json, write_json, stamp, utcnow

NS = {'ht': 'https://trends.google.com/trending/rss'}


def key(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def safe_url(url):
    return url if isinstance(url, str) and urlparse(url).scheme in ('http', 'https') and urlparse(url).netloc else None


def published(text):
    try:
        return stamp(parsedate_to_datetime(text)) if text else None
    except (ValueError, TypeError, OverflowError):
        return None


def dedupe(articles):
    seen = set()
    results = []
    for article in articles:
        identity = re.sub(r'\W+', '', key(article['title']))
        if identity in seen or not article['url']:
            continue
        seen.add(identity)
        results.append(article)
    return results[:3]


def parse_trends_rss(xml):
    result = {}
    for item in ET.fromstring(xml).findall('./channel/item'):
        articles = []
        for news in item.findall('ht:news_item', NS):
            get = lambda name: html.unescape(news.findtext('ht:news_item_' + name, '', NS))
            articles.append({'title': get('title'), 'source': get('source'), 'url': safe_url(get('url')),
                             'image': safe_url(get('picture')), 'published_at': None, 'origin': 'google-trends-rss'})
        result[key(item.findtext('title', ''))] = dedupe(articles)
    return result


def parse_news_rss(xml):
    items = []
    for item in ET.fromstring(xml).findall('./channel/item'):
        items.append({'title': html.unescape(item.findtext('title', '')), 'source': item.findtext('source', ''),
                      'url': safe_url(item.findtext('link', '')), 'published_at': published(item.findtext('pubDate')),
                      'image': None, 'origin': 'google-news-search'})
    items.sort(key=lambda x: x['published_at'] or '', reverse=True)
    return dedupe(items)


class NewsProvider:
    def __init__(self, client, root, geo, budget=120):
        self.client, self.root, self.geo, self.budget = client, root, geo, budget
        self.calls = 0
        self.deadline = time.monotonic() + 120
        self.consecutive_errors = 0
        self.cache = load_json(root / 'news-cache' / f'{geo}.json', {})
        self.linked = {}
        self.errors = 0
        try:
            self.linked = parse_trends_rss(client.get(BASE + '/trending/rss', params={'geo': geo}))
        except Exception as exc:
            self.errors += 1
            print(f'News RSS {geo}: {type(exc).__name__}', flush=True)

    def get(self, keyword):
        identity = key(keyword)
        now = utcnow().timestamp()
        cached = self.cache.get(identity)
        if identity in self.linked:
            articles = self.linked[identity]
        elif cached and now - cached['timestamp'] < 6 * 3600:
            return cached['articles']
        elif self.calls >= self.budget or time.monotonic() >= self.deadline or self.consecutive_errors >= 3:
            return cached['articles'] if cached else []
        else:
            self.calls += 1
            lang, locale, _ = GEOS[self.geo]
            try:
                xml = self.client.get('https://news.google.com/rss/search', params={'q': f'"{keyword}" when:7d', 'hl': lang, 'gl': self.geo, 'ceid': f'{self.geo}:{lang}'})
                articles = parse_news_rss(xml)
                self.consecutive_errors = 0
            except Exception as exc:
                self.errors += 1
                self.consecutive_errors += 1
                print(f'News fetch failed: {type(exc).__name__}', flush=True)
                return cached['articles'] if cached else []
        articles = [dict(a, fetched_at=stamp()) for a in articles]
        self.cache[identity] = {'timestamp': now, 'articles': articles}
        return articles

    def save(self):
        cutoff = utcnow().timestamp() - 7 * 86400
        self.cache = {k: v for k, v in self.cache.items() if v['timestamp'] >= cutoff}
        write_json(self.root / 'news-cache' / f'{self.geo}.json', self.cache)
