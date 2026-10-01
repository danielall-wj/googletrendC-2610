import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analysis
from analysis import (clean_title, tokens_ko, tokens_en, tokens_ja, word_top, category_share, common_keywords,
                      concept_counts, load_config, daily, weekly, run)
from common import load_json, write_json


def doc(titles_by_keyword, volumes=None, geo='KR'):
    volumes = volumes or {}
    return {'geo': geo, 'hours': 24, 'fetched_at': '2026-10-01T01:00:00Z', 'trends': [
        {'keyword': k, 'volume': volumes.get(k, 1000), 'related': [], 'categories': [17 if i % 2 else 4],
         'news': [{'title': t, 'source': '연합뉴스', 'url': f'https://n.example/{k}/{j}'} for j, t in enumerate(titles)]}
        for i, (k, titles) in enumerate(titles_by_keyword.items())]}


class TokenizerTests(unittest.TestCase):
    def test_publisher_suffix_removed(self):
        self.assertEqual(clean_title('유연석 자격증 - 조선비즈 - Chosunbiz', 'Chosunbiz'), '유연석 자격증')
        self.assertEqual(clean_title('A - B 협상 타결', '연합뉴스'), 'A - B 협상 타결')
        self.assertEqual(clean_title('A - B 협상 타결 - 연합뉴스', '연합뉴스'), 'A - B 협상 타결')

    def test_korean_rules_strip_particle_only_when_bare_form_exists(self):
        vocab = {'손흥민', '손흥민이', '머니투데이'}
        self.assertEqual(tokens_ko('손흥민이 결승골', vocab), ['손흥민', '결승골'])
        self.assertNotIn('머니투데', tokens_ko('머니투데이가 전했다', {'머니투데이가'}))
        self.assertNotIn('cm', tokens_ko('키 180cm 몸무게 70 kg', set()))

    def test_english_phrases_and_japanese_runs(self):
        self.assertIn('red sox', tokens_en('Red Sox beat the Yankees'))
        self.assertNotIn('the', tokens_en('Red Sox beat the Yankees'))
        self.assertNotIn('u.s', tokens_en('U.S. Open final'))
        self.assertIn('カブス', tokens_ja('カブスが勝利'))

    @unittest.skipUnless(analysis.Kiwi, 'kiwipiepy not installed')
    def test_kiwi_keeps_trend_names_and_compounds(self):
        tokenize = analysis.tokenizer_for('KR', {'trends': [{'keyword': '허경환', 'related': ['아시안 게임']}]})
        words = tokenize('"허경환과 자주 잤다" 성현주 고백…아시안게임 금메달, 머니투데이가 전했다')
        self.assertTrue({'허경환', '아시안게임', '금메달'} <= set(words))
        self.assertNotIn('허', words)
        self.assertNotIn('머니투데이', words)

    @unittest.skipUnless(analysis.fugashi, 'fugashi not installed')
    def test_mecab_joins_katakana_and_suffix(self):
        words = analysis.tokens_ja_mecab('ポストシーズン進出、戦力外の選手 3人')
        self.assertIn('ポストシーズン', words)
        self.assertIn('戦力外', words)
        self.assertFalse(any(w.isdigit() for w in words))


class AnalysisTests(unittest.TestCase):
    def test_word_top_counts_articles_merges_phrases_and_plurals(self):
        d = doc({'red sox': ['Red Sox clinch playoff spot', 'Red Sox win again', 'Red Sox fans cheer'],
                 'white sox': ['White Sox lose', 'White Sox rebuild', 'White Sox playoffs trade'],
                 'trump': ['Trump speaks on Red Sox']}, {'red sox': 50000, 'trump': 200000}, 'US')
        words = {w['word']: w for w in word_top(d, 'US')['words']}
        self.assertEqual(words['red sox']['count'], 4)
        self.assertNotIn('sox', words)
        self.assertEqual(words['red sox']['trends'][0], 'trump')
        self.assertEqual(words['red sox']['volume'], 250000)
        self.assertEqual(words['playoff']['count'], 2)
        self.assertLessEqual(len(words['red sox']['articles']), 3)

    def test_category_common_and_concepts(self):
        shares = category_share(doc({'a': [], 'b': [], 'c': []}))
        self.assertEqual(sum(s['pct'] for s in shares), 100)
        common = common_keywords({'KR': doc({'WNBA Playoffs': []}), 'US': doc({'wnba  playoffs': []}), 'JP': doc({'台風': []})})
        self.assertEqual(common, [{'keyword': 'WNBA Playoffs', 'geos': ['KR', 'US'], 'volume': 2000}])
        config = {'stopwords': {}, 'concepts': [{'id': 'ai', 'label': '인공지능', 'aliases': {'KR': ['인공지능', 'AI'], 'US': ['AI'], 'JP': ['人工知能']}}]}
        concepts = concept_counts({'KR': doc({'x': ['AI 규제 발표', '인공지능 투자']}), 'US': doc({'y': ['Said hi', 'New AI chip']}, geo='US'),
                                   'JP': doc({'z': ['人工知能の未来']}, geo='JP')}, config)
        self.assertEqual(concepts[0]['counts'], {'KR': 2, 'US': 1, 'JP': 1})

    def test_config_file_is_valid(self):
        config = load_config()
        self.assertTrue(config['concepts'])
        self.assertIn('KR', config['stopwords'])

    def test_rank_change_surge_series_and_weekly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            days = [('2026-09-30', {'k': ['손흥민 골', '손흥민 도움', '토트넘 승리']}),
                    ('2026-10-01', {'k': ['토트넘 승리', '토트넘 패배', '손흥민 골', '아시안게임 개막', '아시안게임 금메달', '아시안게임 폐막', '아시안게임 일정']})]
            for day, titles in days:
                write_json(root / 'latest/KR/24.json', doc(titles))
                result = run(root, ['KR'], day, with_weekly=day == '2026-10-01')
            kr = result['geos']['KR']
            words = {w['word']: w for w in kr['words']}
            self.assertTrue(kr['has_prev'])
            self.assertGreater(words['토트넘']['rank_change'], 0)
            self.assertIsNone(words['아시안게임']['rank_change'])
            self.assertTrue(words['아시안게임']['surge'] and words['아시안게임']['is_new'])
            self.assertFalse(words['토트넘']['surge'])
            self.assertEqual(words['손흥민']['series'][-2:], [2, 1])
            self.assertIsNone(words['손흥민']['series'][0])
            rollup = load_json(root / 'analysis/weekly/2026-10-01.json')
            top = {w['word']: w for w in rollup['geos']['KR']['words']}
            self.assertEqual((rollup['days'], top['손흥민']['count'], top['손흥민']['days']), (2, 3, 2))
            self.assertEqual(load_json(root / 'analysis/index.json')['days'], ['2026-09-30', '2026-10-01'])
            self.assertEqual(weekly(root, '2026-08-01'), None)

    def test_missing_data_fails_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                run(Path(tmp), ['KR'], '2026-10-01')
            self.assertFalse((Path(tmp) / 'analysis').exists())
            self.assertEqual(daily(Path(tmp), ['KR'], '2026-10-01')['geos'], {})


if __name__ == '__main__':
    unittest.main()
