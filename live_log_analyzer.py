"""Extract trades and cumulative PnL from a Prosperity submission log JSON blob."""

from __future__ import annotations

import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def print_error(message: str) -> None:
    """Print a clear error message to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)


def load_log(path: Path) -> Dict[str, object]:
    """Load and parse the JSON log file."""
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse JSON log: {exc}") from exc


def parse_activities_log(activities_log: str) -> List[Dict[str, str]]:
    """Parse the embedded semicolon-delimited activities log."""
    if not activities_log.strip():
        return []
    reader = csv.DictReader(io.StringIO(activities_log), delimiter=";")
    return [row for row in reader]


def display_timestamp(row: Dict[str, str], multi_day: bool) -> str:
    """Render a timestamp field that stays readable across multi-day logs."""
    timestamp = str(row.get("timestamp", "")).strip()
    day = str(row.get("day", "")).strip()
    if multi_day and day:
        return f"{day}:{timestamp}"
    return timestamp


def cumulative_pnl_rows(activity_rows: Sequence[Dict[str, str]]) -> List[Tuple[str, float]]:
    """Aggregate cumulative PnL across products per timestamp."""
    days = {str(row.get("day", "")).strip() for row in activity_rows if str(row.get("day", "")).strip()}
    multi_day = len(days) > 1
    totals: Dict[Tuple[str, str], float] = {}

    for row in activity_rows:
        timestamp = str(row.get("timestamp", "")).strip()
        day = str(row.get("day", "")).strip()
        pnl_text = str(row.get("profit_and_loss", "")).strip()
        if not timestamp or not pnl_text:
            continue
        key = (day, timestamp)
        totals[key] = totals.get(key, 0.0) + float(pnl_text)

    ordered = sorted(totals.items(), key=lambda item: (float(item[0][0]) if item[0][0] else 0.0, float(item[0][1])))
    return [
        (f"{day}:{timestamp}" if multi_day and day else timestamp, total)
        for (day, timestamp), total in ordered
    ]


def mid_price_lookups(
    activity_rows: Sequence[Dict[str, str]],
) -> Tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str], float]]:
    """Build exact and fallback mid-price lookups from the activities log."""
    exact_lookup: Dict[Tuple[str, str, str], float] = {}
    fallback_lookup: Dict[Tuple[str, str], float] = {}
    for row in activity_rows:
        day = str(row.get("day", "")).strip()
        timestamp = str(row.get("timestamp", "")).strip()
        symbol = str(row.get("product", "")).strip()
        mid_text = str(row.get("mid_price", "")).strip()
        if not timestamp or not symbol or not mid_text:
            continue
        try:
            mid_value = float(mid_text)
        except ValueError:
            continue
        exact_lookup[(day, timestamp, symbol)] = mid_value
        fallback_lookup[(timestamp, symbol)] = mid_value
    return exact_lookup, fallback_lookup


def trade_score(
    trade: Dict[str, object],
    exact_mid_lookup: Dict[Tuple[str, str, str], float],
    fallback_mid_lookup: Dict[Tuple[str, str], float],
) -> Optional[float]:
    """Compute an immediate edge score for a submission-side trade."""
    buyer = str(trade.get("buyer", "") or "")
    seller = str(trade.get("seller", "") or "")
    symbol = str(trade.get("symbol", "") or "")
    timestamp = str(trade.get("timestamp", "") or "")
    day = str(trade.get("day", "") or "")

    if buyer != "SUBMISSION" and seller != "SUBMISSION":
        return None

    price = float(trade.get("price", 0.0) or 0.0)
    quantity = float(trade.get("quantity", 0.0) or 0.0)
    mid = exact_mid_lookup.get((day, timestamp, symbol))
    if mid is None:
        mid = fallback_mid_lookup.get((timestamp, symbol))

    if mid is not None:
        if buyer == "SUBMISSION":
            return (mid - price) * quantity
        return (price - mid) * quantity

    if buyer == "SUBMISSION":
        return -price * quantity
    return price * quantity


def best_and_worst_trade(
    trades: Sequence[Dict[str, object]],
    exact_mid_lookup: Dict[Tuple[str, str, str], float],
    fallback_mid_lookup: Dict[Tuple[str, str], float],
) -> Tuple[Optional[Tuple[Dict[str, object], float]], Optional[Tuple[Dict[str, object], float]]]:
    """Return the best and worst submission-side trades."""
    scored = []
    for trade in trades:
        score = trade_score(trade, exact_mid_lookup, fallback_mid_lookup)
        if score is not None:
            scored.append((trade, score))

    if not scored:
        return None, None

    best = max(scored, key=lambda item: item[1])
    worst = min(scored, key=lambda item: item[1])
    return best, worst


def write_trades_csv(path: Path, trades: Sequence[Dict[str, object]]) -> None:
    """Write the trade history into a flat CSV file."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "symbol", "price", "quantity", "buyer", "seller"])
        for trade in trades:
            writer.writerow(
                [
                    trade.get("timestamp", ""),
                    trade.get("symbol", ""),
                    trade.get("price", ""),
                    trade.get("quantity", ""),
                    trade.get("buyer", ""),
                    trade.get("seller", ""),
                ]
            )


def write_cumulative_pnl_csv(path: Path, rows: Sequence[Tuple[str, float]]) -> None:
    """Write total cumulative PnL over time into a CSV file."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "total_cumulative_pnl"])
        for timestamp, pnl in rows:
            writer.writerow([timestamp, f"{pnl:.6f}"])


def format_trade_summary(label: str, item: Optional[Tuple[Dict[str, object], float]]) -> str:
    """Render one summary line for the best or worst trade."""
    if item is None:
        return f"{label}: N/A"
    trade, score = item
    return (
        f"{label}: {trade.get('symbol', '')} @ t={trade.get('timestamp', '')} "
        f"price={trade.get('price', '')} qty={trade.get('quantity', '')} edge={score:.2f}"
    )


def main(argv: List[str]) -> int:
    """Parse a Prosperity log, export CSVs, and print a summary."""
    if len(argv) != 2:
        print("Usage: python live_log_analyzer.py <path_to_log.json>", file=sys.stderr)
        return 1

    log_path = Path(argv[1]).expanduser().resolve()

    try:
        payload = load_log(log_path)
        activities_raw = str(payload.get("activitiesLog", "") or "")
        activity_rows = parse_activities_log(activities_raw)
        trades = list(payload.get("tradeHistory", []) or [])
    except (FileNotFoundError, ValueError, TypeError) as exc:
        print_error(str(exc))
        return 1

    if not activity_rows:
        print_error("activitiesLog is missing or empty in the provided log")
        return 1

    trades_csv_path = log_path.with_name(f"{log_path.stem}_trades.csv")
    pnl_csv_path = log_path.with_name(f"{log_path.stem}_cumulative_pnl.csv")

    cumulative_rows = cumulative_pnl_rows(activity_rows)
    total_pnl = cumulative_rows[-1][1] if cumulative_rows else 0.0
    trade_counts = Counter(str(trade.get("symbol", "") or "") for trade in trades)
    exact_lookup, fallback_lookup = mid_price_lookups(activity_rows)
    best_trade, worst_trade = best_and_worst_trade(trades, exact_lookup, fallback_lookup)

    write_trades_csv(trades_csv_path, trades)
    write_cumulative_pnl_csv(pnl_csv_path, cumulative_rows)

    print(f"Total PnL: {total_pnl:.2f}")
    print("Trades Per Product:")
    if trade_counts:
        for symbol in sorted(trade_counts):
            print(f"  {symbol}: {trade_counts[symbol]}")
    else:
        print("  No trades found in tradeHistory")
    print(format_trade_summary("Best Single Trade", best_trade))
    print(format_trade_summary("Worst Single Trade", worst_trade))
    print(f"Wrote: {trades_csv_path}")
    print(f"Wrote: {pnl_csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
