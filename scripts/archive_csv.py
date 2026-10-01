#!/usr/bin/env python3
"""Archive the latest collected datasets at 18:00 KST, without collecting again."""
import argparse
import csv
import io
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from common import ROOT, GEOS, HOURS, load_json, write_json, stamp, utcnow

KST = timezone(timedelta(hours=9))
DEST = Path(__file__).resolve().parents[1] / 'archives' / 'csv'


def csv_bytes(header, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    for row in rows:
        cells = []
        for value in row:
            text = str(value) if value is not None else ''
            if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
                text = "'" + text
            cells.append(text)
        writer.writerow(cells)
    return ('\ufeff' + output.getvalue()).encode('utf-8')


def export_daily(root=ROOT, destination=DEST, now=None, geos=tuple(GEOS)):
    now = now or utcnow()
    day = now.astimezone(KST).date().isoformat()
    target = destination / day
    if target.exists():
        print(f'CSV archive already exists: {day}; preserving it.')
        return target
    destination.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix='.pending-', dir=destination))
    manifest = {'archive_date_kst': day, 'archived_at': stamp(now), 'files': []}
    errors = load_json(root / 'index.json', {}).get('errors', [])
    try:
        for geo in geos:
            for hours in HOURS:
                doc = load_json(root / 'latest' / geo / f'{hours}.json')
                if not doc or doc.get('geo') != geo or doc.get('hours') != hours:
                    raise ValueError(f'Missing or invalid dataset: {geo}/{hours}')
                age = now - datetime.fromisoformat(doc['fetched_at'].replace('Z', '+00:00'))
                if age > timedelta(hours=3) or age < timedelta(minutes=-5):
                    raise ValueError(f'Stale or future dataset: {geo}/{hours}')
                if any(e.get('source') == 'trending' and e.get('geo') == geo and e.get('hours') == hours for e in errors):
                    raise ValueError(f'Collection failed: {geo}/{hours}')
                name = f'{geo}-{hours}h.csv'
                rows = [[geo, hours, doc['fetched_at'], t['keyword'], t['volume'], t['increase_pct'], t['started_at'], t['ended_at'], ' / '.join(map(str,t['categories'])), ' / '.join(t['related']), ' | '.join(n['url'] for n in t.get('news', []))] for t in doc['trends']]
                (staged / name).write_bytes(csv_bytes(['국가','원본 기간(시간)','수집 UTC','검색어','검색량 하한','증가율 %','시작 UTC','종료 UTC','카테고리 ID','관련 검색어','뉴스 URL'], rows))
                manifest['files'].append({'file': name, 'source_fetched_at': doc['fetched_at'], 'count': len(rows)})
            for period in ('7d', '1m', '3m', '12m'):
                doc = load_json(root / 'explore' / geo / f'{period}.json')
                if not doc:
                    manifest.setdefault('skipped_explore', []).append(f'{geo}/{period}: missing')
                    continue
                age = now - datetime.fromisoformat(doc['fetched_at'].replace('Z', '+00:00'))
                if doc.get('geo') != geo or age > timedelta(hours=36) or age < timedelta(minutes=-5):
                    manifest.setdefault('skipped_explore', []).append(f'{geo}/{period}: stale or invalid')
                    continue
                name = f'{geo}-explore-{period}.csv'
                rows = [[geo,period,doc['fetched_at'],kind,t['query'],t['value'],t.get('label'),t.get('is_breakout'),t.get('rank_change'),doc.get('compare'),doc.get('comparison_status')] for kind in ('top','rising') for t in doc[kind]]
                (staged / name).write_bytes(csv_bytes(['국가','기간','수집 UTC','유형','검색어','원본 값','표시값','급등','순위 변동','비교 기간','비교 상태'],rows))
                manifest['files'].append({'file':name,'source_fetched_at':doc['fetched_at'],'count':len(rows)})
        write_json(staged / 'manifest.json', manifest)
        staged.rename(target)
    except Exception:
        shutil.rmtree(staged)
        raise
    print(f'Archived {len(manifest["files"])} CSV files: {day}')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT)
    parser.add_argument('--destination', type=Path, default=DEST)
    args = parser.parse_args()
    export_daily(args.data, args.destination)
