
import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DRAWS = Path("draws.csv")
PREDICTIONS = Path("predictions.csv")
TZ = ZoneInfo("Asia/Taipei")

WINDOW = 30
TOP_N = 20
HOT_WEIGHT = 0.4
MISS_WEIGHT = 0.6
STRATEGY = "hot40_miss60_top20"

FIELDS = [
    "target_date", "target_issue", "created_at",
    "strategy", "window", "rank", "number",
    "status", "actual_number", "settled_at"
]


def next_draw_date(now):
    day = now.date()
    if now.hour >= 20:
        day += timedelta(days=1)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return day.isoformat()


def read_draws(target):
    with DRAWS.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    rows = [
        r for r in rows
        if r["date"] < target
        and len(r["number"]) == 3
        and r["number"].isdigit()
    ]
    rows.sort(key=lambda r: (r["date"], r["issue"]), reverse=True)
    return rows


def score_digits(rows, position):
    seq = [r["number"][position] for r in rows]
    counts = {d: seq.count(d) for d in "0123456789"}
    misses = {
        d: next((i for i, v in enumerate(seq) if v == d), len(seq))
        for d in "0123456789"
    }

    max_count = max(max(counts.values()), 1)
    max_miss = max(max(misses.values()), 1)

    return {
        d: (
            HOT_WEIGHT * counts[d] / max_count
            + MISS_WEIGHT * misses[d] / max_miss
        )
        for d in "0123456789"
    }


def main():
    now = datetime.now(TZ)
    target = next_draw_date(now)

    if not PREDICTIONS.exists():
        raise RuntimeError("找不到 predictions.csv")

    with PREDICTIONS.open(
        encoding="utf-8-sig", newline=""
    ) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise RuntimeError("predictions.csv 欄位格式不符")
        existing = list(reader)

    if any(
        r["target_date"] == target
        and r["strategy"] == STRATEGY
        and r["window"] == str(WINDOW)
        for r in existing
    ):
        print("該日期已有預測，保留原紀錄")
        return

    history = read_draws(target)
    if len(history) < WINDOW:
        raise RuntimeError("歷史資料不足")

    if (
        datetime.fromisoformat(history[0]["date"]).date()
        < datetime.fromisoformat(target).date() - timedelta(days=3)
    ):
        raise RuntimeError("歷史資料過舊，停止產生預測")

    history = history[:WINDOW]
    scores = [score_digits(history, p) for p in range(3)]

    candidates = []
    for h in "0123456789":
        for t in "0123456789":
            for o in "0123456789":
                number = h + t + o
                score = (
                    scores[0][h] + scores[1][t] + scores[2][o]
                ) / 3
                candidates.append((number, score))

    candidates.sort(key=lambda x: (-x[1], x[0]))
    created = now.isoformat(timespec="seconds")

    new_rows = []
    for rank, (number, _) in enumerate(candidates[:TOP_N], 1):
        new_rows.append({
            "target_date": target,
            "target_issue": "",
            "created_at": created,
            "strategy": STRATEGY,
            "window": str(WINDOW),
            "rank": str(rank),
            "number": number,
            "status": "pending",
            "actual_number": "",
            "settled_at": ""
        })

    with PREDICTIONS.open(
        "a", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerows(new_rows)

    print(f"已建立 {target} 的 {TOP_N} 組測試號碼")
    print(f"建立時間：{created}")


if __name__ == "__main__":
    main()
