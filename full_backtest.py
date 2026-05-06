"""Self-contained local backtester for IMC Prosperity 4 Round 3 data."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import time
import types
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


Symbol = str
Time = int
UserId = str
Position = int

OPTION_NAME_RE = re.compile(r"(VOUCHER|OPTION|COUPON)", re.IGNORECASE)
NUMERIC_SUFFIX_RE = re.compile(r"(?:_|-)\d{2,}$")


@dataclass
class Listing:
    """Minimal listing metadata compatible with common Prosperity traders."""

    symbol: Symbol
    product: str
    denomination: str = "XIRECS"


@dataclass
class Order:
    """Represents a single order produced by a trader."""

    symbol: Symbol
    price: int
    quantity: int


@dataclass
class OrderDepth:
    """Represents visible buy and sell liquidity for one product."""

    buy_orders: Dict[int, int] = field(default_factory=dict)
    sell_orders: Dict[int, int] = field(default_factory=dict)


@dataclass
class Trade:
    """Represents a filled trade."""

    symbol: Symbol
    price: int
    quantity: int
    buyer: Optional[UserId] = None
    seller: Optional[UserId] = None
    timestamp: Time = 0


@dataclass
class ConversionObservation:
    """Compatibility placeholder for traders that inspect observations."""

    bidPrice: float = 0.0
    askPrice: float = 0.0
    transportFees: float = 0.0
    exportTariff: float = 0.0
    importTariff: float = 0.0
    sunlight: float = 0.0
    humidity: float = 0.0


@dataclass
class Observation:
    """Compatibility container for plain and conversion observations."""

    plainValueObservations: Dict[str, float] = field(default_factory=dict)
    conversionObservations: Dict[str, ConversionObservation] = field(default_factory=dict)


class ProsperityEncoder(json.JSONEncoder):
    """JSON encoder that understands the lightweight dataclasses in this file."""

    def default(self, obj: Any) -> Any:
        """Convert dataclasses into plain dictionaries."""
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return super().default(obj)


@dataclass
class TradingState:
    """Trading state passed into the trader at each timestamp."""

    traderData: str
    timestamp: Time
    listings: Dict[Symbol, Listing]
    order_depths: Dict[Symbol, OrderDepth]
    own_trades: Dict[Symbol, List[Trade]]
    market_trades: Dict[Symbol, List[Trade]]
    position: Dict[Symbol, Position]
    observations: Observation = field(default_factory=Observation)

    def toJSON(self) -> str:
        """Serialize the trading state for debugging."""
        return json.dumps(self, cls=ProsperityEncoder, separators=(",", ":"))


def print_error(message: str) -> None:
    """Print a clear error message to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)


def safe_int(value: str) -> Optional[int]:
    """Parse a CSV numeric field into an integer when present."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(float(text))


def safe_float(value: str) -> Optional[float]:
    """Parse a CSV numeric field into a float when present."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def add_book_level(book: Dict[int, int], price: Optional[int], quantity: Optional[int]) -> None:
    """Accumulate a price level into a book side."""
    if price is None or quantity is None or quantity == 0:
        return
    book[price] = book.get(price, 0) + quantity


def build_order_depth(row: Dict[str, str]) -> OrderDepth:
    """Build an order book snapshot from one CSV row."""
    depth = OrderDepth()

    for level in range(1, 4):
        bid_price = safe_int(row.get(f"bid_price_{level}", ""))
        bid_volume = safe_int(row.get(f"bid_volume_{level}", ""))
        ask_price = safe_int(row.get(f"ask_price_{level}", ""))
        ask_volume = safe_int(row.get(f"ask_volume_{level}", ""))

        if bid_volume is not None:
            bid_volume = abs(bid_volume)
        if ask_volume is not None:
            ask_volume = -abs(ask_volume)

        add_book_level(depth.buy_orders, bid_price, bid_volume)
        add_book_level(depth.sell_orders, ask_price, ask_volume)

    return depth


def is_option_product(product: str) -> bool:
    """Infer whether a product is option-like for hardcoded limit selection."""
    upper = product.upper()
    return bool(OPTION_NAME_RE.search(upper) or NUMERIC_SUFFIX_RE.search(upper))


def position_limit_for(product: str) -> int:
    """Return the requested hardcoded position limit for a product."""
    return 300 if is_option_product(product) else 200


def install_compat_datamodel() -> None:
    """Expose the local datamodel under common import paths used by traders."""
    datamodel = types.ModuleType("datamodel")
    datamodel.Symbol = Symbol
    datamodel.Time = Time
    datamodel.UserId = UserId
    datamodel.Position = Position
    datamodel.Listing = Listing
    datamodel.Order = Order
    datamodel.OrderDepth = OrderDepth
    datamodel.Trade = Trade
    datamodel.Observation = Observation
    datamodel.ConversionObservation = ConversionObservation
    datamodel.TradingState = TradingState
    datamodel.ProsperityEncoder = ProsperityEncoder

    sys.modules["datamodel"] = datamodel

    for package_name in ("prosperity3bt", "prosperity4bt"):
        package = types.ModuleType(package_name)
        package.__path__ = []  # type: ignore[attr-defined]
        package.datamodel = datamodel
        sys.modules[package_name] = package
        sys.modules[f"{package_name}.datamodel"] = datamodel


def project_root() -> Path:
    """Return the project root based on the location of this script."""
    return Path(__file__).resolve().parent.parent


def traders_dir() -> Path:
    """Return the traders directory."""
    return project_root() / "traders"


def data_dir() -> Path:
    """Return the data directory."""
    return project_root() / "data"


def load_trader_class(module_name: str) -> type:
    """Load the Trader class from traders/<module_name>.py."""
    trader_path = traders_dir() / f"{module_name}.py"
    if not trader_path.exists():
        raise FileNotFoundError(f"Trader file not found: {trader_path}")

    install_compat_datamodel()

    spec = importlib.util.spec_from_file_location(module_name, trader_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {trader_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    trader_class = getattr(module, "Trader", None)
    if trader_class is None:
        raise AttributeError(f"No Trader class found in {trader_path}")
    return trader_class


def load_price_groups(day: int) -> Tuple[List[int], Dict[int, Dict[str, OrderDepth]], Dict[int, Dict[str, float]], List[str]]:
    """Load one day of price data grouped by timestamp."""
    price_path = data_dir() / f"prices_round_3_day_{day}.csv"
    if not price_path.exists():
        raise FileNotFoundError(f"Missing price file: {price_path}")

    grouped_depths: Dict[int, Dict[str, OrderDepth]] = {}
    grouped_mids: Dict[int, Dict[str, float]] = {}
    products_seen: set[str] = set()

    with price_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        expected = {"timestamp", "product", "bid_price_1", "ask_price_1"}
        if reader.fieldnames is None or not expected.issubset(set(reader.fieldnames)):
            raise ValueError(f"Unexpected schema in {price_path}")

        for row in reader:
            timestamp_text = row.get("timestamp", "").strip()
            product = row.get("product", "").strip()
            if not timestamp_text or not product:
                continue

            timestamp = int(float(timestamp_text))
            products_seen.add(product)

            grouped_depths.setdefault(timestamp, {})[product] = build_order_depth(row)

            mid_price = safe_float(row.get("mid_price", ""))
            if mid_price is None:
                depth = grouped_depths[timestamp][product]
                best_bid = max(depth.buy_orders) if depth.buy_orders else None
                best_ask = min(depth.sell_orders) if depth.sell_orders else None
                if best_bid is not None and best_ask is not None:
                    mid_price = (best_bid + best_ask) / 2.0
                elif best_bid is not None:
                    mid_price = float(best_bid)
                elif best_ask is not None:
                    mid_price = float(best_ask)
                else:
                    mid_price = 0.0

            grouped_mids.setdefault(timestamp, {})[product] = mid_price

    return sorted(grouped_depths), grouped_depths, grouped_mids, sorted(products_seen)


def best_bid_ask(depth: OrderDepth) -> Tuple[Optional[int], int, Optional[int], int]:
    """Return best bid, bid size, best ask, and ask size."""
    best_bid = max(depth.buy_orders) if depth.buy_orders else None
    best_ask = min(depth.sell_orders) if depth.sell_orders else None
    bid_size = depth.buy_orders.get(best_bid, 0) if best_bid is not None else 0
    ask_size = abs(depth.sell_orders.get(best_ask, 0)) if best_ask is not None else 0
    return best_bid, bid_size, best_ask, ask_size


def extract_orders_and_trader_data(result: Any, prior_trader_data: str) -> Tuple[Dict[str, List[Order]], str]:
    """Normalize the trader return value into orders and next traderData."""
    if isinstance(result, tuple):
        orders = result[0] if len(result) >= 1 else {}
        trader_data = result[2] if len(result) >= 3 else prior_trader_data
    elif isinstance(result, list):
        orders = result[0] if result else {}
        trader_data = result[2] if len(result) >= 3 else prior_trader_data
    else:
        orders = result
        trader_data = prior_trader_data

    if not isinstance(orders, dict):
        raise TypeError("Trader.run() must return a dict or tuple whose first item is a dict")

    next_trader_data = "" if trader_data is None else str(trader_data)
    normalized: Dict[str, List[Order]] = {}
    for product, product_orders in orders.items():
        normalized[str(product)] = list(product_orders or [])

    return normalized, next_trader_data


def record_trade(
    own_trades: Dict[str, List[Trade]],
    symbol: str,
    timestamp: int,
    price: int,
    quantity: int,
    buyer: Optional[str],
    seller: Optional[str],
) -> None:
    """Append a filled trade to the running own-trades history."""
    own_trades.setdefault(symbol, []).append(
        Trade(
            symbol=symbol,
            price=price,
            quantity=quantity,
            buyer=buyer,
            seller=seller,
            timestamp=timestamp,
        )
    )


def process_orders(
    timestamp: int,
    orders_by_product: Dict[str, List[Order]],
    order_depths: Dict[str, OrderDepth],
    positions: Dict[str, int],
    own_trades: Dict[str, List[Trade]],
) -> float:
    """Fill aggressive orders against the visible best price only."""
    cash_delta = 0.0

    for declared_product, orders in orders_by_product.items():
        for order in orders:
            symbol = str(getattr(order, "symbol", declared_product))
            depth = order_depths.get(symbol)
            if depth is None:
                continue

            best_bid, bid_size, best_ask, ask_size = best_bid_ask(depth)
            limit = position_limit_for(symbol)
            current_position = positions.get(symbol, 0)
            quantity = int(getattr(order, "quantity", 0))
            price = int(getattr(order, "price", 0))

            if quantity > 0 and best_ask is not None and price >= best_ask:
                allowed = max(0, limit - current_position)
                fill_qty = min(quantity, ask_size, allowed)
                if fill_qty > 0:
                    positions[symbol] = current_position + fill_qty
                    cash_delta -= fill_qty * best_ask
                    record_trade(
                        own_trades,
                        symbol=symbol,
                        timestamp=timestamp,
                        price=best_ask,
                        quantity=fill_qty,
                        buyer="SUBMISSION",
                        seller="BOOK",
                    )
                    current_position = positions[symbol]

            elif quantity < 0 and best_bid is not None and price <= best_bid:
                allowed = max(0, limit + current_position)
                fill_qty = min(abs(quantity), bid_size, allowed)
                if fill_qty > 0:
                    positions[symbol] = current_position - fill_qty
                    cash_delta += fill_qty * best_bid
                    record_trade(
                        own_trades,
                        symbol=symbol,
                        timestamp=timestamp,
                        price=best_bid,
                        quantity=fill_qty,
                        buyer="BOOK",
                        seller="SUBMISSION",
                    )

    return cash_delta


def mark_to_market(cash: float, positions: Dict[str, int], last_mid_prices: Dict[str, float]) -> float:
    """Convert cash plus open positions into day-end PnL."""
    inventory_value = 0.0
    for product, quantity in positions.items():
        inventory_value += quantity * last_mid_prices.get(product, 0.0)
    return cash + inventory_value


def simulate_day(day: int, trader_class: type) -> float:
    """Run the trader over one full day of grouped timestamps."""
    timestamps, grouped_depths, grouped_mids, products = load_price_groups(day)
    trader = trader_class()

    listings = {product: Listing(symbol=product, product=product) for product in products}
    positions: Dict[str, int] = {}
    own_trades: Dict[str, List[Trade]] = {product: [] for product in products}
    market_trades: Dict[str, List[Trade]] = {product: [] for product in products}
    cash = 0.0
    trader_data = ""
    last_mid_prices: Dict[str, float] = {}

    for timestamp in timestamps:
        order_depths = grouped_depths[timestamp]
        last_mid_prices.update(grouped_mids.get(timestamp, {}))

        state = TradingState(
            traderData=trader_data,
            timestamp=timestamp,
            listings=listings,
            order_depths=order_depths,
            own_trades=own_trades,
            market_trades=market_trades,
            position=dict(positions),
            observations=Observation(),
        )

        try:
            trader_result = trader.run(state)
        except Exception as exc:
            raise RuntimeError(f"Trader crashed on day {day} at timestamp {timestamp}: {exc}") from exc

        orders_by_product, trader_data = extract_orders_and_trader_data(trader_result, trader_data)
        cash += process_orders(
            timestamp=timestamp,
            orders_by_product=orders_by_product,
            order_depths=order_depths,
            positions=positions,
            own_trades=own_trades,
        )

    return mark_to_market(cash=cash, positions=positions, last_mid_prices=last_mid_prices)


def main(argv: List[str]) -> int:
    """Parse arguments, run the backtest, and print day-by-day PnL."""
    if len(argv) != 2:
        print("Usage: python full_backtest.py <trader_module_name>", file=sys.stderr)
        return 1

    module_name = argv[1]
    start_time = time.perf_counter()

    try:
        trader_class = load_trader_class(module_name)
        day_pnls = {day: simulate_day(day, trader_class) for day in (0, 1, 2)}
    except FileNotFoundError as exc:
        print_error(str(exc))
        return 1
    except (ImportError, AttributeError, ValueError, RuntimeError, TypeError) as exc:
        print_error(str(exc))
        return 1

    total_pnl = sum(day_pnls.values())
    elapsed = time.perf_counter() - start_time

    for day in (0, 1, 2):
        print(f"Day {day} PnL: {day_pnls[day]:.2f}")
    print(f"Total PnL: {total_pnl:.2f}")
    print(f"Execution time (seconds): {elapsed:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
