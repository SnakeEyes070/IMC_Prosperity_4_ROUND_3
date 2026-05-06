# trader.py — Round 3 Scout (Works with local backtester + Prosperity)
import json, math
from typing import Dict, List, Tuple
from datamodel import Order, OrderDepth, TradingState

class Trader:
    HYDROGEL = "HYDROGEL_PACK"
    VELVET = "VELVETFRUIT_EXTRACT"
    VOUCHERS = [f"VEV_{k}" for k in [4000,4500,5000,5100,5200,5300,5400,5500,6000,6500]]
    LIMIT = 200
    OPT_LIMIT = 300

    # Black-Scholes (manual normal CDF)
    def _norm_cdf(self, x: float) -> float:
        a1,a2,a3,a4,a5 = 0.254829592,-0.284496736,1.421413741,-1.453152027,1.061405429
        p = 0.3275911
        sign = 1.0 if x >= 0 else -1.0
        x = abs(x)/math.sqrt(2.0)
        t = 1.0/(1.0+p*x)
        y = 1.0-(((((a5*t+a4)*t)+a3)*t+a2)*t+a1)*t*math.exp(-x*x)
        return 0.5*(1.0+sign*y)

    def _bs_call(self, S, K, T, r, sigma):
        if T <= 0: return max(0.0, S-K)
        d1 = (math.log(S/K)+(r+0.5*sigma**2)*T)/(sigma*math.sqrt(T))
        d2 = d1 - sigma*math.sqrt(T)
        return S*self._norm_cdf(d1) - K*math.exp(-r*T)*self._norm_cdf(d2)

    def _delta(self, S, K, T, r, sigma):
        if T <= 0: return 1.0 if S>K else 0.0
        d1 = (math.log(S/K)+(r+0.5*sigma**2)*T)/(sigma*math.sqrt(T))
        return self._norm_cdf(d1)

    def bid(self) -> int:
        return 6000

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        orders: Dict[str, List[Order]] = {}
        ts = state.timestamp

        # --- Delta‑1: Buy 1 unit at open ---
        for prod in [self.HYDROGEL, self.VELVET]:
            od = state.order_depths.get(prod)
            if not od: continue
            pos = state.position.get(prod, 0)
            if ts == 0 and pos < self.LIMIT and od.sell_orders:
                best_ask = min(od.sell_orders.keys())
                orders.setdefault(prod, []).append(Order(prod, best_ask, 1))

        # --- Vouchers: passive scout bid ---
        if self.VELVET in state.order_depths:
            ud = state.order_depths[self.VELVET]
            S = (max(ud.buy_orders.keys())+min(ud.sell_orders.keys()))/2.0 if (ud.buy_orders and ud.sell_orders) else 5000
        else:
            S = 5000

        for v in self.VOUCHERS:
            od = state.order_depths.get(v)
            if not od: continue
            pos = state.position.get(v, 0)
            strike = int(v.split("_")[1])
            bid_px = max(1, int(S - strike - 500))
            if pos < self.OPT_LIMIT:
                qty = min(1, self.OPT_LIMIT - pos)
                orders.setdefault(v, []).append(Order(v, bid_px, qty))

        return orders, 0, ""