import gzip
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from common import decode_json, load_json, write_json
from google_trends import normalize_rows, parse_rpc, parse_html
from news import parse_trends_rss, parse_news_rss, safe_url
from explore import parse_ranked, previous_range, shift_months
from storage import save_trends, archive_history, build_index
from notify_discord import build_payloads, build_csv, select_slot, delivery_date

FIXTURES = Path(__file__).parent / 'fixtures'
ROW = ['테스트', None, 'KR', [1790746200], None, None, 50000, None, 1000, ['테스트', '관련'], [9], [], '테스트']


class ParseTests(unittest.TestCase):
    def test_xssi(self):
        self.assertEqual(decode_json(")]}'\n{\"a\":1}"), {'a': 1})

    def test_rpc_frames(self):
        payload = json.dumps([None, [ROW]])
        raw = ")]}'\n\n321\n" + json.dumps([['wrb.fr','i0OFE',payload,None]])
        self.assertEqual(parse_rpc(raw, 'KR')[0]['keyword'], '테스트')
        with self.assertRaises(ValueError): parse_rpc(raw, 'US')
        with self.assertRaises(ValueError): parse_rpc('captcha page', 'KR')

    def test_schema_rejects_incomplete_rows(self):
        for bad in [[], ['x'], ROW[:6], ROW[:3]+[None]+ROW[4:]]:
            with self.assertRaises(ValueError): normalize_rows([bad], 'KR')

    def test_end_and_duplicates(self):
        row = ROW.copy();row[4] = [1790769000]
        result = normalize_rows([row,row], 'KR')
        self.assertEqual(len(result),1)
        self.assertIsNotNone(result[0]['ended_at'])

    def test_real_html_fixture(self):
        result = parse_html((FIXTURES/'trends.html').read_text(), 'KR')
        self.assertGreater(len(result), 0)
        self.assertTrue(all(t['volume'] >= 0 for t in result))

    def test_real_rss_fixture(self):
        result = parse_trends_rss((FIXTURES/'trends-rss.xml').read_text())
        self.assertTrue(result)
        article = next(iter(result.values()))[0]
        self.assertTrue(article['url'].startswith('https://'))
        self.assertIsNone(article['published_at']) # trend pubDate is NOT article date

    def test_news_rss_sort_dedupe_and_url(self):
        xml = '''<rss><channel><item><title>Older</title><link>https://a.test/1</link><pubDate>Wed, 30 Sep 2026 07:00:00 GMT</pubDate><source>A</source></item><item><title>Newer</title><link>https://a.test/2</link><pubDate>Wed, 30 Sep 2026 08:00:00 GMT</pubDate></item><item><title>Bad</title><link>javascript:alert(1)</link></item></channel></rss>'''
        result = parse_news_rss(xml)
        self.assertEqual([a['title'] for a in result], ['Newer','Older'])
        self.assertIsNone(safe_url('javascript:alert(1)'))

    def test_explore_empty_and_breakout(self):
        top,rising=parse_ranked({'default':{'rankedList':[{'rankedKeyword':[{'query':'a','value':100,'formattedValue':'100'}]},{'rankedKeyword':[{'query':'b','value':250000,'formattedValue':'급등'}]}]}})
        self.assertEqual(top[0]['rank'],1)
        self.assertTrue(rising[0]['is_breakout'])
        self.assertEqual(parse_ranked({'default':{'rankedList':[]}}),[[],[]])
        with self.assertRaises(ValueError): parse_ranked({'error':'blocked'})

    def test_calendar_boundaries(self):
        self.assertEqual(shift_months(date(2024,3,31),-1),date(2024,2,29))
        self.assertEqual(previous_range('7d',date(2026,10,1)),'2026-09-17 2026-09-23')
        self.assertEqual(previous_range('1m',date(2026,10,1)),'2026-08-02 2026-08-31')


class StorageTests(unittest.TestCase):
    def test_first_baseline_then_previous_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rows=normalize_rows([ROW],'KR')
            first=save_trends(root,'KR',24,rows)
            self.assertIsNone(first['previous_fetched_at'])
            second=save_trends(root,'KR',24,[])
            self.assertEqual(second['prev_keywords'],['테스트'])
            self.assertEqual(second['count'],0)
            build_index(root)
            index=load_json(root/'index.json')
            self.assertEqual(index['available']['KR'],[24])
            self.assertTrue(index['history_days']['KR'])

    def test_compression_and_incremental_month(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'history/KR';folder.mkdir(parents=True)
            row={'fetched_at':'2026-01-01T00:00:00Z','hours':24,'trends':[]}
            (folder/'2026-01-01.jsonl').write_text(json.dumps(row)+'\n')
            now=datetime(2026,10,1,tzinfo=timezone.utc)
            archive_history(root,now)
            archive=folder/'2026-01.jsonl.gz'
            self.assertFalse((folder/'2026-01-01.jsonl').exists())
            self.assertEqual(json.loads(gzip.decompress(archive.read_bytes())),row)
            (folder/'2026-01-01.jsonl').write_text(json.dumps(row)+'\n')
            archive_history(root,now)
            self.assertEqual(len(gzip.decompress(archive.read_bytes()).splitlines()),1)


class DiscordTests(unittest.TestCase):
    def test_all_three_countries_top5_three_news_and_limits(self):
        for geo in ('KR','JP','US'):
            rows=normalize_rows([ROW],'KR') * 8
            rows=[dict(t,keyword=f'query{i}',news=[{'title':f'article{j}','source':'news','url':'https://example.com/'+str(j)+'x'*900} for j in range(3)]) for i,t in enumerate(rows)]
            messages=build_payloads({'geo':geo,'fetched_at':'2026-10-01T09:00:00Z','trends':rows},set())
            cards=[e for m in messages for e in m.get('embeds',[])]
            self.assertEqual(len(cards),5)
            self.assertTrue(all(e['description'].count('· [')==3 for e in cards))
            for m in messages:
                self.assertIn('구글 트렌드 by 코덱스',m['content'])
                self.assertEqual(m['allowed_mentions'],{'parse':[]})
                self.assertLessEqual(sum(len(e['title'])+len(e['description']) for e in m['embeds']),6000)

    def test_kst_schedule(self):
        self.assertEqual(select_slot(datetime(2026,10,1,10,tzinfo=timezone.utc)),'daily')
        for hour in (3,9,13):
            with self.assertRaises(ValueError):select_slot(datetime(2026,10,1,hour,tzinfo=timezone.utc))

    def test_delivery_state_skips_sent_and_preserves_uncertainty(self):
        import notify_discord as notify
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state.json'
            write_json(state,{'deliveries':{'2026-10-01:all:daily':{'completed':True}}})
            with patch.object(sys,'argv',['notify','--slot','daily','--output',str(root),'--state',str(state)]),patch.object(notify,'utcnow',return_value=datetime(2026,10,1,10,tzinfo=timezone.utc)),patch.object(notify,'load_env'),patch.object(notify,'send') as send:
                self.assertEqual(notify.main(),0)
                send.assert_not_called()
                write_json(state,{'deliveries':{'2026-10-01:all:daily':{'completed':False,'uncertain':1}}})
                with self.assertRaises(RuntimeError):notify.main()
                send.assert_not_called()


class ArchiveTests(unittest.TestCase):
    def seed(self,root):
        for hours in (4,24,48,168):
            write_json(root/'latest/JP'/f'{hours}.json',{'geo':'JP','hours':hours,'fetched_at':'2026-10-01T08:07:00Z','trends':normalize_rows([ROW],'KR')})

    def test_archive_is_dated_kst_and_idempotent(self):
        from archive_csv import export_daily, csv_bytes
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.seed(root)
            now=datetime(2026,10,1,9,tzinfo=timezone.utc)
            result=export_daily(root,root/'archive',now,('JP',))
            self.assertEqual(result.name,'2026-10-01')
            self.assertEqual(len(list(result.glob('*.csv'))),4)
            self.assertTrue((result/'JP-24h.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
            before=(result/'manifest.json').read_bytes()
            export_daily(root,root/'archive',now,('JP',))
            self.assertEqual((result/'manifest.json').read_bytes(),before)
            self.assertIn("'=SUM",csv_bytes(['x'],[['=SUM(1)']]).decode())

    def test_stale_archive_does_not_leave_partial_result(self):
        from archive_csv import export_daily
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.seed(root)
            with self.assertRaises(ValueError):export_daily(root,root/'archive',datetime(2026,10,2,9,tzinfo=timezone.utc),('JP',))
            self.assertEqual(list((root/'archive').iterdir()),[])


if __name__ == '__main__': unittest.main()
