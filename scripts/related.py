"""語釈の中の「～の対義語」「～参照」「～と同義」などから、見出し語どうしの関連を取り出す。

語釈には、関連する語が「アクセント表記[IPA](意味)」の形で書かれ、そのあとに関係を示す語が続く。
  例: ⸢イールムティ[⸢ʔiːrumuti](西側)の対義語。 / ⸣ヌビ[⸣nubi]参照。 / ア⸢ミルン[ʔa⸢miruŋ](浴びる)と同義。
アクセント記号を除いた形が、ほかの見出し語の表記と一致したときだけ、関連として採用する。

関係の種類（rel のキー）:
  a 対義語（相互） s 同義・類義（相互） r 参照（一方向） o 別の言い方（「ともいう」。相互）
"""
import re, html, collections

KINDS = [  # (関係を示す語のパターン, キー)
    (r'(?:の)?対義(?:語)?', 'a'),
    (r'(?:の)?類義(?:語|表現)?|と同義(?:語)?|と同じ(?!大き|くらい|ほど)', 's'),
    (r'(?:の項)?参照', 'r'),
    (r'(?:と)?も(?:いう|いい|言う)|ともよぶ|とも呼ぶ', 'o'),
]
KIND_RE = [(re.compile(p), k) for p, k in KINDS]
# 「X[IPA]」のX。アクセント記号 ⸢ ⸣ を含むカタカナ列
TOKEN = re.compile(r'([゠-ヿぁ-ゖーッふ⸢⸣⸠⸡̀-ͯ⸢-⸥]{1,40})\[([^\]]{1,60})\]')

def plain(s):
    return html.unescape(re.sub(r'<rt>.*?</rt>|<[^>]+>', '', s or ''))

def key_of(s):
    return re.sub(r'[⸢⸣⸠⸡\s̀-ͯ]', '', s)

def add_related(entries, notes=None):
    """entries（slim後のリスト）に 'rel' を付ける。{キー:[見出しの添字,...]}"""
    by = collections.defaultdict(list)
    for i, e in enumerate(entries): by[key_of(e['orth'])].append(i)
    rel = collections.defaultdict(lambda: collections.defaultdict(list))
    miss = collections.Counter(); found = collections.Counter()
    def add(i, k, j):
        if j != i and j not in rel[i][k]: rel[i][k].append(j)
    for i, e in enumerate(entries):
        for s in e['senses']:
            d = plain(s['def'])
            for m in TOKEN.finditer(d):
                tail = d[m.end():m.end() + 14]
                tail = re.sub(r'^\s*(?:\([^()]*\))?', '', tail)     # 直後の（意味）を飛ばす
                kind = None
                for rx, k in KIND_RE:
                    mm = rx.match(tail)
                    if mm: kind = k; break
                if not kind: continue
                targets = by.get(key_of(m.group(1)))
                if not targets: miss[kind] += 1; continue
                if len(targets) > 1:      # 同じ表記の見出しが複数あるときは、IPAが一致するものに絞る
                    ipa = key_of(m.group(2))
                    same = [j for j in targets if key_of(entries[j]['ipa'].strip('[]')) == ipa]
                    targets = same or targets
                if len(targets) > 1:      # それでも複数なら、語釈が同じものに絞る（例: アクビ→ヌビ（あくび））
                    toks = lambda es: {w for x in es['senses'] for w in re.findall(r'[^()（）]+', x['gloss'] or '')}
                    gl = toks(e)
                    same = [j for j in targets if gl & toks(entries[j])]
                    targets = same or targets
                found[kind] += 1
                for j in targets:
                    add(i, kind, j)
                    if kind in ('a', 's', 'o'): add(j, kind, i)       # 相互の関係は逆向きにも付ける
    n = 0
    for i, r in rel.items():
        entries[i]['rel'] = {k: v for k, v in r.items() if v}; n += 1
    return n, found, miss
