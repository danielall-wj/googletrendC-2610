#!/usr/bin/env python3
"""Daily KR/JP/US Top 5 and three news articles per keyword at 19:00 KST, then the news-word analysis.
Secrets never appear in files under public/."""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
import requests
from common import ROOT, load_json, write_json, stamp, utcnow

KST = timezone(timedelta(hours=9))
STATE = Path(__file__).resolve().parents[1] / 'state' / 'discord.json'


def load_env(path):
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name, value = line.split('=', 1)
                os.environ.setdefault(name.strip(), value.strip().strip('\"\''))


def md(text, limit=75):
    return re.sub(r'([\\`*_{}\[\]()<>~|])', r'\\\1', str(text).replace('\n', ' ')[:limit])


def select_slot(now):
    if 19 <= now.astimezone(KST).hour < 22:
        return 'daily'
    raise ValueError('Scheduled delivery is outside the KST 19:00 delivery window')


def delivery_date(now, slot):
    return now.astimezone(KST).date().isoformat()


COUNTRIES = {'KR': '🇰🇷 한국', 'JP': '🇯🇵 일본', 'US': '🇺🇸 미국'}


def build_payloads(doc, new_keywords, dashboard=''):
    geo = doc.get('geo')
    if geo not in COUNTRIES:
        raise ValueError('Unsupported country')
    rows = sorted(doc['trends'], key=lambda t: t['volume'], reverse=True)[:5]
    collected = datetime.fromisoformat(doc['fetched_at'].replace('Z', '+00:00')).astimezone(KST)
    messages, embeds = [], []
    base = f"📈 **구글 트렌드 by 코덱스 · {collected:%Y-%m-%d} · {COUNTRIES[geo]} · 최근 24시간 TOP 5**\n수집 {collected:%m/%d %H:%M} KST · 검색어별 뉴스 최대 3건"
    if dashboard and urlparse(dashboard).scheme in ('https', 'http'):
        base += f'\n{dashboard}'
    def flush():
        if embeds:
            messages.append({'username':'구글 트렌드 by 코덱스', 'content': base, 'allowed_mentions': {'parse': []}, 'embeds': list(embeds)})
            embeds.clear()
    for rank, trend in enumerate(rows, 1):
        title = f"{rank}. {trend['keyword']}"[:230] + (' 🆕' if trend['keyword'] in new_keywords else '')
        lines = [f"검색량 **{trend['volume']:,}+** · 증가율 **{trend['increase_pct']:,}%**"]
        articles = trend.get('news', [])[:3]
        for article in articles:
            url = article.get('url', '')
            label = md(article.get('title', ''), 100)
            source = md(article.get('source', ''), 35)
            if urlparse(url).scheme in ('https', 'http') and len(url) <= 950:
                lines.append(f'· [{label}]({url}) — {source}')
            else:
                lines.append(f'· {label} — {source} (원문 URL은 첨부 JSON 참고)')
        if len(articles) < 3:
            lines.append(f'수집된 관련 기사 {len(articles)}건 / 최대 3건')
        description = '\n'.join(lines)
        embed = {'title': title, 'url': 'https://www.google.com/search?q=' + quote(trend['keyword']),
                 'description': description, 'color': {'KR':0x23724D,'JP':0xD25A66,'US':0x377AC2}[geo]}
        size = len(title) + len(description)
        if embeds and sum(len(e['title'])+len(e['description']) for e in embeds) + size > 5700:
            flush()
        embeds.append(embed)
    flush()
    if not messages:
        messages.append({'username':'구글 트렌드 by 코덱스', 'content':base+'\n현재 검색어가 없습니다.', 'allowed_mentions':{'parse':[]}})
    return messages


FLAGS = {'KR': '🇰🇷', 'JP': '🇯🇵', 'US': '🇺🇸'}


def change_mark(word):
    if word.get('surge'):
        return ' 🔥'
    if word.get('is_new'):
        return ' 🆕'
    change = word.get('rank_change')
    return f' ▲{change}' if change and change > 0 else f' ▼{-change}' if change and change < 0 else ''


def build_analysis_payloads(analysis, weekly=None, dashboard='', top=10):
    """News-word TOP10 per country, surging words, shared keywords and concepts; weekly TOP10 on Sundays."""
    if not analysis or not analysis.get('geos'):
        return []
    link = f'\n{dashboard}?view=analysis' if dashboard and urlparse(dashboard).scheme in ('https', 'http') else ''
    content = f"📊 **구글 트렌드 by 코덱스 · {analysis['date']} · 뉴스 단어 분석**\n최근 24시간 트렌드에 붙은 기사 제목의 단어 · 숫자는 그 단어가 나온 기사 수{link}"
    colors = {'KR': 0x23724D, 'JP': 0xD25A66, 'US': 0x377AC2}
    embeds = []
    for geo in COUNTRIES:
        g = analysis['geos'].get(geo)
        if not g:
            continue
        lines = [f"{i}. **{md(w['word'], 40)}** {w['count']}건{change_mark(w)}" for i, w in enumerate(g['words'][:top], 1)]
        shares = ' · '.join(f"{c['name']} {c['pct']}%" for c in g['categories'][:3])
        lines.append(f"분야: {shares}\n기사 {g['articles']}건 · 분석기 {g['analyzer']}")
        embeds.append({'title': f'{COUNTRIES[geo]} · 뉴스 단어 TOP {top}', 'description': '\n'.join(lines)[:4000], 'color': colors[geo]})
    surging = [f"{FLAGS[geo]} {md(w['word'], 40)} {w['count']}건" for geo in COUNTRIES for w in analysis['geos'].get(geo, {}).get('words', []) if w.get('surge')]
    if surging:
        embeds.append({'title': '🔥 급부상 단어', 'description': '\n'.join(surging[:15]), 'color': 0xE07A1F})
    extra = [f"{''.join(FLAGS[g] for g in c['geos'])} {md(c['keyword'], 60)}" for c in analysis.get('common', [])[:8]]
    concepts = [f"{md(c['label'], 30)}: " + ' · '.join(f"{FLAGS[g]} {n}" for g, n in c['counts'].items()) for c in analysis.get('concepts', []) if sum(1 for n in c['counts'].values() if n) >= 2][:8]
    if extra or concepts:
        parts = (['**국가 공통 검색어**', *extra] if extra else []) + (['**같은 개념 · 나라별 기사 수**', *concepts] if concepts else [])
        embeds.append({'title': '🌏 3개국 비교', 'description': '\n'.join(parts)[:4000], 'color': 0x6B7280})
    messages = [{'username': '구글 트렌드 by 코덱스', 'content': content, 'allowed_mentions': {'parse': []}, 'embeds': embeds}]
    if weekly and weekly.get('geos'):
        week = []
        for geo in COUNTRIES:
            words = weekly['geos'].get(geo, {}).get('words', [])[:top]
            if words:
                week.append({'title': f'{COUNTRIES[geo]} · 주간 TOP {top}', 'color': colors[geo],
                             'description': '\n'.join(f"{i}. **{md(w['word'], 40)}** {w['count']}건 · {w['days']}일" for i, w in enumerate(words, 1))})
        if week:
            messages.append({'username': '구글 트렌드 by 코덱스', 'allowed_mentions': {'parse': []}, 'embeds': week,
                             'content': f"🗓️ **주간 뉴스 단어 · {weekly['start_date']} ~ {weekly['end_date']}** ({weekly['days']}일 합산)"})
    return messages


def build_csv(doc):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['검색어', '검색량 하한', '증가율', '시작 UTC', '뉴스 URL'])
    for t in doc['trends']:
        values = [t['keyword'], t['volume'], t['increase_pct'], t['started_at'], ' | '.join(n['url'] for n in t.get('news', []))]
        writer.writerow(["'" + v if isinstance(v, str) and re.match(r'^\s*[=+@\-]', v) else v for v in values])
    return ('\ufeff' + output.getvalue()).encode()


def send(hook, payload, doc=None, attach=True):
    if not re.fullmatch(r'https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+', hook):
        raise ValueError('Invalid Discord webhook URL')
    files = {} if not doc else {'files[0]': (f"trends-{doc['geo']}-24h.csv", build_csv(doc), 'text/csv'),
             'files[1]': (f"trends-{doc['geo']}-24h.json", json.dumps(doc, ensure_ascii=False).encode(), 'application/json')}
    if not attach or sum(len(v[1]) for v in files.values()) > 7 * 1024 * 1024:
        files = {}
    for attempt in range(3):
        try:
            response = requests.post(hook, headers={'User-Agent':'googletrend-c-2610/1.0'}, params={'wait': 'true'}, data={'payload_json': json.dumps(payload, ensure_ascii=False)}, files=files or None, timeout=30)
        except requests.RequestException:
            # A timeout may already have delivered a message. Avoid automatic duplicate sends.
            raise RuntimeError('Discord connection failed; delivery status is uncertain') from None
        if response.status_code == 429 and attempt < 2:
            delay = float(response.json().get('retry_after', 3))
            if delay > 60:
                raise RuntimeError('Discord rate limit; retry later')
            time.sleep(delay)
            continue
        if response.status_code not in (200, 204):
            raise RuntimeError(f'Discord returned HTTP {response.status_code}')
        return response.json().get('id') if response.content else None
    raise RuntimeError('Discord rate limit')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--slot', choices=['auto', 'daily', 'test'], default='auto')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--output', type=Path, default=ROOT)
    p.add_argument('--state', type=Path, default=STATE)
    args = p.parse_args()
    load_env(Path(__file__).resolve().parents[1] / '.env.local')
    now = utcnow()
    slot = select_slot(now) if args.slot == 'auto' else args.slot
    day = delivery_date(now, slot)
    identity = f'{day}:all:{slot}'
    records = load_json(args.state, {'deliveries': {}})
    receipt = records['deliveries'].get(identity)
    if receipt and receipt.get('completed'):
        print('Already delivered this slot; skipped.')
        return 0
    if receipt and receipt.get('uncertain'):
        raise RuntimeError('Previous transmission result uncertain; check Discord before retrying')
    if not receipt:
        docs, payloads = {}, []
        errors = load_json(args.output / 'index.json', {}).get('errors', [])
        for geo in COUNTRIES:
            doc = load_json(args.output / f'latest/{geo}/24.json')
            if not doc or doc.get('geo') != geo:
                raise RuntimeError(f'No valid {geo} 24h snapshot')
            collected = datetime.fromisoformat(doc['fetched_at'].replace('Z', '+00:00'))
            if now - collected > timedelta(hours=3) or collected - now > timedelta(minutes=5):
                raise RuntimeError(f'{geo} dataset stale or future; digest skipped')
            if any(e.get('source') == 'trending' and e.get('geo') == geo and e.get('hours') == 24 for e in errors):
                raise RuntimeError(f'{geo} collection failed; digest skipped')
            docs[geo] = doc
            previous = [v for k,v in records['deliveries'].items() if k.endswith(':all:daily') and k[:10] < day and v.get('completed')]
            baseline = max(previous, key=lambda v:v['sent_at']).get('keywords', {}).get(geo) if previous else None
            new = {t['keyword'] for t in doc['trends']} - set(baseline) if baseline is not None else set()
            for i, payload in enumerate(build_payloads(doc, new, os.environ.get('DASHBOARD_URL', ''))):
                payloads.append({'geo':geo, 'payload':payload, 'attach':i == 0})
        analysis = load_json(args.output / f'analysis/{day}.json')
        if analysis and now - datetime.fromisoformat(analysis['generated_at'].replace('Z', '+00:00')) <= timedelta(hours=6):
            weekly = load_json(args.output / f'analysis/weekly/{day}.json')
            for payload in build_analysis_payloads(analysis, weekly, os.environ.get('DASHBOARD_URL', '')):
                payloads.append({'geo':None, 'payload':payload, 'attach':False})
        else:
            print('News-word analysis missing or stale; analysis message skipped.')
        receipt = {'created_at':stamp(now), 'docs':docs, 'parts':payloads, 'sent_parts':[], 'completed':False}
    if args.dry_run:
        print(json.dumps(receipt['parts'], ensure_ascii=False, indent=2))
        return 0
    hook = os.environ.get('DISCORD_WEBHOOK_URL', '')
    if not hook:
        raise RuntimeError('DISCORD_WEBHOOK_URL is not configured')
    records['deliveries'][identity] = receipt
    write_json(args.state, records)
    for i, part in enumerate(receipt['parts']):
        if i in receipt['sent_parts']:
            continue
        # Persist an in-flight marker before sending: crashes must not trigger blind duplicates.
        receipt['uncertain'] = i + 1
        write_json(args.state, records)
        send(hook, part['payload'], receipt['docs'].get(part['geo']), attach=part['attach'])
        receipt['sent_parts'].append(i)
        receipt.pop('uncertain', None)
        write_json(args.state, records)
    receipt.update(completed=True, sent_at=stamp(now), keywords={geo:[t['keyword'] for t in doc['trends']] for geo,doc in receipt['docs'].items()})
    receipt.pop('docs', None)
    receipt.pop('parts', None)
    cutoff = (now - timedelta(days=14)).date().isoformat()
    records['deliveries'] = {k:v for k,v in records['deliveries'].items() if k[:10] >= cutoff}
    write_json(args.state, records)
    print(f'Discord {slot} delivered successfully.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        # No exception representations containing secret-bearing request URLs.
        print(f'Discord failed: {str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__}', file=sys.stderr)
        sys.exit(1)
