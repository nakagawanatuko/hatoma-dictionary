#!/usr/bin/env python3
"""site/template.html にデータを組み込み、ブラウザで開ける辞書ページを作る。

使い方（プロジェクト直下で）:
    python3 scripts/build_site.py                  # 全件版: docs/index.html + docs/data/hatoma-data.js
    python3 scripts/build_site.py --sample         # 試作版（先頭100見出し）を1枚のHTMLに埋め込んで site/hatoma-sample100.html

全件版はデータが大きい（約15MB）ため、HTMLとは別の JS ファイルにして読み込みます。
HTMLとデータを同じ相対位置（docs/ の中）に置いたままなら、ダブルクリックで開けます。
"""
import argparse, json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument('--sample', action='store_true', help='先頭100見出しを埋め込んだ1枚のHTMLを作る')
ap.add_argument('--template', default=root / 'site' / 'template.html')
ap.add_argument('--data', default=None)
ap.add_argument('--out', default=None)
a = ap.parse_args()

tpl = Path(a.template).read_text(encoding='utf-8')
head = ('<!doctype html>\n<html lang="ja"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n')
marker = '<script type="application/json" id="hatoma-data">__DATA__</script>'
assert marker in tpl, 'template.html にデータ埋め込みの目印がありません'

if a.sample:
    data_path = Path(a.data or root / 'data' / 'hatoma_sample100.json')
    out = Path(a.out or root / 'site' / 'hatoma-sample100.html')
    data = json.dumps(json.loads(data_path.read_text(encoding='utf-8')), ensure_ascii=False, separators=(',', ':'))
    data = data.replace('</', '<\\/').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    html = head + tpl.replace('__DATA__', data)
    out.write_text(html, encoding='utf-8')
    print(f'{len(html)//1024} KB -> {out}')
else:
    data_path = Path(a.data or root / 'data' / 'hatoma_full.json')
    out = Path(a.out or root / 'docs' / 'index.html')
    js_path = out.parent / 'data' / 'hatoma-data.js'
    js_path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(json.loads(data_path.read_text(encoding='utf-8')), ensure_ascii=False, separators=(',', ':'))
    data = data.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    js_path.write_text('window.HATOMA_DATA=' + data + ';\n', encoding='utf-8')
    html = head + tpl.replace(marker, '<script src="data/hatoma-data.js"></script>')
    out.write_text(html, encoding='utf-8')
    print(f'{len(html)//1024} KB -> {out}')
    print(f'{js_path.stat().st_size//1024} KB -> {js_path}')
