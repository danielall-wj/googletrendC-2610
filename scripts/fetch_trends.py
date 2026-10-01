#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
from common import Client, ROOT, GEOS, HOURS
from google_trends import fetch_trends, parse_html
from news import NewsProvider
from storage import save_trends, archive_history, build_index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--geo', default='KR,US,JP')
    parser.add_argument('--hours', default='4,24,48,168')
    parser.add_argument('--output', type=Path, default=ROOT)
    parser.add_argument('--news-budget', type=int, default=80, help='Maximum new keyword news requests per country per run')
    parser.add_argument('--no-news', action='store_true')
    args = parser.parse_args()
    geos, hours = args.geo.split(','), [int(h) for h in args.hours.split(',')]
    if any(g not in GEOS for g in geos) or any(h not in HOURS for h in hours):
        parser.error('Unsupported geo or hours')
    root, errors = args.output, []
    for geo in geos:
        client = Client(delay=.35)
        news = None if args.no_news else NewsProvider(client, root, geo, args.news_budget)
        results = {}
        for h in hours:
            print(f'Fetching {geo} {h}h', flush=True)
            try:
                source = 'batchexecute'
                try:
                    rows, _ = fetch_trends(client, geo, h)
                except Exception:
                    # Full-period fallback; an RSS subset must not overwrite a full list.
                    html = client.get('https://trends.google.co.kr/trending', params={'geo': geo, 'hours': h, 'hl': GEOS[geo][0]})
                    rows = parse_html(html, geo)
                    source = 'page-json'
                results[h] = (rows, source)
            except Exception as exc:
                errors.append({'source': 'trending', 'geo': geo, 'hours': h, 'error': type(exc).__name__})
                print(f'FAILED {geo} {h}: {type(exc).__name__}', file=sys.stderr, flush=True)
        # Prioritize high volume keywords across windows; one news query serves all windows.
        all_rows = sorted([t for rows, _ in results.values() for t in rows], key=lambda t: t['volume'], reverse=True)
        if 24 in results:
            all_rows = sorted(results[24][0], key=lambda t:t['volume'], reverse=True)[:5] + all_rows
        articles = {}
        for trend in all_rows:
            if trend['keyword'] not in articles:
                articles[trend['keyword']] = news.get(trend['keyword']) if news else []
        for h, (rows, source) in results.items():
            for trend in rows:
                trend['news'] = articles[trend['keyword']]
            save_trends(root, geo, h, rows, source)
            print(f'Saved {geo}/{h}: {len(rows)} trends', flush=True)
        if news:
            news.save()
            if news.errors:
                errors.append({'source': 'news', 'geo': geo, 'error': f'{news.errors} requests failed'})
    archive_history(root)
    build_index(root, errors)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
