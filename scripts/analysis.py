#!/usr/bin/env python3
"""News-title word analysis per country from the latest 24h trends, without new Google requests.

Each word counts once per article. Korean nouns come from Kiwi (kiwipiepy) and Japanese nouns from
MeCab/UniDic (fugashi + unidic-lite). Without those packages a rule-based tokenizer is used instead;
the `analyzer` field records which one ran. English uses stopwords plus adjacent-word phrases.
Output: public/data/analysis/YYYY-MM-DD.json (KST date), weekly/YYYY-MM-DD.json, index.json.
"""
import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from common import ROOT, GEOS, load_json, write_json, stamp, utcnow
from categories import CATEGORIES

KST = timezone(timedelta(hours=9))
CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'news-analysis.json'
TOP_N = 20
COUNT_KEEP = 200  # per-day counts kept for the 7-day series and surge comparison
SERIES_DAYS = 7

KO_JOSA = sorted('''은 는 이 가 을 를 의 에 에서 에게 께 께서 한테 으로 로 으로서 로서 와 과 도 만 까지 부터 마저 조차 이나 나
이랑 랑 하고 처럼 보다 밖에 이며 며 이고 고 이다 였다 했다 한다 하는 했던 하며 해 한 할 된 되는 됐다 에도 에는 에서도 에서는
으로는 로는 이라 라 이라는 라는 이란 인 들 들이 들은 들을 들의 적 적인 적으로 씨 측'''.split(), key=len, reverse=True)
KO_STOP = set('''기자 뉴스 사진 영상 속보 단독 종합 포토 오늘 내일 어제 이번 지난 올해 지금 현재 관련 대한 위해 통해 대해 따라 위한 이후
이전 가운데 그리고 하지만 그러나 또한 경우 정도 이상 이하 등 및 것 수 때 중 더 또 첫 전 후 년 월 일 시 분 명 개 건 곳 만에 억 조
한국 추진 실시 공개 발표 진행 예정 확인 기록 결과 모습 사실 시작 소식 이유 상황 화제 근황 공식 최초 최고 최대 국내 전국 우리 대표 뭐길래 무슨
어떤 이런 그런 누구 결국 직접 다시 함께 모두 계속 바로 가장 매우 많이 크게 새로운 가능 필요 한편 동안 내년 충격 관심 선정 눈길
깜짝 발칵 경악 출신 고백 언급 심경 반응 주목 등장 포착 제공 대박 무려 결정 참석 조선 일보 신문 데일리 일간 투데이 미디어 닷컴
연합뉴스 뉴시스 뉴스1 머니투데이 조선일보 중앙일보 동아일보 한겨레 경향신문 한국일보 매일경제 한국경제 서울경제 헤럴드경제 아시아경제
이데일리 파이낸셜뉴스 노컷뉴스 오마이뉴스 프레시안 데일리안 뉴데일리 스포츠조선 스포츠동아 스포츠서울 스포츠경향 일간스포츠
마이데일리 엑스포츠뉴스 텐아시아 스타뉴스 조이뉴스24 디스패치 지디넷코리아 전자신문 블로터 조선비즈 비즈니스포스트'''.split())
EN_STOP = set('''a an the and or but if of to in on at by for with from as is are was were be been being it its this that these
those he she they we you i his her their our your my me him them us who whom whose which what when where why how not no yes do
does did done has have had will would can could should may might must just than then so too very about after before over under
into out up down off again more most some such only own same other another any each all both few new news says said say vs via
amid per here there now today tonight week year years day days time live update updates video watch report reports photos photo
get got gets make makes made one two first last next back big top game games season win wins won loss lose lost against free know
need see look looks set sets ahead final odds pick picks prediction predictions preview recap highlights score scores stream
streaming channel tickets breaking official schedule check announce announced kbs mbc sbs jtbc ytn mbn osen nhk yahoo msn'''.split())
JP_STOP = set('''情報 発表 速報 写真 動画 記事 今日 明日 昨日 今回 現在 予想 予定 開始 公開 発生 関連 全国 ニュース 年ぶり 年目 年前 画像
枚目 ネット テレビ オリコン スポニチ 日刊スポーツ サンスポ デイリー スポーツ報知 東スポ 共同通信 時事通信 毎日新聞 朝日新聞 読売新聞
産経新聞 日経 日本 配信 視聴 実施 所属 映像 方法 無料 今季 ヤフー ライブドア エキサイト モデルプレス 女性自身 文春 新潮 番組 放送 話題 結果 最新 発売 開催'''.split())
SPLIT = re.compile(r'[^\w가-힣]+')
JP_RUN = re.compile(r'[一-鿿々]{2,}|[゠-ヿー]{2,}|[A-Za-z][A-Za-z0-9.+-]{2,}')

try:
    from kiwipiepy import Kiwi
except ImportError:  # rule-based fallback
    Kiwi = None
try:
    import fugashi
except ImportError:
    fugashi = None
_mecab = None


def load_config(path=CONFIG):
    config = load_json(path, {}) or {}
    return {'stopwords': {geo: set(words) for geo, words in config.get('stopwords', {}).items()},
            'concepts': config.get('concepts', [])}


def clean_title(title, source=''):
    """Google News search titles end with ' - Publisher', sometimes doubled (' - 조선비즈 - Chosunbiz')."""
    head, sep, tail = title.rpartition(' - ')
    if not (sep and head and source and tail.strip().lower() == source.strip().lower()):
        return title.strip()
    inner, sep, tail = head.rpartition(' - ')
    return (inner if sep and inner and len(tail.strip()) <= 20 and ' ' not in tail.strip() else head).strip()


def strip_josa(token, vocab):
    """Drop a trailing particle only when the bare form appears on its own that day (머니투데이 ≠ 머니투데)."""
    for josa in KO_JOSA:
        if len(token) > len(josa) + 1 and token.endswith(josa) and token[:-len(josa)] in vocab:
            return token[:-len(josa)]
    return token


UNITS = {'cm', 'mm', 'km', 'kg', 'mg', 'ml', 'kb', 'mb', 'gb', 'tb'}


def latin_word(token, stop):
    word = token.lower()
    return word if len(word) >= 2 and word not in EN_STOP and word not in UNITS and word not in stop else None


def tokens_ko(title, vocab=frozenset(), stop=frozenset()):
    out = []
    for raw in SPLIT.split(title):
        if not raw or raw.isdigit():
            continue
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', raw):
            if word := latin_word(raw, stop):
                out.append(word)
            continue
        word = strip_josa(raw, vocab)
        if len(word) >= 2 and word not in KO_STOP and word not in stop and not (re.search(r'\d', word) and not re.search(r'[가-힣]{2}', word)):
            out.append(word)
    return out


def tokens_en(title, vocab=frozenset(), stop=frozenset()):
    """Unigrams plus adjacent-word phrases (red sox, wild card); rare phrases are dropped in word_top."""
    words = []
    for raw in re.findall(r"[A-Za-z][A-Za-z'.-]*[A-Za-z]|[A-Za-z]", title):
        word = raw.lower().strip("'.-").replace('.', '')
        words.append(word[:-2] if word.endswith("'s") else word)
    ignore = EN_STOP | stop
    out = [w for w in words if len(w) >= 3 and w not in ignore]
    out += [f'{a} {b}' for a, b in zip(words, words[1:]) if a not in ignore and b not in ignore and len(a) >= 2 and len(b) >= 2]
    return out


def tokens_ja(title, vocab=frozenset(), stop=frozenset()):
    out = []
    for match in JP_RUN.findall(title):
        word = match.lower() if match[0].isascii() else match
        if word not in JP_STOP and word not in EN_STOP and word not in stop:
            out.append(word)
    return out


KATAKANA = re.compile(r'[゠-ヿー]+')


def merge_nouns(pieces, contiguous=False):
    """Join touching noun pieces: a one-character fragment always (허+경+환 -> 허경환), touching katakana
    words (ポスト+シーズン -> ポストシーズン), and every touching pair when contiguous (Korean 아시안+게임 ->
    아시안게임, since a space-free run of nouns is one compound)."""
    out = []
    for form, start, end in pieces:
        katakana = out and KATAKANA.fullmatch(form) and KATAKANA.fullmatch(out[-1][0])
        if out and out[-1][2] == start and (contiguous or katakana or len(form) == 1 or len(out[-1][0]) == 1):
            out[-1][0] += form
            out[-1][2] = end
        else:
            out.append([form, start, end])
    return [form for form, _, _ in out]


def kiwi_tokenizer(doc, stop):
    kiwi = Kiwi()
    names = {t['keyword'] for t in doc.get('trends', [])} | {r for t in doc.get('trends', []) for r in t.get('related', [])}
    for name in names | {n.replace(' ', '') for n in names}:
        if 2 <= len(name) <= 20 and ' ' not in name and re.search(r'[가-힣]', name):
            kiwi.add_user_word(name, 'NNP', 3.0)  # today's trend names should not be split
    def tokenize(title, vocab=frozenset(), _=None):
        pieces = [(t.form, t.start, t.start + t.len) for t in kiwi.tokenize(title) if t.tag in ('NNG', 'NNP', 'SL', 'SH')]
        out = []
        for word in merge_nouns(pieces, contiguous=True):
            if re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', word):
                if latin := latin_word(word, stop):
                    out.append(latin)
            elif len(word) >= 2 and word not in KO_STOP and word not in stop:
                out.append(word)
        return out
    return tokenize


def tokens_ja_mecab(title, vocab=frozenset(), stop=frozenset()):
    global _mecab
    _mecab = _mecab or fugashi.Tagger()
    pieces, position = [], 0
    for word in _mecab(title):
        start = title.find(word.surface, position)
        start = position if start < 0 else start
        position = start + len(word.surface)
        feature = word.feature
        if feature.pos1 == '名詞' and feature.pos2 not in ('数詞', '助数詞', '非自立可能'):
            pieces.append((word.surface, start, position))
        elif feature.pos1 == '接尾辞' and feature.pos2 != '助数詞' and pieces and pieces[-1][2] == start:
            form, begin, _ = pieces.pop()  # a noun suffix belongs to its noun (戦力+外 -> 戦力外)
            pieces.append((form + word.surface, begin, position))
    out = []
    for word in merge_nouns(pieces):
        word = word.lower() if word.isascii() else word
        if len(word) >= 2 and not re.search(r'[0-9０-９]', word) and word not in JP_STOP and word not in EN_STOP and word not in stop:
            out.append(word)
    return out


def analyzer_name(geo):
    return {'KR': 'kiwi' if Kiwi else 'rules', 'JP': 'mecab' if fugashi else 'rules'}.get(geo, 'rules')


def tokenizer_for(geo, doc, stop=frozenset()):
    if geo == 'KR':
        return kiwi_tokenizer(doc, stop) if Kiwi else tokens_ko
    if geo == 'JP':
        return tokens_ja_mecab if fugashi else tokens_ja
    return tokens_en


def collect_articles(doc):
    articles = {}
    for trend in doc.get('trends', []):
        for news in trend.get('news', []):
            if not news.get('title'):
                continue
            article = articles.setdefault(news.get('url') or news['title'], {
                'title': clean_title(news['title'], news.get('source', '')), 'source': news.get('source', ''),
                'url': news.get('url'), 'trends': set()})
            article['trends'].add(trend['keyword'])
    return articles


def word_top(doc, geo, config=None, top_n=TOP_N):
    stop = (config or load_config())['stopwords'].get(geo, set())
    stop = {w.lower() for w in stop} | stop
    tokenize = tokenizer_for(geo, doc, stop)
    articles = collect_articles(doc)
    volume = {t['keyword']: t['volume'] for t in doc.get('trends', [])}
    sources = {a['source'].lower() for a in articles.values() if a['source']}
    vocab = {raw for a in articles.values() for raw in SPLIT.split(a['title']) if raw}
    counts, trends, examples = Counter(), defaultdict(set), defaultdict(list)
    for article in articles.values():
        for word in {w for w in tokenize(article['title'], vocab, stop) if w.lower() not in sources}:
            counts[word] += 1
            trends[word] |= article['trends']
            if len(examples[word]) < 3:
                examples[word].append({k: article[k] for k in ('title', 'source', 'url')})
    if geo not in ('KR', 'JP'):
        for plural in [w for w in counts if w.endswith('s') and w[:-1] in counts]:  # playoffs -> playoff
            counts[plural[:-1]] += counts.pop(plural)
            trends[plural[:-1]] |= trends.pop(plural)
            examples[plural[:-1]] = (examples[plural[:-1]] + examples.pop(plural))[:3]
    for phrase in [w for w in counts if ' ' in w and counts[w] < 3]:
        del counts[phrase]
    # Drop a shorter word mostly used inside longer ones (sox -> red sox + white sox) so a story is listed once.
    def inside(long, short):
        return short in long.split() if ' ' in long else (short in long and not short.isascii())
    for short in sorted(counts, key=len):
        longer = [w for w in counts if len(w) > len(short) and counts[w] >= 3 and inside(w, short)]
        if longer and sum(counts[w] for w in longer) >= 0.6 * counts[short]:
            del counts[short]
    ranked = sorted(counts, key=lambda w: (-counts[w], -len(trends[w]), w))
    return {'analyzer': analyzer_name(geo), 'articles': len(articles),
            'counts': {w: counts[w] for w in ranked[:COUNT_KEEP]},
            'words': [{'word': w, 'count': counts[w], 'volume': sum(volume.get(k, 0) for k in trends[w]),
                       'trends': sorted(trends[w], key=lambda k: -volume.get(k, 0))[:6], 'articles': examples[w]}
                      for w in ranked[:top_n]]}


def category_share(doc):
    counts = Counter((t.get('categories') or [11])[0] for t in doc.get('trends', []))
    total = sum(counts.values()) or 1
    return [{'id': cid, 'name': CATEGORIES.get(cid, f'기타 ({cid})'), 'count': n, 'pct': round(n * 100 / total)}
            for cid, n in counts.most_common()]


def normalize(keyword):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', keyword)).strip().lower()


def common_keywords(docs, limit=15):
    seen = {}
    for geo, doc in docs.items():
        for trend in doc.get('trends', []):
            entry = seen.setdefault(normalize(trend['keyword']), {'keyword': trend['keyword'], 'geos': [], 'volume': 0})
            if geo not in entry['geos']:
                entry['geos'].append(geo)
                entry['volume'] += trend['volume']
    shared = [e for e in seen.values() if len(e['geos']) >= 2]
    return sorted(shared, key=lambda e: (-len(e['geos']), -e['volume']))[:limit]


def alias_pattern(alias):
    if re.fullmatch(r'[A-Za-z0-9 .\-]+', alias):
        return re.compile(r'(?<![A-Za-z0-9])' + re.escape(alias) + r'(?![A-Za-z0-9])', re.I)
    return re.compile(re.escape(alias))


def concept_counts(docs, config):
    """Articles per country mentioning the same concept under any local alias (AI·인공지능·人工知能)."""
    titles = {geo: [a['title'] for a in collect_articles(doc).values()] for geo, doc in docs.items()}
    out = []
    for concept in config['concepts']:
        counts = {}
        for geo, items in titles.items():
            patterns = [alias_pattern(a) for a in concept.get('aliases', {}).get(geo, [])]
            counts[geo] = sum(1 for title in items if any(p.search(title) for p in patterns))
        if sum(counts.values()):
            out.append({'id': concept['id'], 'label': concept['label'], 'counts': counts, 'total': sum(counts.values())})
    return sorted(out, key=lambda c: (-sum(1 for n in c['counts'].values() if n), -c['total'], c['id']))


def shift(day, days):
    return (Date.fromisoformat(day) + timedelta(days=days)).isoformat()


def daily(root, geos, day, config=None):
    config = config or load_config()
    docs = {geo: doc for geo in geos if (doc := load_json(root / 'latest' / geo / '24.json')) and doc.get('trends')}
    history = {d: load_json(root / 'analysis' / f'{d}.json', {}) or {} for d in (shift(day, -i) for i in range(1, SERIES_DAYS))}
    previous = history[shift(day, -1)]
    out = {'schema_version': 1, 'date': day, 'generated_at': stamp(), 'hours': 24, 'geos': {},
           'common': common_keywords(docs), 'concepts': concept_counts(docs, config)}
    for geo, doc in docs.items():
        result = word_top(doc, geo, config)
        before = previous.get('geos', {}).get(geo, {})
        before_rank = {w['word']: i for i, w in enumerate(before.get('words', []))}
        before_counts = before.get('counts', {})
        for i, word in enumerate(result['words']):
            w = word['word']
            word['rank_change'] = before_rank[w] - i if w in before_rank else None
            word['is_new'] = bool(before) and w not in before_rank
            # surging: newly in the TOP20 and at least double yesterday's article count
            word['surge'] = word['is_new'] and word['count'] >= 3 and word['count'] >= 2 * max(1, before_counts.get(w, 0))
            word['series'] = [history[shift(day, -k)].get('geos', {}).get(geo, {}).get('counts', {}).get(w, 0)
                              if history[shift(day, -k)] else None for k in range(SERIES_DAYS - 1, 0, -1)] + [word['count']]
        out['geos'][geo] = {'fetched_at': doc['fetched_at'], 'trends': len(doc['trends']), 'articles': result['articles'],
                            'analyzer': result['analyzer'], 'has_prev': bool(before), 'words': result['words'],
                            'counts': result['counts'], 'categories': category_share(doc)}
    return out


def weekly(root, end_day, days=SERIES_DAYS):
    files = [f for i in range(days) if (f := load_json(root / 'analysis' / f'{shift(end_day, -i)}.json'))]
    if not files:
        return None
    out = {'schema_version': 1, 'end_date': end_day, 'start_date': shift(end_day, -(days - 1)), 'days': len(files),
           'generated_at': stamp(), 'geos': {}}
    for geo in sorted({g for f in files for g in f['geos']}):
        total, seen, trends = Counter(), Counter(), defaultdict(set)
        for f in files:
            for word, n in f['geos'].get(geo, {}).get('counts', {}).items():
                total[word] += n
            for w in f['geos'].get(geo, {}).get('words', []):
                seen[w['word']] += 1
                trends[w['word']] |= set(w['trends'])
        ranked = sorted(total, key=lambda w: (-total[w], -seen[w], w))[:TOP_N]
        out['geos'][geo] = {'words': [{'word': w, 'count': total[w], 'days': seen[w], 'trends': sorted(trends[w])[:6]} for w in ranked]}
    return out


def write_index(root):
    folder = root / 'analysis'
    write_json(folder / 'index.json', {'schema_version': 1, 'updated_at': stamp(),
               'days': sorted(p.stem for p in folder.glob('????-??-??.json')),
               'weekly': sorted(p.stem for p in (folder / 'weekly').glob('????-??-??.json'))})


def run(root=ROOT, geos=tuple(GEOS), day=None, with_weekly=None, now=None):
    now = now or utcnow()
    day = day or now.astimezone(KST).date().isoformat()
    doc = daily(root, list(geos), day)
    if not doc['geos']:
        raise RuntimeError('No 24h datasets to analyze')
    write_json(root / 'analysis' / f'{day}.json', doc)
    if with_weekly is None:
        with_weekly = Date.fromisoformat(day).weekday() == 6  # Sunday KST
    if with_weekly and (rollup := weekly(root, day)):
        write_json(root / 'analysis' / 'weekly' / f'{day}.json', rollup)
    write_index(root)
    print('analysis ' + day + ': ' + ', '.join(f"{g} {v['articles']} articles ({v['analyzer']})" for g, v in doc['geos'].items()))
    return doc


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--geo', default=','.join(GEOS))
    parser.add_argument('--date', help='KST date label (default: today)')
    parser.add_argument('--weekly', action=argparse.BooleanOptionalAction, default=None, help='7-day rollup (default: Sundays)')
    parser.add_argument('--data', type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.data, [g.strip().upper() for g in args.geo.split(',') if g.strip()], args.date, args.weekly)
