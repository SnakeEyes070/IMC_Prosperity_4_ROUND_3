"""Analyze Round 3 capsule data and print recommended strategy parameters."""

from __future__ import annotations

import csv
import math
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


SIGMA = 0.235
RISK_FREE_RATE = 0.0
TIME_TO_EXPIRY = 5.0 / 365.0
OPTION_KEYWORDS = ("VOUCHER", "OPTION", "COUPON")
OPTION_STRIKE_RE = re.compile(r"^(?P<base>.+?)[_-](?P<strike>\d{3,})$")


@dataclass
class QuoteRow:
    """Normalized quote data for one product at one timestamp."""

    day: int
    timestamp: int
    product: str
    best_bid: Optional[int]
    best_ask: Optional[int]
    bid_volume_1: int
    ask_volume_1: int
    mid_price: float

    @property
    def spread(self) -> Optional[float]:
        """Return the top-of-book spread when both sides exist."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return float(self.best_ask - self.best_bid)


def print_error(message: str) -> None:
    """Print a clear error message to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)


def project_root() -> Path:
    """Return the project root based on the location of this script."""
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Return the data directory."""
    return project_root() / "data"


def safe_int(value: str) -> Optional[int]:
    """Parse an integer field when present."""
    text = str(value).strip()
    if not text:
        return None
    return int(float(text))


def safe_float(value: str) -> Optional[float]:
    """Parse a float field when present."""
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def median_or_default(values: Sequence[float], default: float) -> float:
    """Return the median of a non-empty list or a default."""
    return statistics.median(values) if values else default


def percentile(values: Sequence[float], fraction: float, default: float) -> float:
    """Return a simple linear-interpolated percentile."""
    if not values:
        return default
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = fraction * (len(ordered) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def product_alias(product: str) -> str:
    """Create a short uppercase alias suitable for parameter names."""
    upper = product.upper()
    if upper.isalpha() and len(upper) <= 5:
        return upper
    parts = [part for part in re.split(r"[_\W]+", upper) if part]
    if not parts:
        return upper[:5]
    alias = "".join(part[0] for part in parts)
    digits = "".join(ch for ch in upper if ch.isdigit())
    combined = alias + digits
    return combined[:8] if combined else upper[:8]


def load_quotes(days: Iterable[int] = (0, 1, 2)) -> List[QuoteRow]:
    """Load the Round 3 price CSVs from ../data/."""
    quotes: List[QuoteRow] = []

    for day in days:
        price_path = data_dir() / f"prices_round_3_day_{day}.csv"
        if not price_path.exists():
            raise FileNotFoundError(f"Missing price file: {price_path}")

        with price_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            expected = {"day", "timestamp", "product", "bid_price_1", "ask_price_1", "mid_price"}
            if reader.fieldnames is None or not expected.issubset(set(reader.fieldnames)):
                raise ValueError(f"Unexpected schema in {price_path}")

            for row in reader:
                product = row.get("product", "").strip()
                if not product:
                    continue

                best_bid = safe_int(row.get("bid_price_1", ""))
                best_ask = safe_int(row.get("ask_price_1", ""))
                bid_volume_1 = abs(safe_int(row.get("bid_volume_1", "")) or 0)
                ask_volume_1 = abs(safe_int(row.get("ask_volume_1", "")) or 0)
                mid_price = safe_float(row.get("mid_price", ""))
                if mid_price is None:
                    if best_bid is not None and best_ask is not None:
                        mid_price = (best_bid + best_ask) / 2.0
                    elif best_bid is not None:
                        mid_price = float(best_bid)
                    elif best_ask is not None:
                        mid_price = float(best_ask)
                    else:
                        continue

                quotes.append(
                    QuoteRow(
                        day=int(float(row["day"])),
                        timestamp=int(float(row["timestamp"])),
                        product=product,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        bid_volume_1=bid_volume_1,
                        ask_volume_1=ask_volume_1,
                        mid_price=mid_price,
                    )
                )

    if not quotes:
        raise ValueError("No quote rows were loaded from ../data/")
    return quotes


def grouped_quotes(quotes: Iterable[QuoteRow]) -> Dict[str, List[QuoteRow]]:
    """Group quote rows by product."""
    grouped: Dict[str, List[QuoteRow]] = defaultdict(list)
    for quote in quotes:
        grouped[quote.product].append(quote)
    for product_rows in grouped.values():
        product_rows.sort(key=lambda row: (row.day, row.timestamp))
    return dict(grouped)


def is_option_product(product: str) -> bool:
    """Infer whether a symbol looks like a voucher or option."""
    upper = product.upper()
    if any(keyword in upper for keyword in OPTION_KEYWORDS):
        return True
    return bool(OPTION_STRIKE_RE.match(upper))


def detect_option_strike(product: str) -> Optional[Tuple[str, int]]:
    """Extract a product family and strike if the symbol is option-like."""
    match = OPTION_STRIKE_RE.match(product.upper())
    if not match:
        return None
    return match.group("base"), int(match.group("strike"))


def normal_cdf(value: float) -> float:
    """Compute the standard normal CDF."""
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def black_scholes_call(spot: float, strike: float, sigma: float, rate: float, tenor: float) -> Tuple[float, float]:
    """Return Black-Scholes call fair value and delta."""
    if spot <= 0 or strike <= 0 or sigma <= 0 or tenor <= 0:
        intrinsic = max(0.0, spot - strike)
        delta = 1.0 if spot > strike else 0.0
        return intrinsic, delta

    sqrt_t = math.sqrt(tenor)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * tenor) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    fair = spot * normal_cdf(d1) - strike * math.exp(-rate * tenor) * normal_cdf(d2)
    delta = normal_cdf(d1)
    return fair, delta


def print_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    """Print a simple ASCII table."""
    string_rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(str(header)) for header in headers]
    for row in string_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    header_line = " | ".join(str(header).ljust(widths[index]) for index, header in enumerate(headers))
    separator = "-+-".join("-" * width for width in widths)
    print(header_line)
    print(separator)
    for row in string_rows:
        print(" | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def recommend_delta_one_parameters(rows: Sequence[QuoteRow], alias: str) -> List[Tuple[str, str, str]]:
    """Generate market-making style parameters for a non-option product."""
    spreads = [quote.spread for quote in rows if quote.spread is not None]
    spreads = [spread for spread in spreads if spread is not None]
    mids = [quote.mid_price for quote in rows]
    top_sizes = [max(quote.bid_volume_1, quote.ask_volume_1) for quote in rows if max(quote.bid_volume_1, quote.ask_volume_1) > 0]

    moves = [abs(curr - prev) for prev, curr in zip(mids, mids[1:]) if curr != prev]
    halfspread = max(1, int(round(median_or_default(spreads, 2.0) / 2.0)))
    refresh_tick = max(1, int(round(percentile(moves, 0.35, 1.0))))
    order_size = max(1, int(round(percentile(top_sizes, 0.40, 5.0) / 2.0)))

    return [
        (f"{alias}_HALFSPREAD", str(halfspread), "Median quoted spread divided by two"),
        (f"{alias}_REFRESH_TICK", str(refresh_tick), "Typical non-zero mid-price move size"),
        (f"{alias}_ORDER_SIZE", str(order_size), "Roughly half of the lower-book top size"),
    ]


def similarity_score(option_base: str, candidate_product: str) -> Tuple[int, int]:
    """Score a candidate underlying product for an option family."""
    base = option_base.upper()
    product = candidate_product.upper()
    alias = product_alias(candidate_product)

    common_prefix = 0
    for left, right in zip(base, product):
        if left != right:
            break
        common_prefix += 1

    alias_prefix = 0
    for left, right in zip(base, alias):
        if left != right:
            break
        alias_prefix += 1

    return alias_prefix, common_prefix


def guess_underlying(option_base: str, all_products: Sequence[str]) -> Optional[str]:
    """Guess the underlying product for an option family."""
    candidates = [product for product in all_products if not is_option_product(product)]
    if not candidates:
        return None

    preferred = []
    for product in candidates:
        if option_base in product.upper():
            preferred.append(product)

    if preferred:
        preferred.sort(key=lambda product: (-len(product), product))
        return preferred[0]

    ranked = sorted(candidates, key=lambda product: similarity_score(option_base, product), reverse=True)
    best = ranked[0]
    return best if similarity_score(option_base, best) > (0, 0) else None


def analyze_option_family(
    family_base: str,
    family_rows: Sequence[QuoteRow],
    all_quotes: Dict[str, List[QuoteRow]],
    all_products: Sequence[str],
) -> Tuple[List[Tuple[str, str, str]], List[List[str]]]:
    """Recommend option parameters and compute per-strike BS mispricing."""
    alias = family_base.upper() if len(family_base) <= 5 else product_alias(family_base)

    underlying = guess_underlying(family_base, all_products)
    if underlying is None or underlying not in all_quotes:
        return [], [[alias, "N/A", "N/A", "N/A", "Unable to identify underlying product"]]

    underlying_lookup = {(row.day, row.timestamp): row.mid_price for row in all_quotes[underlying]}
    grouped_by_strike: Dict[int, List[QuoteRow]] = defaultdict(list)
    deltas: List[float] = []
    underpricing: List[float] = []
    overpricing: List[float] = []
    strike_rows: List[List[str]] = []

    for row in family_rows:
        parsed = detect_option_strike(row.product)
        if parsed is None:
            continue
        _, strike = parsed
        grouped_by_strike[strike].append(row)

    for strike, rows in sorted(grouped_by_strike.items()):
        signed_mispricings: List[float] = []
        absolute_mispricings: List[float] = []

        for row in rows:
            spot = underlying_lookup.get((row.day, row.timestamp))
            if spot is None:
                continue
            fair_value, delta = black_scholes_call(
                spot=spot,
                strike=float(strike),
                sigma=SIGMA,
                rate=RISK_FREE_RATE,
                tenor=TIME_TO_EXPIRY,
            )
            mispricing = row.mid_price - fair_value
            signed_mispricings.append(mispricing)
            absolute_mispricings.append(abs(mispricing))
            deltas.append(delta)

            if mispricing < 0:
                underpricing.append(abs(mispricing))
            elif mispricing > 0:
                overpricing.append(mispricing)

        if not signed_mispricings:
            strike_rows.append([alias, str(strike), "N/A", "N/A", "Missing underlying overlap"])
            continue

        avg_signed = statistics.mean(signed_mispricings)
        avg_abs = statistics.mean(absolute_mispricings)
        flag = "FLAG > 4 ticks" if avg_abs > 4.0 else ""
        strike_rows.append(
            [
                alias,
                str(strike),
                f"{avg_signed:.2f}",
                f"{avg_abs:.2f}",
                flag,
            ]
        )

    fair_slope = statistics.mean(deltas) if deltas else 0.5
    buy_tol = max(1, int(round(percentile(underpricing, 0.65, 2.0))))
    sell_tol = max(1, int(round(percentile(overpricing, 0.65, 2.0))))

    recommended = [
        (f"{alias}_FAIR_SLOPE", f"{fair_slope:.4f}", f"Average Black-Scholes delta using sigma={SIGMA}"),
        (f"{alias}_BUY_TOL", str(buy_tol), "65th percentile of underpricing in ticks"),
        (f"{alias}_SELL_TOL", str(sell_tol), "65th percentile of overpricing in ticks"),
    ]
    return recommended, strike_rows


def main() -> int:
    """Load the capsule, print recommended parameters, and report voucher mispricing."""
    try:
        quotes = load_quotes()
    except (FileNotFoundError, ValueError) as exc:
        print_error(str(exc))
        return 1

    by_product = grouped_quotes(quotes)
    all_products = sorted(by_product)

    recommended_rows: List[Tuple[str, str, str]] = []
    option_family_rows: Dict[str, List[QuoteRow]] = defaultdict(list)

    for product, rows in by_product.items():
        if is_option_product(product):
            parsed = detect_option_strike(product)
            family_base = parsed[0] if parsed is not None else product
            option_family_rows[family_base].extend(rows)
        else:
            recommended_rows.extend(recommend_delta_one_parameters(rows, product_alias(product)))

    mispricing_rows: List[List[str]] = []
    if option_family_rows:
        for family_base in sorted(option_family_rows):
            family_recommended, family_mispricing = analyze_option_family(
                family_base=family_base,
                family_rows=option_family_rows[family_base],
                all_quotes=by_product,
                all_products=all_products,
            )

            recommended_rows.extend(family_recommended)
            mispricing_rows.extend(family_mispricing)

    recommended_rows.sort(key=lambda row: row[0])

    print("Recommended Parameters")
    print_table(["Parameter", "Value", "Rationale"], recommended_rows)
    print()

    if mispricing_rows:
        print(f"Voucher Mispricing (sigma={SIGMA}, r={RISK_FREE_RATE}, T={TIME_TO_EXPIRY:.6f})")
        print_table(["Alias", "Strike", "Avg Mispricing", "Avg Abs Mispricing", "Flag"], mispricing_rows)
    else:
        print("Voucher Mispricing")
        print("No option-like products were detected in ../data/.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
