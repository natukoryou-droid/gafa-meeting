"""
GAFA公式サイトからオンラインミーティング情報をスクレイピングするスクリプト

実行方法:
    python scripts/scrape.py

出力:
    meetings.json (成功時)
    error.log (失敗時)

注意:
    失敗時は既存の meetings.json を維持し、エラーログのみ追記する
"""

import json
import re
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# 設定
GAFA_URL = "https://gafa-official.org/meeting/"
OUTPUT_FILE = Path(__file__).parent.parent / "meetings.json"
ERROR_LOG = Path(__file__).parent.parent / "error.log"
REQUEST_TIMEOUT = 30
USER_AGENT = "GAFA-Meeting-Updater/1.0 (personal use)"

# 曜日マッピング
DAY_MAP = {
    "月曜日": "月", "火曜日": "火", "水曜日": "水",
    "木曜日": "木", "金曜日": "金", "土曜日": "土", "日曜日": "日",
    "月": "月", "火": "火", "水": "水",
    "木": "木", "金": "金", "土": "土", "日": "日",
}


def log_error(message: str) -> None:
    """エラーをタイムスタンプ付きでログ出力"""
    jst = timezone(timedelta(hours=9))
    ts = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}\n"
    print(line, file=sys.stderr, end="")
    try:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def fetch_html(url: str) -> str:
    """GAFA公式サイトのHTMLを取得"""
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_time(text: str) -> str:
    """時間文字列を 'HH:MM-HH:MM' 形式に正規化"""
    if not text:
        return ""
    # 全角を半角に
    text = text.translate(str.maketrans("０１２３４５６７８９：", "0123456789:"))
    # 〜やーをハイフンに統一
    text = re.sub(r"[〜~ー―–—]", "-", text)
    text = text.replace("@", "-")
    # 時間パターンを抽出
    match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return text.strip()


def normalize_day(text: str) -> str:
    """曜日表記を1文字に正規化"""
    if not text:
        return ""
    text = text.strip()
    for key, val in DAY_MAP.items():
        if key in text:
            return val
    return ""


def parse_meetings(html: str) -> list[dict]:
    """HTMLからミーティング情報を抽出"""
    soup = BeautifulSoup(html, "html.parser")
    meetings = []

    # GAFA公式サイトの構造に合わせて探索
    # テーブル形式の場合
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            # 曜日を含む行を抽出
            day = ""
            for t in texts:
                d = normalize_day(t)
                if d:
                    day = d
                    break
            if not day:
                continue
            # メールアドレス検索
            mail = ""
            for c in cells:
                m = re.search(r"[\w\.\-]+@[\w\.\-]+", c.get_text())
                if m:
                    mail = m.group(0)
                    break
            # 時間検索
            time_str = ""
            for t in texts:
                if re.search(r"\d{1,2}:\d{2}", t):
                    time_str = parse_time(t)
                    break
            # グループ名と県を推定
            name = ""
            pref = ""
            for t in texts:
                if normalize_day(t):
                    continue
                if re.search(r"\d{1,2}:\d{2}", t):
                    continue
                if "@" in t:
                    continue
                if re.search(r"[都道府県]$", t) or t in ["北海道", "京都", "大阪", "東京"]:
                    pref = t
                elif not name and t:
                    name = t

            if name and mail:
                meetings.append({
                    "day": day,
                    "name": name,
                    "pref": pref,
                    "time": time_str,
                    "mail": mail,
                    "note": "",
                })

    if not meetings:
        # テーブルが見つからない場合は別の手段を試す
        raise ValueError("ミーティング情報が見つかりませんでした。サイト構造が変更された可能性があります。")

    # 各曜日内で開始時間順にソート
    def time_key(m):
        t = m.get("time", "")
        match = re.match(r"(\d{1,2}):(\d{2})", t)
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
        return 9999

    day_order = ["日", "月", "火", "水", "木", "金", "土"]
    meetings.sort(key=lambda m: (day_order.index(m["day"]) if m["day"] in day_order else 99, time_key(m)))

    # No.を曜日内で振り直す
    counts = {}
    for m in meetings:
        d = m["day"]
        counts[d] = counts.get(d, 0) + 1
        m["no"] = counts[d]

    return meetings


def main() -> int:
    try:
        print(f"GAFA公式サイトからデータ取得開始: {GAFA_URL}")
        html = fetch_html(GAFA_URL)
        print(f"HTML取得成功 ({len(html)} バイト)")

        meetings = parse_meetings(html)
        print(f"ミーティング数: {len(meetings)} 件")

        if len(meetings) == 0:
            log_error("ミーティング数が0件です。既存データを維持します。")
            return 1

        # 既存データの件数チェック（極端な減少は異常とみなす）
        if OUTPUT_FILE.exists():
            try:
                with OUTPUT_FILE.open("r", encoding="utf-8") as f:
                    old = json.load(f)
                if len(old) > 0 and len(meetings) < len(old) * 0.5:
                    log_error(
                        f"取得件数が既存の半分未満です（{len(meetings)} < {len(old) * 0.5}）。"
                        "既存データを維持します。"
                    )
                    return 1
            except Exception:
                pass

        # 保存
        jst = timezone(timedelta(hours=9))
        output = {
            "updated_at": datetime.now(jst).strftime("%Y/%-m/%-d %H:%M") if sys.platform != "win32" else datetime.now(jst).strftime("%Y/%#m/%#d %H:%M"),
            "count": len(meetings),
            "meetings": meetings,
        }
        with OUTPUT_FILE.open("w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"保存完了: {OUTPUT_FILE}")
        return 0

    except Exception as e:
        log_error(f"スクレイピングエラー: {e}\n{traceback.format_exc()}")
        print("既存データを維持します。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
