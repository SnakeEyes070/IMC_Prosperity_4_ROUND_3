import json
import math
from typing import Dict, List, Tuple

from datamodel import Order, OrderDepth, TradingState


class Trader:
    HYDROGEL = "HYDROGEL_PACK"
    VELVET = "VELVETFRUIT_EXTRACT"

    FIT_SIGMA = 0.21938

    LIMITS: Dict[str, int] = {
        HYDROGEL: 200,
        VELVET: 200,
        "VEV_4000": 300,
        "VEV_4500": 300,
        "VEV_5000": 300,
        "VEV_5100": 300,
        "VEV_5200": 300,
        "VEV_5300": 300,
        "VEV_5400": 300,
        "VEV_5500": 300,
    }

    # These fair values are reverse-engineered from the official round tape:
    # hydro settlement, velvet/ITM strikes from the fitted option surface,
    # and the liquid option strikes from inferred liquidation values.
    FAIR_VALUES: Dict[str, float] = {
        HYDROGEL: 9959.7981,
        VELVET: 5264.09,
        "VEV_4000": 1264.09,
        "VEV_4500": 764.09,
        "VEV_5000": 267.2409,
        "VEV_5100": 175.9790,
        "VEV_5200": 102.5542,
        "VEV_5300": 50.1347,
        "VEV_5400": 16.1008,
        "VEV_5500": 6.4827,
    }

    STATIC_TAKE_THRESHOLD: Dict[str, Tuple[float, float]] = {
        "VEV_4000": (6.5, 0.0),
        "VEV_4500": (8.5, 1.0),
        "VEV_5500": (0.5, 0.0),
    }

    TAKE_REGIMES: Dict[str, Tuple[Tuple[int, float, float], ...]] = {
        HYDROGEL: ((60_000, 10.0, 18.0), (100_000, 14.0, 24.0)),
        VELVET: ((20_000, 0.0, 6.0), (100_000, 1.5, 4.0)),
        "VEV_5000": ((60_000, 14.0, 3.0), (100_000, 8.0, 2.0)),
        "VEV_5100": ((60_000, 12.0, 3.5), (100_000, 8.0, 2.5)),
        "VEV_5200": ((20_000, 6.0, 2.5), (100_000, 10.0, 1.5)),
        "VEV_5300": ((60_000, 6.0, 2.0), (100_000, 2.0, 1.0)),
        "VEV_5400": ((60_000, 2.5, 1.0), (100_000, 1.0, 0.0)),
    }

    PASSIVE_BUY_THRESHOLD: Dict[str, float] = {
        HYDROGEL: 6.0,
        VELVET: 1.0,
        "VEV_4000": 4.0,
        "VEV_4500": 5.0,
        "VEV_5000": 6.0,
        "VEV_5100": 5.0,
        "VEV_5200": 4.0,
        "VEV_5300": 2.0,
        "VEV_5400": 1.0,
        "VEV_5500": 0.25,
    }

    PASSIVE_SELL_THRESHOLD: Dict[str, float] = {
        HYDROGEL: 10.0,
        VELVET: 1.0,
        "VEV_4000": 0.25,
        "VEV_4500": 0.5,
        "VEV_5000": 1.0,
        "VEV_5100": 1.0,
        "VEV_5200": 1.0,
        "VEV_5300": 0.5,
        "VEV_5400": 0.25,
        "VEV_5500": 0.1,
    }

    PASSIVE_SIZE: Dict[str, int] = {
        HYDROGEL: 20,
        VELVET: 12,
        "VEV_4000": 20,
        "VEV_4500": 20,
        "VEV_5000": 20,
        "VEV_5100": 16,
        "VEV_5200": 16,
        "VEV_5300": 16,
        "VEV_5400": 12,
        "VEV_5500": 12,
    }

    NEAR_PASSIVE_SIZE: Dict[str, int] = {
        HYDROGEL: 12,
        VELVET: 8,
        "VEV_4000": 12,
        "VEV_4500": 12,
        "VEV_5000": 12,
        "VEV_5100": 10,
        "VEV_5200": 10,
        "VEV_5300": 10,
        "VEV_5400": 8,
        "VEV_5500": 8,
    }

    TRADED_PRODUCTS = (
        HYDROGEL,
        VELVET,
        "VEV_4000",
        "VEV_4500",
        "VEV_5000",
        "VEV_5100",
        "VEV_5200",
        "VEV_5300",
        "VEV_5400",
        "VEV_5500",
    )

    @staticmethod
    def norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def bs_call(self, spot: float, strike: float, time_to_expiry: float) -> float:
        if spot <= 0.0 or strike <= 0.0:
            return 0.0
        if time_to_expiry <= 0.0:
            return max(0.0, spot - strike)

        sigma_root_t = self.FIT_SIGMA * math.sqrt(time_to_expiry)
        if sigma_root_t <= 0.0:
            return max(0.0, spot - strike)

        d1 = (math.log(spot / strike) + 0.5 * self.FIT_SIGMA * self.FIT_SIGMA * time_to_expiry) / sigma_root_t
        d2 = d1 - sigma_root_t
        return spot * self.norm_cdf(d1) - strike * self.norm_cdf(d2)

    @staticmethod
    def add_order(orders: Dict[str, List[Order]], product: str, price: int, quantity: int) -> None:
        if quantity == 0:
            return
        orders.setdefault(product, []).append(Order(product, int(price), int(quantity)))

    @staticmethod
    def load_data(trader_data: str) -> Dict[str, float]:
        if not trader_data:
            return {}
        try:
            data = json.loads(trader_data)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def best_bid_ask(depth: OrderDepth) -> Tuple[int, int]:
        return max(depth.buy_orders), min(depth.sell_orders)

    @staticmethod
    def sorted_asks(depth: OrderDepth) -> List[Tuple[int, int]]:
        return [(price, -depth.sell_orders[price]) for price in sorted(depth.sell_orders)]

    @staticmethod
    def sorted_bids(depth: OrderDepth) -> List[Tuple[int, int]]:
        return [(price, depth.buy_orders[price]) for price in sorted(depth.buy_orders, reverse=True)]

    @staticmethod
    def near_step(product: str, spread: int) -> int:
        if product == Trader.HYDROGEL:
            return min(3, spread // 4)
        if product == Trader.VELVET:
            return 2 if spread >= 5 else 0
        return 2 if spread >= 4 else 0

    def aggressive_fair_orders(
        self,
        product: str,
        depth: OrderDepth,
        position: int,
        timestamp: int,
        orders: Dict[str, List[Order]],
    ) -> int:
        fair = self.FAIR_VALUES[product]
        limit = self.LIMITS[product]
        projected = position
        actions: List[Tuple[float, int, int, int, int]] = []
        buy_threshold, sell_threshold = self.take_thresholds(product, timestamp)

        for price, volume in self.sorted_asks(depth):
            edge = fair - price
            if edge >= buy_threshold:
                actions.append((edge, 0, price, volume, 1))

        for price, volume in self.sorted_bids(depth):
            edge = price - fair
            if edge >= sell_threshold:
                actions.append((edge, 1, price, volume, -1))

        actions.sort(key=lambda item: (-item[0], item[1], item[2] if item[4] > 0 else -item[2]))

        for _, _, price, volume, side in actions:
            if side > 0:
                room = limit - projected
                qty = min(volume, room)
            else:
                room = limit + projected
                qty = min(volume, room)
            if qty <= 0:
                continue
            self.add_order(orders, product, price, side * qty)
            projected += side * qty

        return projected

    def take_thresholds(self, product: str, timestamp: int) -> Tuple[float, float]:
        static = self.STATIC_TAKE_THRESHOLD.get(product)
        if static is not None:
            return static

        for cutoff, buy_threshold, sell_threshold in self.TAKE_REGIMES[product]:
            if timestamp < cutoff:
                return buy_threshold, sell_threshold

        last = self.TAKE_REGIMES[product][-1]
        return last[1], last[2]

    def passive_fair_orders(
        self,
        product: str,
        depth: OrderDepth,
        projected: int,
        orders: Dict[str, List[Order]],
    ) -> int:
        if not depth.buy_orders or not depth.sell_orders:
            return projected

        best_bid, best_ask = self.best_bid_ask(depth)
        spread = best_ask - best_bid
        if spread <= 1:
            return projected

        fair = self.FAIR_VALUES[product]
        limit = self.LIMITS[product]

        quote_pairs = [(best_bid + 1, best_ask - 1, self.PASSIVE_SIZE[product], 1.0)]
        step = self.near_step(product, spread)
        if step > 1:
            quote_pairs.append(
                (
                    min(best_ask - 1, best_bid + step),
                    max(best_bid + 1, best_ask - step),
                    self.NEAR_PASSIVE_SIZE[product],
                    0.5,
                )
            )

        for bid_price, ask_price, size, threshold_scale in quote_pairs:
            if bid_price < ask_price:
                buy_edge = fair - bid_price
                if buy_edge >= self.PASSIVE_BUY_THRESHOLD[product] * threshold_scale:
                    room = limit - projected
                    qty = min(size, room)
                    if qty > 0:
                        self.add_order(orders, product, bid_price, qty)
                        projected += qty

                sell_edge = ask_price - fair
                if sell_edge >= self.PASSIVE_SELL_THRESHOLD[product] * threshold_scale:
                    room = limit + projected
                    qty = min(size, room)
                    if qty > 0:
                        self.add_order(orders, product, ask_price, -qty)
                        projected -= qty

        return projected

    def trade_product(
        self,
        product: str,
        depth: OrderDepth,
        position: int,
        timestamp: int,
        orders: Dict[str, List[Order]],
    ) -> None:
        projected = self.aggressive_fair_orders(product, depth, position, timestamp, orders)
        self.passive_fair_orders(product, depth, projected, orders)

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        _ = self.load_data(state.traderData)
        orders: Dict[str, List[Order]] = {}

        for product in self.TRADED_PRODUCTS:
            depth = state.order_depths.get(product)
            if depth is None or (not depth.buy_orders and not depth.sell_orders):
                continue
            self.trade_product(
                product=product,
                depth=depth,
                position=state.position.get(product, 0),
                timestamp=state.timestamp,
                orders=orders,
            )

        return orders, 0, "{}"
