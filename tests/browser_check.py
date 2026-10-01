"""Run with a local server: python tests/browser_check.py (Chrome or Playwright Chromium)."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path('test-results');OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True,args=['--disable-gpu'])
    page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:3000',wait_until='networkidle')
    page.wait_for_selector('#rows tr')
    assert page.locator('#rows tr').count()>50
    page.screenshot(path=str(OUT/'dashboard-desktop.png'),full_page=True)
    page.locator('#rows .keyword button').first.click()
    page.wait_for_selector('#detail[open]')
    page.wait_for_timeout(300)
    assert page.locator('#detail-title').inner_text()
    assert page.locator('#detail-body .links a').count()==3
    page.screenshot(path=str(OUT/'news-detail.png'))
    page.locator('#detail-close').click()
    page.locator('#search').fill('zzzz-no-result')
    assert page.locator('#empty').is_visible()
    page.locator('#search').fill('')
    with page.expect_download() as result:
        page.locator('#export-csv').click()
    download=result.value
    download.save_as(str(OUT/'export.csv'))
    assert (OUT/'export.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    with page.expect_download() as result:
        page.locator('#export-json').click()
    result.value.save_as(str(OUT/'export.json'))
    assert len(json.loads((OUT/'export.json').read_text())['items'])>0
    page.locator('#history-toggle').click()
    page.wait_for_function("document.querySelector('#status').textContent.includes('과거 기록')")
    page.locator('#back-live').click()
    page.wait_for_function("document.querySelector('#status').textContent.includes('수집')")
    page.get_by_role('button',name='12시간',exact=True).click()
    page.wait_for_function("document.querySelector('#warning').textContent.includes('24시간 원본')")
    assert page.locator('#rows tr').count()>0
    page.locator('#geo').select_option('US')
    page.wait_for_function("document.querySelector('#region-label').textContent.includes('미국') && !document.querySelector('#refresh').disabled")
    assert page.locator('#rows tr').count()>0
    page.locator('#geo').select_option('KR')
    page.wait_for_function("!document.querySelector('#refresh').disabled")
    page.locator('[data-view=explore]').click()
    page.wait_for_function("document.querySelector('#heading').textContent.includes('사람들이') && !document.querySelector('#refresh').disabled")
    assert page.locator('#rows tr').count()==25
    page.locator('[data-type=rising]').click()
    assert '증가율' in page.locator('#columns').inner_text()
    page.get_by_role('button',name='지난 1년',exact=True).click()
    page.wait_for_function("!document.querySelector('#refresh').disabled")
    assert page.locator('#rows tr').count()>0
    page.screenshot(path=str(OUT/'explore-desktop.png'),full_page=True)
    page.locator('#theme').click()
    page.screenshot(path=str(OUT/'dark-mode.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page horizontal overflow'
    page.goto('http://127.0.0.1:3000/?geo=KR&hours=24#open='+__import__('urllib.parse',fromlist=['quote']).quote('지게차'),wait_until='networkidle')
    # The fixture keyword may rotate out; verify hash opens with the current first keyword.
    first=page.locator('#rows .keyword button').first.inner_text()
    page.goto('http://127.0.0.1:3000/?geo=KR&hours=24#open='+__import__('urllib.parse',fromlist=['quote']).quote(first),wait_until='networkidle')
    assert page.locator('#detail').is_visible()
    assert not errors, errors
    browser.close()
print('Browser checks passed: real data, detail, search, CSV/JSON, history, countries, Explore, theme, mobile, deep links.')
