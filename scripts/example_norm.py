"""例文の突き合わせ用の共通関数。convert_tei.py と find_typos.py が使う。"""
import html, re

T = '{http://www.tei-c.org/ns/1.0}'


def norm_ex(s):
    """例文ファイル（Hatoma_example_*.txt）の記法をTEI側の形にそろえ、空白を除く。

    \\ruby{親}{ルビ} -> 親 / {EOS} -> 。 / {EOS!} -> ! / {f}…{/f}（ふりがな注記）-> 削除
    """
    s = s or ''
    s = re.sub(r'\{f\}.*?\{/f\}', '', s)
    s = re.sub(r'\\ruby\{([^}]*)\}\{[^}]*\}', r'\1', s)
    s = s.replace('{EOS!}', '!').replace('{EOS}', '。')
    return re.sub(r'\s+', '', s)


def ntr(s):
    """訳文を比べるための形。空白、末尾の「。」、全体を囲む ( ) を除く。"""
    s = re.sub(r'[。.]+$', '', norm_ex(s))
    return s[1:-1] if s.startswith('(') and s.endswith(')') else s


def html_plain(s):
    """ruby入りのHTML断片から、ルビ（rt）を除いた文字列を取り出す。"""
    s = re.sub(r'<rt>.*?</rt>', '', s or '')
    return html.unescape(re.sub(r'<[^>]+>', '', s))


def plain_tei(e):
    """TEIの要素から、ルビ（rt）を除いた文字列を取り出す。"""
    if e is None:
        return ''
    out = [e.text or '']
    for c in e:
        name = c.tag.split('}')[-1] if isinstance(c.tag, str) else ''
        if name == 'ruby':
            rb = c.find(T + 'rb')
            out.append(''.join(rb.itertext()) if rb is not None else '')
        elif name != 'rt':
            out.append(plain_tei(c))
        out.append(c.tail or '')
    return ''.join(out)
