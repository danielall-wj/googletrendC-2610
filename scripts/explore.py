#!/usr/bin/env python3
"""Daily Explore Top/Rising, with a separate preceding-period rank comparison."""
import argparse
import calendar
import json
import sys
from datetime import timedelta
from pathlib import Path
from common import BASE, GEOS, ROOT, Client, decode_json, load_json, write_json, stamp, utcnow
from storage import append_jsonl, build_index

PERIODS = {'7d': ('now 7-d', 'now 7-d'), '1m': ('today 1-m', 'today 1-m'), '3m': ('today 3-m', 'today 3-m'), '12m': ('today 12-m', 'today 1-y')}


def shift_months(day, months):
    month = day.year * 12 + day.month - 1 + months
    year, index = divmod(month, 12)
    return day.replace(year=year, month=index + 1, day=min(day.day, calendar.monthrange(year, index + 1)[1]))


def previous_range(period, today):
    # Closed calendar-day range ending before the start of the rolling current range.
    # This is an approximate calendar-day comparison, not Google's percentage change.
    start = today - timedelta(days=7) if period == '7d' else shift_months(today, -{'1m': 1, '3m': 3, '12m': 12}[period])
    duration = today - start
    return f'{start - duration} {start - timedelta(days=1)}'


def parse_ranked(payload):
    ranked = payload.get('default', {}).get('rankedList')
    if not isinstance(ranked, list):
        raise ValueError('Explore rankedList missing')
    lists = []
    for index in range(2):
        values = ranked[index].get('rankedKeyword', []) if index < len(ranked) else []
        if not isinstance(values, list):
            raise ValueError('Explore rankedKeyword schema changed')
        rows = []
        for rank, entry in enumerate(values, 1):
            if not isinstance(entry.get('query'), str) or not isinstance(entry.get('value'), (int, float)):
                raise ValueError('Invalid Explore query')
            label = entry.get('formattedValue', str(entry['value']))
            breakout = index == 1 and (entry['value'] > 5000 or label.lower() in ('breakout', '급등'))
            rows.append({'query': entry['query'], 'value': entry['value'], 'label': label, 'rank': rank, 'is_breakout': breakout})
        lists.append(rows)
    return lists


def related(client, geo, time_range):
    request = {'comparisonItem': [{'geo': geo, 'time': time_range}], 'category': 0, 'property': ''}
    raw = client.get(BASE + '/trends/api/explore', params={'hl': GEOS[geo][0], 'tz': -540, 'req': json.dumps(request, separators=(',', ':'))})
    widgets = decode_json(raw).get('widgets', [])
    widget = next((w for w in widgets if w.get('id') == 'RELATED_QUERIES'), None)
    if not widget:
        raise ValueError('RELATED_QUERIES not provided')
    raw = client.get(BASE + '/trends/api/widgetdata/relatedsearches', params={'hl': GEOS[geo][0], 'tz': -540, 'req': json.dumps(widget['request'], separators=(',', ':')), 'token': widget['token']})
    return parse_ranked(decode_json(raw)), raw


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--geo', default='KR')
    p.add_argument('--periods', default='7d,1m,3m,12m')
    p.add_argument('--once-per-day', action='store_true')
    p.add_argument('--output', type=Path, default=ROOT)
    args = p.parse_args()
    geos, periods = args.geo.split(','), args.periods.split(',')
    if any(g not in GEOS for g in geos) or any(v not in PERIODS for v in periods):
        p.error('Unsupported country or period')
    errors = []
    for geo in geos:
        client = Client()
        initialized = False
        for period in periods:
            path = args.output / 'explore' / geo / f'{period}.json'
            existing = load_json(path)
            now = utcnow()
            if args.once_per_day and existing and existing['fetched_at'][:10] == now.date().isoformat() and existing.get('comparison_status') == 'ok':
                continue
            print(f'Explore {geo}/{period}', flush=True)
            try:
                if not initialized:
                    client.get(BASE + '/explore', params={'geo': geo, 'hl': GEOS[geo][0]})
                    initialized = True
                (top, rising), _ = related(client, geo, PERIODS[period][0])
                compare = previous_range(period, now.date())
                comparison_status = 'ok'
                try:
                    (previous, _), _raw = related(client, geo, compare)
                    ranks = {t['query']: t['rank'] for t in previous}
                    for item in top:
                        item['rank_change'] = ranks[item['query']] - item['rank'] if item['query'] in ranks else None
                        item['is_new'] = item['query'] not in ranks
                except Exception as exc:
                    comparison_status = 'unavailable'
                    for item in top:
                        item.update(rank_change=None, is_new=False)
                    errors.append({'source': 'explore-comparison', 'geo': geo, 'period': period, 'error': type(exc).__name__})
                doc = {'schema_version': 1, 'geo': geo, 'period': period, 'time': PERIODS[period][0], 'source': 'google-explore',
                       'source_url': f'{BASE}/explore?geo={geo}&date={PERIODS[period][1]}', 'fetched_at': stamp(now), 'compare': compare,
                       'comparison_status': comparison_status, 'comparison_method': 'preceding-calendar-days',
                       'category': 0, 'property': '', 'top': top, 'rising': rising}
                append_jsonl(args.output / 'history' / 'explore' / geo / f'{now:%Y-%m}.jsonl', doc)
                write_json(path, doc)
                print(f'Saved {geo}/{period}: top {len(top)}, rising {len(rising)}', flush=True)
            except Exception as exc:
                errors.append({'source': 'explore', 'geo': geo, 'period': period, 'error': type(exc).__name__})
                print(f'FAILED Explore {geo}/{period}: {type(exc).__name__}', file=sys.stderr, flush=True)
    old_errors = (load_json(args.output / 'index.json', {}) or {}).get('errors', [])
    build_index(args.output, [e for e in old_errors if not e['source'].startswith('explore')] + errors)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
