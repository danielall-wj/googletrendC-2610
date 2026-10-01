import json
import re
from datetime import datetime, timezone
from common import BASE, GEOS, decode_json


def normalize_rows(rows, geo):
    if not isinstance(rows, list):
        raise ValueError('Trend list missing')
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, list) or len(row) < 11 or not isinstance(row[0], str) or row[2] != geo:
            raise ValueError('Trend row schema changed')
        if not isinstance(row[3], list) or not row[3] or not isinstance(row[3][0], (int, float)):
            raise ValueError('Invalid trend timestamp')
        if not isinstance(row[6], (int, float)) or not isinstance(row[8], (int, float)) or not isinstance(row[9], list) or not isinstance(row[10], list):
            raise ValueError('Invalid trend metrics')
        if row[4] is not None and (not isinstance(row[4], list) or not row[4] or not isinstance(row[4][0], (int, float))):
            raise ValueError('Invalid end timestamp')
        if row[0] in seen:
            continue
        seen.add(row[0])
        iso = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')
        result.append({'keyword': row[0], 'started_at': iso(row[3][0]), 'ended_at': iso(row[4][0]) if row[4] else None,
                       'volume': row[6], 'increase_pct': row[8], 'related': [s for s in row[9] if isinstance(s, str)],
                       'categories': [n for n in row[10] if isinstance(n, int)], 'news': []})
    return result


def parse_rpc(text, geo):
    # batchexecute is a sequence of JSON frames, optionally preceded by byte lengths.
    for line in text.splitlines():
        if not line.startswith('['):
            continue
        try:
            frames = json.loads(line)
        except json.JSONDecodeError:
            continue
        for frame in frames:
            if isinstance(frame, list) and len(frame) > 2 and frame[0] == 'wrb.fr' and frame[1] == 'i0OFE' and frame[2]:
                payload = json.loads(frame[2])
                if not isinstance(payload, list) or len(payload) < 2:
                    raise ValueError('RPC payload changed')
                return normalize_rows(payload[1], geo)
    raise ValueError('i0OFE data not found')


def parse_html(text, geo):
    match = re.search(r"AF_initDataCallback\(\{key:\s*'ds:0',\s*hash:\s*'[^']*',\s*data:([\s\S]*?),\s*sideChannel:", text)
    if not match:
        raise ValueError('Embedded trends data not found')
    payload = json.loads(match.group(1))
    return normalize_rows(payload[1], geo)


def fetch_trends(client, geo, hours):
    lang = GEOS[geo][0]
    request = [[["i0OFE", json.dumps([None, None, geo, 0, lang, hours, 1]), None, "generic"]]]
    raw = client.post(BASE + '/_/TrendsUi/data/batchexecute', params={'rpcids': 'i0OFE', 'hl': lang}, data={'f.req': json.dumps(request)})
    return parse_rpc(raw, geo), raw
