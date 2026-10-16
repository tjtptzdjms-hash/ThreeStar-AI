from datetime import datetime
from pathlib import Path
import csv
import re
import sys

from TaiwanLottery import TaiwanLotteryCrawler
import requests

CSV_FILE = Path("draws.csv")
HEADERS = ["date", "issue", "number"]


def month_range(start_year, start_month, end_year, end_month):
    y, m = start_year, start_month

    while (y, m) <= (end_year, end_month):
        yield y, m

        m += 1
        if m == 13:
            y += 1
            m = 1


def load_existing():
    rows = []

    if not CSV_FILE.exists():
        return rows

    with CSV_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            date = str(row.get("date", "")).strip()
            issue = str(row.get("issue", "")).strip()
            number = str(row.get("number", "")).strip().zfill(3)

            if date and issue and re.fullmatch(r"\d{3}", number):
                rows.append({
                    "date": date,
                    "issue": issue,
                    "number": number,
                })

    return rows


def walk_objects(obj):
    if isinstance(obj, dict):
        yield obj

        for value in obj.values():
            yield from walk_objects(value)

    elif isinstance(obj, list):
        for item in obj:
            yield from walk_objects(item)


def first_value(data, keys):
    for key in keys:
        if key in data and data[key] not in (None, "", []):
            return data[key]

    return None


def normalize_date(value):
    if value is None:
        return None

    text = str(value).strip()

    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)

    if not match:
        return None

    y, m, d = map(int, match.groups())

    try:
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return None


def normalize_issue(value):
    if value is None:
        return None

    text = re.sub(r"\D", "", str(value))

    if len(text) < 5:
        return None

    return text


def normalize_number(value):
    if value is None:
        return None

    # [1, 2, 3]
    if isinstance(value, (list, tuple)):
        digits = []

        for item in value:
            s = re.sub(r"\D", "", str(item))

            if len(s) == 1:
                digits.append(s)

        if len(digits) >= 3:
            return "".join(digits[:3])

    text = str(value).strip()

    # 例如 "1,2,3" / "1 2 3"
    separated = re.findall(r"(?<!\d)(\d)(?!\d)", text)

    if len(separated) >= 3:
        return "".join(separated[:3])

    # 例如 "123"
    digits = re.sub(r"\D", "", text)

    if len(digits) == 3:
        return digits

    return None


def extract_draws(raw):
    draws = []

    date_keys = [
        "開獎日期",
        "lotteryDate",
        "drawDate",
        "date",
        "openDate",
    ]

    issue_keys = [
        "期別",
        "期號",
        "period",
        "issue",
        "drawTerm",
    ]

    number_keys = [
        "獎號",
        "中獎號碼",
        "drawNumberSize",
        "drawNumbers",
        "numbers",
        "number",
        "winningNumbers",
    ]

    for item in walk_objects(raw):
        date_raw = first_value(item, date_keys)
        issue_raw = first_value(item, issue_keys)
        number_raw = first_value(item, number_keys)

        date = normalize_date(date_raw)
        issue = normalize_issue(issue_raw)
        number = normalize_number(number_raw)

        if date and issue and number:
            draws.append({
                "date": date,
                "issue": issue,
                "number": number,
            })

    unique = {}

    for row in draws:
        unique[row["issue"]] = row

    return list(unique.values())


def fetch_month(year, month):
    print(f"正在抓取 {year}-{month:02d} ...")

    crawler = TaiwanLotteryCrawler()

    raw = crawler.lotto3d([
        str(year),
        f"{month:02d}",
    ])

    rows = extract_draws(raw)

    print(f"  找到 {len(rows)} 期")

    return rows


def save_rows(rows):
    valid = {}

    for row in rows:
        date = row["date"]
        issue = row["issue"]
        number = row["number"]

        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            continue

        if not issue.isdigit():
            continue

        if not re.fullmatch(r"\d{3}", number):
            continue

        valid[issue] = {
            "date": date,
            "issue": issue,
            "number": number,
        }

    result = list(valid.values())

    result.sort(
        key=lambda x: (
            x["date"],
            int(x["issue"]),
        ),
        reverse=True,
    )

    with CSV_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(result)

    return result

def fetch_latest_official():
    """
    補最新三星彩資料。
    先嘗試直接從台彩目前使用的 API 取得本月結果。
    若 API 格式改變或暫時失效，就回傳空陣列，不破壞原資料。
    """

    now = datetime.now()
    month = now.strftime("%Y-%m")

    candidates = [
        (
            "https://api.taiwanlottery.com/TLCAPIWeB/"
            f"Lottery/3DResult?period&month={month}&pageNum=1&pageSize=50"
        ),
        (
            "https://api.taiwanlottery.com/TLCAPIWeB/"
            f"Lottery/Lotto3DResult?period&month={month}&pageNum=1&pageSize=50"
        ),
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Safari/604.1"
        )
    }

    for url in candidates:
        try:
            r = requests.get(
                url,
                headers=headers,
                timeout=20,
            )

            if r.status_code != 200:
                continue

            data = r.json()
            rows = extract_draws(data)

            if rows:
                print(
                    f"官方最新來源成功取得 {len(rows)} 期"
                )
                return rows

        except Exception as exc:
            print(
                f"官方最新來源失敗：{exc}",
                file=sys.stderr,
            )

    print("官方最新來源目前沒有取得有效資料。")
    return []
def main():
    existing = load_existing()

    now = datetime.now()

    # 第一次建立資料庫：
    # 從 2024-01 抓到目前月份。
    #
    # 日後每日自動執行時：
    # 只重新抓本月及上月，避免大量重複請求。
    if len(existing) <= 1:
        start_year = 2024
        start_month = 1

        print("第一次建立三星彩歷史資料庫")
        print("將回填 2024-01 至目前月份")

    else:
        if now.month == 1:
            start_year = now.year - 1
            start_month = 12
        else:
            start_year = now.year
            start_month = now.month - 1

        print(
            f"目前已有 {len(existing)} 期，"
            "只更新最近兩個月份"
        )

    all_rows = existing.copy()
    success_months = 0
    latest_rows = fetch_latest_official()

if latest_rows:
    all_rows.extend(latest_rows)

    for year, month in month_range(
        start_year,
        start_month,
        now.year,
        now.month,
    ):
        try:
            rows = fetch_month(year, month)

            if rows:
                all_rows.extend(rows)
                success_months += 1

        except Exception as exc:
            print(
                f"警告：{year}-{month:02d} 抓取失敗：{exc}",
                file=sys.stderr,
            )

    if success_months == 0 and not latest_rows:
        print("沒有成功取得任何月份資料。")

        if existing:
            print("保留原本 draws.csv，不覆蓋。")
            return

        raise RuntimeError(
            "首次建立資料庫失敗，未取得任何有效三星彩資料。"
        )

    saved = save_rows(all_rows)

    if not saved:
        raise RuntimeError("沒有有效資料可寫入。")

    print()
    print("更新完成")
    print(f"目前總期數：{len(saved)}")
    print(
        f"最新一期：{saved[0]['date']} "
        f"{saved[0]['issue']} "
        f"{saved[0]['number']}"
    )


if __name__ == "__main__":
    main()
