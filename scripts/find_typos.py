#!/usr/bin/env python3
"""hatoma.tei から誤植・不整合の候補を機械的に拾い、memo.txt に書き出す。

使い方（プロジェクト直下で）:
    python3 scripts/find_typos.py
    python3 scripts/find_typos.py --ninda-repo /path/to/NINDA   # GitHub上の音声の有無も調べる

あくまで候補の一覧です。誤植でないものも含まれます。確認の足がかりに使ってください。
必要なもの: pip install lxml
"""
import argparse, collections, csv, datetime, re, subprocess
from pathlib import Path
from lxml import etree

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from example_norm import norm_ex, ntr, plain_tei

T = '{http://www.tei-c.org/ns/1.0}'
XID = '{http://www.w3.org/XML/1998/namespace}id'
MARKS = '\u2e20\u2e22\u2e23'          # アクセント記号 ⸠ ⸢ ⸣
norm = norm_ex
txt = lambda e: re.sub(r'\s+', ' ', ''.join(e.itertext())).strip() if e is not None else ''

PAIRS = {'(': ')', '（': '）', '「': '」', '『': '』', '〈': '〉', '＜': '＞', '<': '>', '[': ']', '［': '］', '{': '}', '【': '】'}
CLOSERS = {v: k for k, v in PAIRS.items()}


def bracket_problem(s, pairs=PAIRS):
    """括弧の対応が取れていなければ (理由, 位置) を返す。取れていれば None。"""
    closers = {v: k for k, v in pairs.items()}
    stack = []
    for i, c in enumerate(s):
        if c in pairs:
            stack.append((c, i))
        elif c in closers:
            # 「1)」「2)」のような番号の閉じ括弧は対象にしない
            if not stack:
                if c == ')' and i > 0 and s[i - 1].isdigit():
                    continue
                return '閉じ括弧「%s」が余分' % c, i
            if pairs[stack[-1][0]] != c:
                return '括弧の種類が合わない（「%s」に対して「%s」）' % (stack[-1][0], c), i
            stack.pop()
    if stack:
        return '閉じ括弧「%s」が足りない' % pairs[stack[-1][0]], stack[-1][1]
    return None


def excerpt(s, pos, width=34):
    """問題の位置の前後を切り出す（長い語釈用）。"""
    if len(s) <= width * 2 + 10:
        return s
    a, b = max(0, pos - width), min(len(s), pos + width)
    return ('…' if a else '') + s[a:b] + ('…' if b < len(s) else '')


def hint(s, pos, reason):
    """「⸢」が「「」の誤りと思われる場合の注記。"""
    # 「⸢」の直後がカタカナでなければ、アクセント記号ではなく「「」の誤りの疑いが強い
    if '」' in reason and re.search(r'⸢[^ァ-ヶー\s\u2e20\u2e22\u2e23\[\]]', s[:pos]):
        return '  ※「⸢」が「「」の誤りの可能性'
    return ''


class Report:
    def __init__(self):
        self.items = collections.defaultdict(list)

    def add(self, cat, **kw):
        self.items[cat].append(kw)


def main():
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument('--tei', default=root / 'source' / 'hatoma.tei')
    ap.add_argument('--examples', default=root / 'source' / 'Hatoma_example_20220921.txt')
    ap.add_argument('--out', default=root / 'memo.txt')
    ap.add_argument('--ninda-repo', default=None, help='NINDA の git clone。指定すると音声ファイルの有無も調べる')
    a = ap.parse_args()

    R = Report()

    def check_markup(label, s, el, head):
        m = re.search(r'\{/?[A-Za-z!]*\}|\\ruby|[{}]', s)
        if m:
            R.add('記法', head=head, line=el.sourceline if el is not None else 0,
                  what='%s: 変換されなかった記法が残っている「%s」' % (label, m.group(0)), text=excerpt(s, m.start()))

    def check_br(label, s, el, head, pairs=PAIRS, extra=None):
        check_markup(label, s, el, head)
        p = bracket_problem(s, pairs)
        if extra and not p:
            p = (extra, 0)
        if p:
            R.add('括弧', head=head, line=el.sourceline if el is not None else 0,
                  what='%s: %s%s' % (label, p[0], hint(s, p[1], p[0])), text=excerpt(s, p[1]))
    ids = collections.defaultdict(list)          # xml:id -> [行番号]
    n_entries = n_senses = n_ex = 0

    # ---- 例文ファイル（WdID -> 行）----
    by = collections.defaultdict(list)
    ex_rows = {}
    if Path(a.examples).exists():
        with open(a.examples, encoding='utf-8-sig') as f:
            r = csv.reader(f, delimiter='\t'); next(r)
            for x in r:
                if len(x) >= 7 and x[2].isdigit():
                    row = (int(x[2]), x[4], x[5], x[6], x[1], x[0])
                    by[x[0]].append(row); ex_rows[row[0]] = row
    used_by = collections.defaultdict(set)
    matched_sids = set()

    for ev, top in etree.iterparse(str(a.tei), tag=T + 'entry', recover=True):
        if top.getparent() is not None and etree.QName(top.getparent()).localname == 'entry':
            continue
        n_entries += 1
        eid = top.get(XID)
        form = top.find(T + 'form[@type="lemma"]')
        orth = txt(form.find(T + 'orth')) if form is not None and form.find(T + 'orth') is not None else ''
        wid = eid.split('.')[1] if eid and '.' in eid else ''
        head = '%s %s' % (eid, orth)
        for el in top.iter():
            if isinstance(el.tag, str) and el.get(XID):
                ids[el.get(XID)].append(el.sourceline)

        # --- 見出し部分 ---
        if form is None:
            R.add('見出し', head=head, line=top.sourceline, what='見出し形（form）がない', text='')
        else:
            if not re.fullmatch(r'[ァ-ヶー・~〜ヴふ]+', re.sub('[%s]' % MARKS, '', orth)):
                R.add('見出し', head=head, line=form.sourceline, what='見出し語にカタカナ以外の文字がある', text=orth)
            ipas = [txt(p) for p in form.findall(T + 'pron') if p.get('notation') == 'IPA']
            accs = [txt(p) for p in form.findall(T + 'pron') if p.get('notation') == 'accent']
            if not ipas:
                R.add('見出し', head=head, line=form.sourceline, what='IPA表記がない', text='')
            for s in ipas:
                check_br('見出しのIPA', s, form, head, {'[': ']'}, None if (s.startswith('[') and s.endswith(']')) else '[ ] で囲まれていない')
            if not accs:
                R.add('見出し', head=head, line=form.sourceline, what='アクセント表記がない', text='')
            m = form.find(T + 'media')
            url = m.get('url') if m is not None else None
            if not url:
                R.add('音声', head=head, line=form.sourceline, what='見出し語の音声ファイルの指定がない', text='')
            elif not re.fullmatch(r'htmvoc_\d+\.wav', url):
                R.add('音声', head=head, line=m.sourceline, what='見出し語の音声ファイル名が想定と違う', text=url)
            elif url != 'htmvoc_%s.wav' % wid:
                R.add('音声', head=head, line=m.sourceline, what='音声ファイルの番号が見出しIDと違う', text=url)

        # --- 語義・例文 ---
        for en in top.iter(T + 'entry'):
            for s in en.findall(T + 'sense'):
                n_senses += 1
                d = s.find(T + 'def')
                dtxt = txt(d)
                sid_ = s.get(XID) or eid
                if not dtxt:
                    R.add('空欄', head=head, line=s.sourceline, what='語釈（def）が空', text=sid_)
                else:
                    check_br('語釈', dtxt, d, head)
                    if re.search(r'[。、]{2,}|[,.]{2,}', dtxt):
                        R.add('句読点', head=head, line=d.sourceline, what='語釈: 句読点が重なっている', text=dtxt)
                for nt in s.findall(T + 'note'):
                    check_br('語義の注', txt(nt), nt, head)
                for c in s.findall(T + 'cit'):
                    if c.get('type') != 'example':
                        continue
                    n_ex += 1
                    q = c.find(T + 'quote'); ip = c.find(T + 'pron'); tr = c.find(T + 'cit/' + T + 'quote')
                    qt, it, tt = txt(q), txt(ip), txt(tr)
                    tt_cmp = plain_tei(tr)
                    cid = c.get(XID) or sid_
                    if not qt:
                        R.add('空欄', head=head, line=c.sourceline, what='例文が空', text=cid)
                    else:
                        check_br('例文', qt, q, head)
                    if not it:
                        R.add('空欄', head=head, line=c.sourceline, what='例文のIPAがない', text=qt)
                    else:
                        check_br('例文のIPA', it, ip, head, {'[': ']'}, None if (it.startswith('[') and it.endswith(']')) else '[ ] で囲まれていない')
                    if not tt:
                        R.add('空欄', head=head, line=c.sourceline, what='例文の訳がない', text=qt)
                    else:
                        check_br('例文の訳', tt, tr, head)
                        if re.search(r'[。、]{2,}|[,.]{2,}', tt):
                            R.add('句読点', head=head, line=tr.sourceline, what='例文の訳: 句読点が重なっている', text=tt)
                    for nt in c.findall(T + 'note'):
                        check_br('例文の注', txt(nt), nt, head)

                    # --- 例文ファイルとの照合 ---
                    if by:
                        cand = sorted(by.get(wid, []))
                        used = used_by[wid]
                        hit = next((x for x in cand if x[0] not in used and norm(x[1]) == norm(qt)), None)
                        how = 'exact'
                        if hit is None:
                            hit = next((x for x in cand if x[0] not in used and (
                                (norm(x[2]) and norm(x[2]) == norm(it)) or (ntr(x[3]) and ntr(x[3]) == ntr(tt_cmp)))), None)
                            how = 'loose'
                        if hit is None:
                            R.add('例文音声', head=head, line=c.sourceline, what='例文ファイルに対応する行が見つからない（音声を付けていない）',
                                  text='TEI: %s / %s' % (qt, tt))
                        else:
                            used.add(hit[0]); matched_sids.add(hit[0])
                            if how == 'loose':
                                R.add('表記の不一致', head=head, line=q.sourceline, what='例文の表記がTEIと例文ファイルで違う（SID %d）' % hit[0],
                                      text='TEI: %s\n        例文ファイル: %s' % (qt, re.sub(r'\s+', ' ', hit[1].replace('　', ' ')).strip()))
                            else:
                                if ntr(hit[3]) != ntr(tt_cmp):
                                    R.add('表記の不一致', head=head, line=tr.sourceline if tr is not None else c.sourceline,
                                          what='例文の訳がTEIと例文ファイルで違う（SID %d）' % hit[0], text='TEI: %s\n        例文ファイル: %s' % (tt, hit[3]))
                                if norm(hit[2]) != norm(it):
                                    R.add('表記の不一致', head=head, line=ip.sourceline if ip is not None else c.sourceline,
                                          what='例文のIPAがTEIと例文ファイルで違う（SID %d）' % hit[0], text='TEI: %s\n        例文ファイル: %s' % (it, hit[2]))
        top.clear()

    # ---- ID重複 ----
    for k, lines in sorted(ids.items()):
        if len(lines) > 1:
            R.add('ID重複', head=k, line=lines[0], what='xml:id が重複している（TEIの行: %s）' % ', '.join(map(str, lines)), text='')

    # ---- 例文ファイルにあってTEIにない行 ----
    orphan = [ex_rows[s] for s in sorted(ex_rows) if s not in matched_sids]
    for row in orphan:
        R.add('例文ファイルだけにある', head='WdID %s' % row[5], line=0, what='SID %d（見出し %s）' % (row[0], row[4]), text='%s / %s' % (re.sub(r'\s+', ' ', row[1].replace('　', ' ')).strip(), row[3]))

    # ---- GitHub上の音声の有無 ----
    audio_note = '（--ninda-repo を指定していないため、音声ファイルの有無は調べていません）'
    if a.ninda_repo:
        out = subprocess.run(['git', '-C', str(a.ninda_repo), 'ls-tree', '-r', '--name-only', 'HEAD', 'hatoma/midashi', 'hatoma/goi'],
                             capture_output=True, text=True).stdout.split()
        have = {p.split('/')[-1] for p in out}
        audio_note = 'NINDA の GitHub（hatoma/midashi, hatoma/goi）に %d ファイルあります。' % len(have)
        # 見出し語の音声
        for ev, top in etree.iterparse(str(a.tei), tag=T + 'entry', recover=True):
            if top.getparent() is not None and etree.QName(top.getparent()).localname == 'entry':
                continue
            m = top.find(T + 'form/' + T + 'media')
            url = m.get('url') if m is not None else None
            if url and re.fullmatch(r'htmvoc_\d+\.wav', url) and url.replace('.wav', '.mp3') not in have:
                o = top.find(T + 'form/' + T + 'orth')
                R.add('音声ファイルなし', head='%s %s' % (top.get(XID), txt(o)), line=m.sourceline, what='見出し語の音声がGitHubにない', text=url.replace('.wav', '.mp3'))
            top.clear()
        miss = [sid for sid in sorted(matched_sids) if 'htm_%d.mp3' % sid not in have]
        runs = []
        for sid in miss:
            if runs and sid == runs[-1][1] + 1:
                runs[-1][1] = sid
            else:
                runs.append([sid, sid])
        if miss:
            R.add('音声ファイルなし', head='例文の音声 %d件' % len(miss), line=0,
                  what='GitHubの hatoma/goi にない htm_<SID>.mp3 の番号（連続は範囲で表記）',
                  text=', '.join(str(a) if a == b else '%d-%d' % (a, b) for a, b in runs))

    # ---- 書き出し ----
    sections = [
        ('ID重複', 'xml:id の重複', 'XMLの検証や、IDでの検索がうまく動かなくなります。'),
        ('括弧', '括弧の対応が取れていないもの', '閉じ括弧の重複（「(黒蟻))」など）や、足りないもの、種類の違うものを拾っています。「⸢」と「「」の取り違えもここに出ます。'),
        ('記法', 'TEIに変換されずに残っている記法（{…} など）', '歌や出典の注記に使う {Title} {/Bibl} などが、そのまま本文に残っています。'),
        ('表記の不一致', '例文の表記が、TEIと例文ファイルで違うもの', 'どちらが正しいかは、音声と照らして確認が必要です。'),
        ('例文音声', '例文ファイルに対応する行が見つからないもの', 'このサイトでは、これらの例文には音声を付けていません。'),
        ('例文ファイルだけにある', '例文ファイルにあるが、TEIに対応する例文が見つからないもの', 'TEIから漏れた例文か、例文の表記が大きく違う可能性があります。'),
        ('句読点', '句読点が重なっているもの', ''),
        ('空欄', '空欄・欠けているもの', ''),
        ('見出し', '見出し部分の気になる点', ''),
        ('音声', '見出し語の音声ファイル名の指定', ''),
        ('音声ファイルなし', 'GitHub上に音声ファイルがないもの', 'Zenodoの音声一式（zip）には含まれている可能性があります。'),
    ]
    L = []
    L.append('鳩間方言辞典 誤植・不整合の候補メモ')
    L.append('作成日: %s' % datetime.date.today().isoformat())
    L.append('対象: %s（%d見出し、%d語義、%d例文）' % (Path(a.tei).name, n_entries, n_senses, n_ex))
    L.append('作成: scripts/find_typos.py（機械的な検出です。誤植でないものも含みます）')
    L.append('書き方: 見出しID 見出し語 / TEIの行番号 / 内容')
    L.append('')
    L.append('■ 件数')
    for key, title, _ in sections:
        if R.items.get(key) or key in ('ID重複', '括弧'):
            L.append('  %-40s %d件' % (title, len(R.items.get(key, []))))
        if key == '括弧':
            for kw, lab in (('が余分', '閉じ括弧が余分（「(黒蟻))」など）'), ('括弧の種類が合わない', '括弧の種類が合わない'), ('が足りない', '閉じ括弧が足りない')):
                n = sum(1 for it in R.items.get('括弧', []) if kw in it['what'])
                if n:
                    L.append('      内訳: %s %d件' % (lab, n))
            n_hint = sum(1 for it in R.items.get('括弧', []) if '※「⸢」' in it['what'])
            if n_hint:
                L.append('      うち、「⸢」が「「」になっている疑い %d件（「※」で印を付けています）' % n_hint)
    L.append('  %s' % audio_note)
    L.append('')
    for key, title, note in sections:
        its = R.items.get(key, [])
        if not its:
            continue
        L.append('=' * 70)
        L.append('■ %s（%d件）' % (title, len(its)))
        if note:
            L.append('  ' + note)
        L.append('=' * 70)
        for it in its:
            where = ('TEI %d行' % it['line']) if it['line'] else ''
            L.append('%s / %s / %s' % (it['head'], where, it['what']))
            if it['text']:
                L.append('    ' + it['text'])
        L.append('')
    Path(a.out).write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('->', a.out)
    for key, title, _ in sections:
        print('  %-36s %d' % (title, len(R.items.get(key, []))))


if __name__ == '__main__':
    main()
