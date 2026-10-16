from datetime import datetime
from pathlib import Path
import csv
import re
import sys
import requests
from TaiwanLottery import TaiwanLotteryCrawler


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

    with CSV_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        reader = csv.DictReader(f)

        for row in reader:
            date = str(
                row.get("date", "")
            ).strip()

            issue = str(
                row.get("issue", "")
            ).strip()

            number = str(
                row.get("number", "")
            ).strip().zfill(3)

            if (
                date
                and issue
                and re.fullmatch(r"\d{3}", number)
            ):
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
        if key in data:
            value = data[key]

            if value not in (None, "", []):
                return value

    return None


def normalize_date(value):
    if value is None:
        return None

    text = str(value).strip()

    match = re.search(
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
        text
    )

    if not match:
        return None

    year, month, day = map(
        int,
        match.groups()
    )

    try:
        datetime(year, month, day)
    except ValueError:
        return None

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def normalize_issue(value):
    if value is None:
        return None

    text = re.sub(
        r"\D",
        "",
        str(value)
    )

    if len(text) < 5:
        return None

    return text


def normalize_number(value):
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        digits = []

        for item in value:
            text = re.sub(
                r"\D",
                "",
                str(item)
            )

            if len(text) == 1:
                digits.append(text)

        if len(digits) >= 3:
            return "".join(
                digits[:3]
            )

    text = str(value).strip()

    separated = re.findall(
        r"(?<!\d)(\d)(?!\d)",
        text
    )

    if len(separated) >= 3:
        return "".join(
            separated[:3]
        )

    digits = re.sub(
        r"\D",
        "",
        text
    )

    if len(digits) == 3:
        return digits

    return None


def extract_draws(raw):
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
        "drawNumberAppear",
        "drawNumberSize",
        "drawNumbers",
        "numbers",
        "number",
        "winningNumbers",
    ]

    draws = []

    for item in walk_objects(raw):
        date_raw = first_value(
            item,
            date_keys
        )

        issue_raw = first_value(
            item,
            issue_keys
        )

        number_raw = first_value(
            item,
            number_keys
        )

        date = normalize_date(
            date_raw
        )

        issue = normalize_issue(
            issue_raw
        )

        number = normalize_number(
            number_raw
        )

        if date and issue and number:
            draws.append({
                "date": date,
                "issue": issue,
                "number": number,
            })

    unique = {}

    for row in draws:
        unique[row["issue"]] = row

    return list(
        unique.values()
    )


def fetch_month(year, month):
    print(
        f"抓取 {year}-{month:02d}"
    )

    crawler = TaiwanLotteryCrawler()

    raw = crawler.lotto3d([
        str(year),
        f"{month:02d}",
    ])

    rows = extract_draws(raw)

    print(
        f"取得 {len(rows)} 期"
    )

    return rows

def fetch_latest_official():
    now = datetime.now()

    month = now.strftime("%Y-%m")

    url = (
        "https://api.taiwanlottery.com/"
        "TLCAPIWeB/Lottery/3DResult"
        f"?period&month={month}&pageNum=1&pageSize=50"
    )

    print("抓取台彩官方最新三星彩資料")

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    response.raise_for_status()

    data = response.json()

    if data.get("rtCode") != 0:
        raise RuntimeError(
            f"台彩 API 回傳異常：{data.get('rtCode')}"
        )

    content = data.get("content", {})

    raw_rows = content.get(
        "lotto3DRes",
        []
    )

    rows = extract_draws(
        raw_rows
    )

    print(
        f"官方最新來源取得 {len(rows)} 期"
    )

    return rows
def save_rows(rows):
    unique = {}

    for row in rows:
        date = row.get("date")
        issue = row.get("issue")
        number = row.get("number")

        if not date:
            continue

        if not issue:
            continue

        if not number:
            continue

        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            date
        ):
            continue

        if not issue.isdigit():
            continue

        if not re.fullmatch(
            r"\d{3}",
            number
        ):
            continue

        unique[issue] = {
            "date": date,
            "issue": issue,
            "number": number,
        }

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda row: (
            row["date"],
            int(row["issue"]),
        ),
        reverse=True,
    )

    with CSV_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=HEADERS
        )

        writer.writeheader()
        writer.writerows(result)

    return result


def main():
    existing = load_existing()

    now = datetime.now()

    print(
        f"現有資料：{len(existing)} 期"
    )

    if existing:
        if now.month == 1:
            start_year = now.year - 1
            start_month = 12
        else:
            start_year = now.year
            start_month = now.month - 1

        print(
            "更新最近兩個月份"
        )

    else:
        start_year = 2024
        start_month = 1

        print(
            "首次建立資料庫"
        )

    all_rows = existing.copy()
    success_months = 0
    try:
        latest_rows = fetch_latest_official()

        if latest_rows:
            all_rows.extend(latest_rows)

    except Exception as exc:
        print(
            f"官方最新來源失敗：{exc}",
            file=sys.stderr
        )
    for year, month in month_range(
        start_year,
        start_month,
        now.year,
        now.month,
    ):
        try:
            rows = fetch_month(
                year,
                month
            )

            if rows:
                all_rows.extend(rows)
                success_months += 1

        except Exception as exc:
            print(
                (
                    f"{year}-{month:02d} "
                    f"抓取失敗：{exc}"
                ),
                file=sys.stderr
            )

    if success_months == 0:
        if existing:
            print(
                "沒有取得新資料，"
                "保留原 draws.csv"
            )
            return

        raise RuntimeError(
            "沒有取得任何有效資料"
        )

    saved = save_rows(
        all_rows
    )

    if not saved:
        raise RuntimeError(
            "沒有有效資料可寫入"
        )

    latest = saved[0]

    print("")
    print("更新完成")
    print(
        f"總期數：{len(saved)}"
    )
    print(
        (
            f"最新："
            f"{latest['date']} "
            f"{latest['issue']} "
            f"{latest['number']}"
        )
    )


if __name__ == "__main__":
    main()
