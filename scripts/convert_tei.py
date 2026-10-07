#!/usr/bin/env python3
"""hatoma.tei (TEI Lex-0) の先頭 N 見出しを、サイト用の JSON に変換する。

使い方（プロジェクト直下で）:
    python3 scripts/convert_tei.py                 # 先頭100見出し -> data/hatoma_sample100.json
    python3 scripts/convert_tei.py --limit 0       # 全見出し（0 = 無制限）

例文の音声: Hatoma_example_20220921.txt（WdID・SID・例文）と照合し、各例文に音声ファイル名
            （htm_<SID>.mp3）を付ける。--examples で別のファイルを指定、--no-examples で省略。

必要なもの: pip install lxml pykakasi
注意: 重複した xml:id があると lxml が途中で止まるため、全件変換は --limit 0 のとき
      recover=True で続行する（README.md の「変換の方針」を参照）。
"""
import argparse, sys, csv, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from example_norm import norm_ex, ntr, html_plain
import re, json
from lxml import etree
import pykakasi
T='{http://www.tei-c.org/ns/1.0}'
XID='{http://www.w3.org/XML/1998/namespace}id'
kks=pykakasi.kakasi()
POS={'名':'名詞','他動':'他動詞','自動':'自動詞','連':'連語','感':'感動詞','副':'副詞','語素':'語素','助動':'助動詞','補動':'補助動詞','接尾':'接尾辞','文':'文',
     '形':'形容詞','代':'代名詞','固':'固有名詞','連体':'連体詞','終助':'終助詞','格助':'格助詞','副助':'副助詞','係助':'係助詞','接助':'接続助詞',
     '助数':'助数詞','接頭':'接頭辞','形動':'形容動詞'}   # 略号のうち意味が確かなものだけ展開（成・接・助・並立・間助・慣・句・接続 などは原文のまま）
DOM={'動':'動物','植':'植物','地':'地名','海底地名':'海底地名'}
def norm(s): return re.sub(r'\s+',' ',s or '').strip()
def txt(e): return norm(''.join(e.itertext()))
def esc(s): return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def def_html(d):
    out=esc(d.text or '')
    for c in d:
        if etree.QName(c).localname=='ruby':
            rb=c.find(T+'rb'); rt=c.find(T+'rt')
            out+='<ruby>%s<rt>%s</rt></ruby>'%(esc(txt(rb)),esc(txt(rt)))
        else: out+=esc(txt(c))
        out+=esc(c.tail or '')
    return norm(out)
def balanced(s):
    return s.count('(')==s.count(')') and s.count('（')==s.count('）')
def clean_tr(s):
    s=norm(s)
    s=re.sub(r'[。.]+$','',s)
    if s.startswith('(') and s.endswith(')') and balanced(s[1:-1]): s=s[1:-1]
    return s
def hira(s):
    return ''.join(x['hira'] for x in kks.convert(s))
def gloss_of(plain):
    s=re.sub(r'^\((?:[^()]{1,6})\)','',plain).strip()
    g=s.split('。')[0].strip()
    return g
def entry_pos(e):
    g=e.find(T+'gramGrp/'+T+'gram')
    return norm(''.join(g.itertext())) if g is not None else None
def parse_senses(e, sub_id, inherit_pos, out):
    for s in e.findall(T+'sense'):
        g=s.find(T+'gramGrp/'+T+'gram')
        pos=norm(''.join(g.itertext())) if g is not None else inherit_pos
        u=s.find(T+'usg')
        dom=txt(u) if u is not None else None
        d=s.find(T+'def')
        dh=def_html(d) if d is not None else ''
        plain=txt(d) if d is not None else ''
        plain=re.sub(r'\s+','',plain) if False else plain
        ex=[]; notes=[]
        for c in s.findall(T+'cit'):
            if c.get('type')!='example': continue
            q=c.find(T+'quote'); ip=c.find(T+'pron')
            tr=c.find(T+'cit/'+T+'quote')
            note=c.find(T+'note')
            ex.append({'t':txt(q),'ipa':txt(ip) if ip is not None else '','tr':clean_tr(def_html(tr)) if tr is not None else '',
                       'song':q.get('type')=='song','note':txt(note) if note is not None else ''})
        for n in s.findall(T+'note'): notes.append(txt(n))
        out.append({'sub':sub_id,'pos':POS.get(pos,pos),'posRaw':pos,'domain':DOM.get(dom,dom) if dom else None,
                    'def':dh,'gloss':gloss_of(plain),'ex':ex,'notes':notes})
def convert_entry(e):
    f=e.find(T+'form[@type="lemma"]')
    orth=txt(f.find(T+'orth'))
    acc=ipa=''
    for p in f.findall(T+'pron'):
        if p.get('notation')=='accent': acc=txt(p)
        elif p.get('notation')=='IPA': ipa=txt(p)
    m=f.find(T+'media')
    audio=m.get('url') if m is not None else None
    base_pos=entry_pos(e)
    senses=[]
    parse_senses(e,None,base_pos,senses)
    for h in e.findall(T+'entry'):
        parse_senses(h,h.get(XID),entry_pos(h) or base_pos,senses)
    # etc: collect unknown children for survey
    return {'id':e.get(XID),'orth':orth,'acc':acc,'ipa':ipa,'audio':audio,'senses':senses}

def attach_example_audio(entries, txt_path):
    """TEIの例文に、例文音声（htm_<SID>.mp3）を対応づける。

    同じ WdID の行のうち、次の条件で、まだ使っていない行を SID の小さい順に選ぶ。
      1. 例文の文字列（空白を除く）が一致する
      2. 1がなければ、IPAか訳文のどちらかが一致する（例文の表記ゆれ用）
    どちらにも当てはまらない例文には音声を付けない（誤った音声を付けるより安全なため）。
    戻り値: (付けられた数, 2で付けた数, 付けられなかった数)
    """
    norm = norm_ex
    by = collections.defaultdict(list)
    with open(txt_path, encoding='utf-8-sig') as f:
        r = csv.reader(f, delimiter='\t'); next(r)
        for x in r:
            if len(x) >= 7 and x[2].isdigit(): by[x[0]].append((int(x[2]), x[4], x[5], x[6]))
    n = loose = none = 0
    used_by = collections.defaultdict(set)      # 同じWdIDを持つ見出しの間で、使った行を共有する
    for e in entries:
        wid = e['id'].split('.')[1]
        cand = sorted(by.get(wid, []))
        used = used_by[wid]
        for s in e['senses']:
            for ex in s['ex']:
                hit = next((c for c in cand if c[0] not in used and norm(c[1]) == norm(ex['t'])), None)
                if hit is None:
                    ipa_ex = norm(ex.get('ipa', ''))
                    tr_ex = ntr(html_plain(ex.get('tr', '')))
                    hit = next((c for c in cand if c[0] not in used and (
                        (norm(c[2]) and norm(c[2]) == ipa_ex) or (ntr(c[3]) and ntr(c[3]) == tr_ex))), None)
                    loose += hit is not None
                if hit is None:
                    none += 1; continue
                used.add(hit[0]); n += 1
                ex['a'] = hit[0]
    return n, loose, none

def slim(entries):
    """サイト用に軽くする。既定値と、復元できる項目は省く。"""
    out = []
    for e in entries:
        num = e['id'].split('.')[1]
        o = {'id': e['id'], 'orth': e['orth'], 'acc': e['acc'], 'ipa': e['ipa']}
        a = e['audio']
        if not a or not re.fullmatch(r'htmvoc_\d+\.wav', a): o['na'] = 1          # 音声なし（'#' など）
        elif a != 'htmvoc_%s.wav' % num: o['audio'] = a                          # 番号が見出しIDと違うときだけ保存
        o['senses'] = []
        for s in e['senses']:
            so = {'pos': s['pos'] or '', 'def': s['def'], 'gloss': s['gloss'], 'glossKey': s['glossKey'], 'ex': []}
            if s['domain']: so['domain'] = s['domain']
            if s['sub']: so['sub'] = s['sub']
            if s['notes']: so['notes'] = s['notes']
            for x in s['ex']:
                xo = {'t': x['t']}
                for k in ('ipa', 'tr', 'a', 'note'):
                    if x.get(k): xo[k] = x[k]
                if x.get('song'): xo['song'] = 1
                so['ex'].append(xo)
            o['senses'].append(so)
        out.append(o)
    return out

def main():
    root=Path(__file__).resolve().parent.parent
    ap=argparse.ArgumentParser()
    ap.add_argument('--tei',default=root/'source'/'hatoma.tei')
    ap.add_argument('--limit',type=int,default=100,help='先頭の親見出しの数（0で全件）')
    ap.add_argument('--out',default=root/'data'/'hatoma_sample100.json')
    ap.add_argument('--examples',default=root/'source'/'Hatoma_example_20220921.txt')
    ap.add_argument('--no-examples',action='store_true')
    a=ap.parse_args()
    entries=[]
    for ev,el in etree.iterparse(str(a.tei),tag=T+'entry',recover=(a.limit==0)):
        if el.getparent() is not None and etree.QName(el.getparent()).localname=='entry': continue
        entries.append(convert_entry(el)); el.clear()
        if a.limit and len(entries)>=a.limit: break
    if not a.no_examples and Path(a.examples).exists():
        n,bo,no=attach_example_audio(entries,a.examples)
        print('例文音声:',n,'件を対応づけ（うちIPA・訳文の一致で補ったもの',bo,'件）、未対応',no,'件')
    for e in entries:
        for s in e['senses']:
            g=s['gloss']
            s['glossKey']=hira(re.sub(r'[(（].*?[)）]','',g)) if g else ''
    entries=slim(entries)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    json.dump(entries,open(a.out,'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
    print(len(entries),'見出し /',sum(len(e['senses']) for e in entries),'語義 /',sum(len(s['ex']) for e in entries for s in e['senses']),'例文 ->',a.out)
    print('音声なしの見出し:',sum(1 for e in entries if e.get('na')),'件 / 例文音声あり:',sum(1 for e in entries for s in e['senses'] for x in s['ex'] if 'a' in x),'件')

if __name__=='__main__': main()
