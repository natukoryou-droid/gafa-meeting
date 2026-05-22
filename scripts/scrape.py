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

GAFA_URL = "https://gafa-official.org/search-results/?meeting-feature%5B%5D=online"
OUTPUT_FILE = Path(__file__).parent.parent / "meetings.json"
ERROR_LOG = Path(__file__).parent.parent / "error.log"
REQUEST_TIMEOUT = 30
USER_AGENT = "GAFA-Meeting-Updater/1.0 (personal use)"

WEEKDAY_CLASS_MAP = {
    "sunday": "日", "monday": "月", "tuesday": "火", "wednesday": "水",
    "thursday": "木", "friday": "金", "saturday": "土",
}
WEEKDAY_TEXT_MAP = {
    "日曜日": "日", "月曜日": "月", "火曜日": "火", "水曜日": "水",
    "木曜日": "木", "金曜日": "金", "土曜日": "土",
}
DAY_ORDER = ["日", "月", "火", "水", "木", "金", "土"]

# meeting-area の li class → 既存JSONで使われている表記
PREF_FROM_CLASS = {
    "hokkaido": "北海道",
    "aomori": "青森県", "akita": "秋田県", "iwate": "岩手県", "miyagi": "宮城県",
    "yamagata": "山形県", "fukushima": "福島県",
    "ibaraki": "茨城県", "tochigi": "栃木県", "gunma": "群馬県",
    "saitama": "埼玉県", "chiba": "千葉県", "tokyo": "東京都", "kanagawa": "神奈川県",
    "niigata": "新潟県", "toyama": "富山県", "ishikawa": "石川県", "fukui": "福井県",
    "yamanashi": "山梨県", "nagano": "長野県",
    "gifu": "岐阜県", "shizuoka": "静岡県", "aichi": "愛知県", "mie": "三重県",
    "shiga": "滋賀県", "kyoto": "京都", "osaka": "大阪", "hyogo": "兵庫県",
    "nara": "奈良県", "wakayama": "和歌山県",
    "tottori": "鳥取県", "shimane": "島根県", "okayama": "岡山県",
    "hiroshima": "広島県", "yamaguchi": "山口県",
    "tokushima": "徳島県", "kagawa": "香川県", "ehime": "愛媛県", "kochi": "高知県",
    "fukuoka": "福岡県", "saga": "佐賀県", "nagasaki": "長崎県", "kumamoto": "熊本県",
    "oita": "大分県", "miyazaki": "宮崎県", "kagoshima": "鹿児島県", "okinawa": "沖縄県",
}

# 〜の表記ゆれ（U+301C / U+FF5E / ASCII ~ / 各種ハイフン）
TILDE_CHARS = "〜～~ー―–—-"


def log_error(message: str) -> None:
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
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def to_halfwidth(text: str) -> str:
    return text.translate(str.maketrans("０１２３４５６７８９：", "0123456789:"))


def normalize_time(text: str) -> str:
    """'10:15〜11:15' → '10:15-11:15'"""
    text = to_halfwidth(text)
    text = re.sub(f"[{TILDE_CHARS}]", "-", text)
    m = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def extract_prefecture(card) -> str:
    """ul.meeting-area の li class から都道府県を取得（最も具体的なものを採用）"""
    for li in card.select("ul.meeting-area li"):
        for cls in li.get("class", []):
            if cls in PREF_FROM_CLASS:
                return PREF_FROM_CLASS[cls]
    return ""


def extract_email(card) -> str:
    """カード内 <table> から「お問い合わせ」セルのメールを抽出（全角＠も対応）"""
    def find_in(text: str) -> str:
        text = text.replace("＠", "@")
        m = re.search(r"[\w.\-]+@[\w.\-]+\.[\w.\-]+", text)
        return m.group(0) if m else ""

    for tr in card.select("figure.wp-block-table table tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2 and "お問い合わせ" in tds[0].get_text():
            mail = find_in(tds[1].get_text())
            if mail:
                return mail
    return find_in(card.get_text())


def parse_time_field(time_text: str) -> list[tuple[str, str, str]]:
    """
    p.time のテキストから (曜日, 時間, note) のリストを返す。

    例:
      "10:15〜11:15"
        → [("", "10:15-11:15", "")]
      "第1・3（日）10:15〜11:15　第2・4（火）19:15〜20:15"
        → [("日", "10:15-11:15", "第1・3日のみ"),
           ("火", "19:15-20:15", "第2・4火のみ")]
    """
    text = time_text.strip()
    # 特殊スケジュール: 第N・M（曜）HH:MM〜HH:MM
    pattern = re.compile(
        r"第([0-9０-９]+(?:[・,]\s*[0-9０-９]+)*)\s*[（(]\s*([日月火水木金土])\s*[)）]\s*"
        r"([0-9０-９]{1,2}[:：][0-9０-９]{2}\s*[" + TILDE_CHARS + r"]\s*[0-9０-９]{1,2}[:：][0-9０-９]{2})"
    )
    matches = list(pattern.finditer(text))
    if matches:
        results = []
        for m in matches:
            weeks = to_halfwidth(m.group(1)).replace("，", ",").replace("、", ",")
            weeks = weeks.replace(",", "・")
            day = m.group(2)
            time_str = normalize_time(m.group(3))
            note = f"第{weeks}{day}のみ"
            if time_str:
                results.append((day, time_str, note))
        if results:
            return results

    time_str = normalize_time(text)
    if time_str:
        return [("", time_str, "")]
    return []


def parse_meetings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.meeting-content")
    if not cards:
        # 一部レイアウトでは meeting-block を起点に探す
        cards = [b.parent for b in soup.select("div.meeting-block")]

    meetings: list[dict] = []

    for card in cards:
        title_el = card.select_one("h2.wp-block-post-title, .wp-block-post-title")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        if not name:
            continue

        # 曜日（複数あり得る）
        days: list[str] = []
        for li in card.select("ul.meeting-week li"):
            d = ""
            for cls in li.get("class", []):
                if cls in WEEKDAY_CLASS_MAP:
                    d = WEEKDAY_CLASS_MAP[cls]
                    break
            if not d:
                d = WEEKDAY_TEXT_MAP.get(li.get_text(strip=True), "")
            if d and d not in days:
                days.append(d)
        if not days:
            continue

        # 時間（特殊スケジュール対応）
        time_el = card.select_one("p.time")
        time_text = time_el.get_text(" ", strip=True) if time_el else ""
        time_entries = parse_time_field(time_text)
        if not time_entries:
            continue

        pref = extract_prefecture(card)

        mail = extract_email(card)
        if not mail:
            continue

        # 曜日と時間のマッチング
        # ケースA: 特殊スケジュール（day付きエントリ） → そのday/timeで登録
        # ケースB: 単一時間（day=""） → meeting-week 各曜日に同じ時間で登録
        specific = [e for e in time_entries if e[0]]
        if specific:
            for day, time_str, note in specific:
                if day in days:
                    meetings.append({
                        "day": day, "name": name, "pref": pref,
                        "time": time_str, "mail": mail, "note": note,
                    })
        else:
            _, time_str, _ = time_entries[0]
            for day in days:
                meetings.append({
                    "day": day, "name": name, "pref": pref,
                    "time": time_str, "mail": mail, "note": "",
                })

    if not meetings:
        raise ValueError("ミーティング情報が見つかりませんでした。サイト構造が変更された可能性があります。")

    # 重複排除（同じ day+name+time）
    seen = set()
    deduped = []
    for m in meetings:
        key = (m["day"], m["name"], m["time"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    meetings = deduped

    # 曜日順→時刻順
    def time_key(m):
        mm = re.match(r"(\d{1,2}):(\d{2})", m.get("time", ""))
        return int(mm.group(1)) * 60 + int(mm.group(2)) if mm else 9999

    meetings.sort(key=lambda m: (
        DAY_ORDER.index(m["day"]) if m["day"] in DAY_ORDER else 99,
        time_key(m),
    ))

    # 曜日内 No. 採番
    counts: dict[str, int] = {}
    for m in meetings:
        counts[m["day"]] = counts.get(m["day"], 0) + 1
        m["no"] = counts[m["day"]]

    # キー順を既存JSONに合わせる
    ordered = []
    for m in meetings:
        ordered.append({
            "day": m["day"], "no": m["no"], "name": m["name"],
            "pref": m["pref"], "time": m["time"], "mail": m["mail"],
            "note": m["note"],
        })
    return ordered


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

        if OUTPUT_FILE.exists():
            try:
                with OUTPUT_FILE.open("r", encoding="utf-8") as f:
                    old = json.load(f)
                old_count = old.get("count", len(old.get("meetings", []))) if isinstance(old, dict) else len(old)
                if old_count > 0 and len(meetings) < old_count * 0.5:
                    log_error(
                        f"取得件数が既存の半分未満です（{len(meetings)} < {old_count * 0.5}）。"
                        "既存データを維持します。"
                    )
                    return 1
            except Exception:
                pass

        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst)
        fmt = "%Y/%#m/%#d %H:%M" if sys.platform == "win32" else "%Y/%-m/%-d %H:%M"
        output = {
            "updated_at": now.strftime(fmt),
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
