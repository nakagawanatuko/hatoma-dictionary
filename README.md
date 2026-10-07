# 鳩間方言辞典アプリ

`hatoma.tei`（TEI Lex-0版 鳩間方言辞典）の全体から、FirstVoices風の検索サイトを作る作業フォルダです。
全16,732見出し・18,327語義・34,155例文を収めています。
生成AI (Claude Sonnet 5.5 Medium) で作りました。

## すぐ使う

`docs/index.html` をブラウザで開きます（ダブルクリックで開けます）。
同じ場所の `docs/data/hatoma-data.js`（約15MB）を読み込むので、`docs` フォルダごと扱ってください。

- 検索: 「すべて」「方言から」「標準語から」。方言はカタカナ・ひらがな・IPAで引けます。
- 絞り込み: 頭の音（五十音）、品詞、分野。
- 音声: 見出し語と例文の再生ボタン。ネットにつながっていれば鳴ります（下の「音声」を参照）。
- 一覧は少しずつ表示します。スクロールするか、「さらに表示」で続きが出ます。
- タイトル「鳩間方言辞典」を押すと、最初の状態に戻ります。

## GitHub Pages で公開する

リポジトリの Settings → Pages で、Branch を `main`、フォルダを `/docs` にして Save します。
公開アドレスは `https://nakagawanatuko.github.io/hatoma-dictionary/` です。

## フォルダ構成

```
hatoma-dictionary/
├─ docs/                  公開用（GitHub Pages がここを配信）
│   ├─ index.html           完成品
│   ├─ data/hatoma-data.js  全件のデータ
│   └─ audio/               任意。mp3を置くと、GitHubより先にこちらを使う
├─ source/                元データ
│   ├─ hatoma.tei                              TEI Lex-0（https://github.com/yf-wang-ninjal/hatoma-dic/tree/main/tei）
│   ├─ Hatoma_example_20220921.txt             例文と例文音声（SID）の対応（非公開）
│   ├─ hatoma_reverse_dict.tsv                 標準語キーワード→鳩間語の逆引き（非公開）
│   └─ hatoma_reverse_index_full_hiragana.tsv  逆引き索引（ひらがな読み付き）（非公開）
├─ scripts/
│   ├─ convert_tei.py     TEI → JSON（既定は先頭100見出し。--limit 0 で全件）
│   ├─ example_norm.py    例文の突き合わせ用の共通関数
│   ├─ find_typos.py      誤植・不整合の候補を拾って memo.txt を作る
│   ├─ build_site.py      テンプレート＋JSON → docs/
│   └─ smoke_test.py      ブラウザでの簡易動作確認（Playwright）
├─ data/
│   ├─ hatoma_full.json        全件（サイト用に軽量化済み）
│   └─ hatoma_sample100.json   先頭100見出し
├─ site/
│   ├─ template.html           画面の元（CSS・JS入り、データなし）
│   └─ hatoma-sample100.html   試作版（先頭100見出しを埋め込んだ1枚のHTML）
├─ memo.txt                誤植・不整合の候補メモ（find_typos.py の出力）
├─ LICENSE                 ライセンスと出典
└─ README.md               このファイル
```

## 作り直す手順

プロジェクト直下で実行します。

```
pip install lxml pykakasi
python3 scripts/convert_tei.py --limit 0 --out data/hatoma_full.json   # 約7秒
python3 scripts/build_site.py                                            # docs/ に全件版を作る
python3 scripts/find_typos.py                                            # memo.txt を作る
```

- 試作版: `python3 scripts/convert_tei.py` のあと `python3 scripts/build_site.py --sample`。
- 動作確認: `pip install playwright && playwright install chromium` のあと `python3 scripts/smoke_test.py`。
- 音声の有無まで調べる: `python3 scripts/find_typos.py --ninda-repo <NINDAのgit clone>`。

## 変換の方針

- 対象は親見出しです。同形語（`type="homonymicEntry"`）は親の見出しに語義として含めます。
- 標準語の見出しは、語釈の最初の一文（「。」まで）から自動で取り出し、読みはpykakasiで付けています。
  TEIに標準語の見出し欄がないための暫定処置です。そのため「魚の名前」のような説明文も標準語側に並びます。
- 品詞の略号は、意味が確かなものだけ展開しています（名→名詞、形→形容詞、格助→格助詞 など）。
  成・接・助・並立・間助・慣・句・接続 などは原文のままです。
- 分野の略号は、動→動物、植→植物、地→地名 と読み替えています。この3つはファイル内に定義が見当たらず、推測です。
  屋・数・人・幼 などは原文のままです。
- 例文の訳は、外側の ( ) と文末の「。」を取り、ルビはHTMLのruby要素で表示します。
- 同じ `xml:id` を持つ見出し（`HATOMA.1622` が2つ）は、2つ目に `HATOMA.1622_2` という表示用のキーを付けています。
- データは軽くするため、既定値を省いています（見出し語の音声名は `htmvoc_<ID番号>.wav` を既定とし、違うときだけ保存）。

## 音声

再生ボタンは、次の順に取得を試します（`site/template.html` の `sources`）。

1. `docs/audio/` に置いた mp3（あれば）
2. NINDAのGitHub（`somiyagawa/NINDA`）
   - 見出し語: `hatoma/midashi/htmvoc_N.mp3`
   - 例文: `hatoma/goi/htm_N.mp3`（Nは `Hatoma_example_20220921.txt` のSID）

- TEIの `.wav` や例文ファイルの `htm_N.wav` は、実際は `.mp3` です（読み替えています）。
- 例文音声は、`Hatoma_example_20220921.txt` の同じWdIDの行から、例文の文字列（空白・ルビ記法を除く）が一致するものを選んでSIDを対応づけています。
  一致しないときは、IPAか訳文が一致する行を使います（5件）。それも合わない168例文には音声を付けていません（`memo.txt` に一覧）。
- 見出し語の音声がない見出しは2件です（`HATOMA.1327`、`HATOMA.5026`。TEIの指定が `#`）。
- GitHubには、対応づけた例文音声のうち530件が見当たりません（番号は `memo.txt` に範囲で記載）。
  Zenodoの音声一式（zip）には含まれている可能性があるので、zipを展開して `docs/audio/` に入れると鳴ります。
- GitHubの `raw` は常用の配信先ではありません。公開するときは、自前のサーバーかCDNに音声を移してください。

## 誤植の候補

`memo.txt` にあります。機械的な検出なので、誤植でないものも含みます。主な内容は次のとおりです。

- 括弧の対応が取れていないもの 721件。閉じ括弧の重複（「(黒蟻))」など）が556件です。
  そのうち538件は「⸢」が「「」になっている疑いで、「※」を付けています。
- xml:id の重複 11件。
- TEIに変換されずに残っている記法（`{Title}`、`{` など）64件。
- 例文の表記が、TEIと例文ファイルで違うもの 208件。
- 例文ファイルとTEIで対応が取れない例文（168件と202件）。

## 次にやること（案）

1. 標準語引きの精度を上げる。`hatoma_reverse_index_full_hiragana.tsv` の「日本語（見出し語）」と
   「読み（ひらがな）」を標準語見出しとして使えば、自動抽出よりきれいになる可能性があります（未検証）。
2. 意味分野（身体、自然、親族など）を、FirstVoicesのカテゴリのように追加する。
3. 音声を自前の配信先に移す。

## 出典

TEI Lex-0版 鳩間方言辞典（国立国語研究所、編集: 王一凡・中川奈津子、2026年4月28日版）。
音声（見出し語）: [doi:10.5281/zenodo.4560935](https://doi.org/10.5281/zenodo.4560935)
音声（例文）: [doi:10.5281/zenodo.7100944](https://doi.org/10.5281/zenodo.7100944)
配信元: NINDAのGitHub `somiyagawa/NINDA`。
ライセンス: 辞書データは [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)、見出し語の音声はCC BY-SA、例文の音声はCC BY（版は未確認）。
