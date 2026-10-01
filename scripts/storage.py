import gzip
import json
from datetime import timedelta
from common import load_json, write_json, utcnow, stamp, GEOS, HOURS
from categories import CATEGORIES


def append_jsonl(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text() if path.exists() else ''
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(old + json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n')
    temp.replace(path)


def save_trends(root, geo, hours, trends, source='batchexecute'):
    path = root / 'latest' / geo / f'{hours}.json'
    previous = load_json(path)
    when = stamp()
    doc = {'schema_version': 1, 'geo': geo, 'hours': hours, 'fetched_at': when, 'count': len(trends),
           'source': source, 'source_url': f'https://trends.google.co.kr/trending?geo={geo}&hours={hours}',
           'previous_fetched_at': previous['fetched_at'] if previous else None,
           'prev_keywords': [t['keyword'] for t in previous['trends']] if previous else [], 'trends': trends}
    compact = [[t['keyword'], t['volume'], t['increase_pct'], t['categories'], t['started_at'], t['ended_at']] for t in trends]
    # Write history first, latest remains untouched if persisting the snapshot fails.
    append_jsonl(root / 'history' / geo / f'{when[:10]}.jsonl', {'fetched_at': when, 'hours': hours, 'trends': compact})
    write_json(path, doc)
    return doc


def archive_history(root, now=None):
    cutoff = ((now or utcnow()) - timedelta(days=90)).date().isoformat()
    for geo in GEOS:
        folder = root / 'history' / geo
        if not folder.exists():
            continue
        groups = {}
        for file in folder.glob('????-??-??.jsonl'):
            if file.stem < cutoff:
                groups.setdefault(file.stem[:7], []).append(file)
        for month, files in groups.items():
            archive = folder / f'{month}.jsonl.gz'
            previous = gzip.decompress(archive.read_bytes()).decode() if archive.exists() else ''
            rows = previous.splitlines() + [line for file in sorted(files) for line in file.read_text().splitlines()]
            # Idempotent if a prior run stopped after archive replacement but before removal.
            unique = { (json.loads(line)['fetched_at'], json.loads(line)['hours']): line for line in rows if line }
            temp = archive.with_suffix('.gz.tmp')
            temp.write_bytes(gzip.compress(('\n'.join(unique[k] for k in sorted(unique)) + '\n').encode(), mtime=0))
            temp.replace(archive)
            for file in files:
                file.unlink()


def build_index(root, errors=None):
    geos = [geo for geo in GEOS if (root / 'latest' / geo).exists() or (root / 'explore' / geo).exists()]
    history_days, history_archives, available = {}, {}, {}
    for geo in geos:
        folder = root / 'history' / geo
        history_days[geo] = sorted(p.stem for p in folder.glob('????-??-??.jsonl'))
        history_archives[geo] = sorted(p.name for p in folder.glob('????-??.jsonl.gz'))
        available[geo] = [h for h in HOURS if (root / 'latest' / geo / f'{h}.json').exists()]
    explore = {geo: [p.stem for p in sorted((root / 'explore' / geo).glob('*.json'))] for geo in geos}
    write_json(root / 'index.json', {'schema_version': 1, 'geos': geos, 'hours': list(HOURS), 'available': available,
               'updated_at': stamp(), 'history_days': history_days, 'history_archives': history_archives,
               'explore': explore, 'categories': CATEGORIES, 'errors': errors or []})
