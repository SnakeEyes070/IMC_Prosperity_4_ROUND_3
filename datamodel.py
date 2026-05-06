# Minimal datamodel for local backtesting
from typing import Dict, List

class Order:
    def __init__(self, symbol: str, price: int, quantity: int):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity

class OrderDepth:
    def __init__(self):
        self.buy_orders: Dict[int, int] = {}
        self.sell_orders: Dict[int, int] = {}

class Trade:
    def __init__(self, symbol: str, price: int, quantity: int, buyer: str = "", seller: str = ""):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller

class TradingState:
    def __init__(self, traderData: str, timestamp: int, 
                 order_depths: Dict[str, OrderDepth],
                 own_trades: Dict[str, List[Trade]],
                 market_trades: Dict[str, List[Trade]],
                 position: Dict[str, int],
                 observations: Dict = None):
        self.traderData = traderData
        self.timestamp = timestamp
        self.order_depths = order_depths
        self.own_trades = own_trades
        self.market_trades = market_trades
        self.position = position
        self.observations = observations or {}