#!/usr/bin/env python3
"""サイトの簡易動作確認（Playwright）。検索・絞り込み・音声エラー表示・横スクロールの有無を確かめ、
スクリーンショットを site/screenshots/ に保存する。

    pip install playwright && playwright install chromium
    python3 scripts/smoke_test.py
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

root = Path(__file__).resolve().parent.parent
page_url = (root / 'docs' / 'index.html').as_uri()
shots = root / 'site' / 'screenshots'
shots.mkdir(exist_ok=True)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': 1360, 'height': 860})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(page_url)
        await pg.wait_for_selector('.row')
        print('表示中の行数（最初の一部）', await pg.locator('.row').count(), '/', (await pg.inner_text('#count')).replace('\n', ' '))
        for text, mode in [('アーサ', 'all'), ('あわ', 'all'), ('あわ', 'std'), ('アー', 'dia'), ('zzz', 'all')]:
            await pg.click(f'.modes button[data-mode="{mode}"]')
            await pg.fill('#q', text)
            await pg.wait_for_timeout(400)
            print(text, mode, (await pg.inner_text('#count')).replace('\n', ' '))
        await pg.fill('#q', '')
        await pg.click('.modes button[data-mode="all"]')
        await pg.screenshot(path=str(shots / 'desktop.png'))
        m = await b.new_page(viewport={'width': 390, 'height': 844})
        await m.goto(page_url)
        await m.wait_for_selector('.row')
        print('横スクロール', await m.evaluate('document.documentElement.scrollWidth>innerWidth'))
        await m.screenshot(path=str(shots / 'mobile.png'))
        print('JSエラー', errs)
        await b.close()

asyncio.run(main())
