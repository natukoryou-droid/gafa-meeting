"""
meetings.json を元に gafa_meeting.html 内のデータを更新するスクリプト

更新箇所:
    1. const meetings = [...]  ← ミーティングデータ
    2. <span id="last-updated">  ← 最終更新日時
    3. <span id="group-count">  ← グループ数

A4縦1ページに収まるよう、件数に応じて行高さ・フォントサイズを自動調整する。

実行方法:
    python scripts/update_html.py
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 設定
ROOT = Path(__file__).parent.parent
JSON_FILE = ROOT / "meetings.json"
HTML_FILE = ROOT / "gafa_meeting.html"


def build_meetings_array(meetings: list[dict]) -> str:
    """ミーティングデータをJavaScript配列の文字列に変換"""
    lines = []
    for m in meetings:
        day = m.get("day", "")
        no = m.get("no", 0)
        name = m.get("name", "").replace('"', '\\"')
        pref = m.get("pref", "").replace('"', '\\"')
        time = m.get("time", "").replace('"', '\\"')
        mail = m.get("mail", "").replace('"', '\\"')
        note = m.get("note", "").replace('"', '\\"')
        lines.append(
            f'    {{ day: "{day}", no: {no}, name: "{name}", pref: "{pref}", '
            f'time: "{time}", mail: "{mail}", note: "{note}" }},'
        )
    return "\n".join(lines)


def build_density_style(count: int) -> str:
    """件数に応じた密度調整CSS（A4縦1枚を維持するため）"""
    if count <= 24:
        # 標準サイズ（オリジナル維持）
        return ""
    elif count <= 30:
        # 少し小さめ
        return """
  /* 件数調整: 25-30件 */
  tbody td { padding: 6px 5px; }
  td.name { font-size: 12.5px; }
  td.time { font-size: 11.5px; }
  td.mail { font-size: 10px; }
"""
    elif count <= 37:
        # かなり小さめ
        return """
  /* 件数調整: 31-37件 */
  tbody td { padding: 4px 4px; }
  td.name { font-size: 11.5px; }
  td.pref { font-size: 10.5px; }
  td.time { font-size: 10.5px; }
  td.mail { font-size: 9px; }
  .day-tag { font-size: 15px; padding: 4px 3px; min-width: 32px; }
"""
    else:
        # 最小サイズ（38件以上）
        return """
  /* 件数調整: 38件以上 */
  tbody td { padding: 3px 3px; }
  td.name { font-size: 10.5px; }
  td.pref { font-size: 9.5px; }
  td.time { font-size: 9.5px; }
  td.mail { font-size: 8.5px; }
  .day-tag { font-size: 13px; padding: 3px 2px; min-width: 28px; }
  td.check input[type="checkbox"] { width: 14px; height: 14px; }
"""


def update_html(html: str, meetings: list[dict], updated_at: str, checked_at: str) -> str:
    """HTML文字列内のミーティングデータと更新日時を書き換え"""
    count = len(meetings)

    # 1. const meetings = [...]; を置換
    new_array = build_meetings_array(meetings)
    pattern = r"(const meetings = \[)[\s\S]*?(\n\s*\];)"
    replacement = r"\g<1>\n" + new_array + r"\g<2>"
    html = re.sub(pattern, replacement, html, count=1)

    # 2. 最終更新日時を置換（データ変更時のみ実質変わる）
    html = re.sub(
        r'(<span id="last-updated">)[^<]*(</span>)',
        f"\\g<1>{updated_at}\\g<2>",
        html,
    )

    # 2.5 自動チェック日時を置換（毎回必ず更新）
    html = re.sub(
        r'(<span id="last-checked">)[^<]*(</span>)',
        f"\\g<1>{checked_at}\\g<2>",
        html,
    )

    # 3. グループ数を置換
    html = re.sub(
        r'(<span id="group-count">)[^<]*(</span>)',
        f"\\g<1>{count}\\g<2>",
        html,
    )

    # 4. 密度調整CSSを挿入（既存の調整を削除してから）
    html = re.sub(
        r"\n\s*/\* 件数調整[\s\S]*?\*/[\s\S]*?(?=\n\s*/\*|\n\s*@media|</style>)",
        "\n",
        html,
    )
    density_css = build_density_style(count)
    if density_css.strip():
        html = html.replace(
            "@media print {",
            f"{density_css}\n  @media print {{",
            1,
        )

    return html


def main() -> int:
    if not JSON_FILE.exists():
        print(f"エラー: {JSON_FILE} が見つかりません", file=sys.stderr)
        return 1
    if not HTML_FILE.exists():
        print(f"エラー: {HTML_FILE} が見つかりません", file=sys.stderr)
        return 1

    # データ読み込み
    with JSON_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    checked_at = f"{now.year}/{now.month}/{now.day} {now.hour:02d}:{now.minute:02d}"

    if isinstance(data, list):
        meetings = data
        updated_at = checked_at
    else:
        meetings = data.get("meetings", [])
        updated_at = data.get("updated_at", "") or checked_at

    if not meetings:
        print("エラー: meetings.json にデータがありません", file=sys.stderr)
        return 1

    # HTML読み込み
    with HTML_FILE.open("r", encoding="utf-8") as f:
        html = f.read()

    # 更新
    new_html = update_html(html, meetings, updated_at, checked_at)

    # 書き込み
    with HTML_FILE.open("w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"HTML更新完了: {len(meetings)}件、データ更新 {updated_at}、自動チェック {checked_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
