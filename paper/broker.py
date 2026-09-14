import pandas as pd

from . import config as cfg


class Broker:
    def equity(self, prices):
        raise NotImplementedError

    def positions(self):
        raise NotImplementedError

    def rebalance(self, target_weights, prices):
        raise NotImplementedError


class PaperBroker(Broker):
    def __init__(self, cash=None, positions=None, avg_entry=None):
        self.cash = float(cfg.INITIAL_CAPITAL if cash is None else cash)
        self.pos = {k: float(v) for k, v in (positions or {}).items()}
        self.avg = {k: float(v) for k, v in (avg_entry or {}).items()}

    def positions(self):
        return dict(self.pos)

    def market_value(self, prices):
        return sum(q * prices.get(s, 0.0) for s, q in self.pos.items())

    def equity(self, prices):
        return self.cash + self.market_value(prices)

    def gross_notional(self, prices):
        return sum(abs(q) * prices.get(s, 0.0) for s, q in self.pos.items())

    def net_notional(self, prices):
        return sum(q * prices.get(s, 0.0) for s, q in self.pos.items())

    def current_weights(self, prices, equity=None):
        equity = equity if equity is not None else self.equity(prices)
        if equity <= 0:
            return pd.Series(dtype=float)
        return pd.Series({s: q * prices.get(s, 0.0) / equity for s, q in self.pos.items()})

    def rebalance(self, target_weights, prices, reason="rebalance"):
        equity = self.equity(prices)
        if equity <= 0:
            return [], equity
        tgt = pd.Series(target_weights, dtype=float)
        tgt = tgt[tgt.index.isin(list(prices.keys()))]
        symbols = sorted(set(tgt.index) | set(self.pos.keys()))
        fills = []
        for s in symbols:
            px = prices.get(s)
            if not px or px <= 0:
                continue
            cur_qty = self.pos.get(s, 0.0)
            cur_notional = cur_qty * px
            tgt_notional = float(tgt.get(s, 0.0)) * equity
            delta = tgt_notional - cur_notional
            if abs(delta) < cfg.MIN_ORDER_USD:
                continue
            qty_delta = delta / px
            old_qty = cur_qty
            new_qty = old_qty + qty_delta
            self.pos[s] = new_qty
            self.cash -= qty_delta * px
            fee = abs(delta) * cfg.FEE_BPS / 1e4
            slip = abs(delta) * cfg.SLIP_BPS / 1e4
            self.cash -= (fee + slip)
            if abs(new_qty) * px < cfg.MIN_ORDER_USD:
                self.pos[s] = 0.0
                self.avg[s] = 0.0
            elif old_qty == 0 or (old_qty * new_qty < 0):
                self.avg[s] = px
            elif abs(new_qty) > abs(old_qty):
                prev = self.avg.get(s, px)
                self.avg[s] = (abs(old_qty) * prev + abs(qty_delta) * px) / (abs(old_qty) + abs(qty_delta))
            fills.append({
                "symbol": s, "side": "BUY" if qty_delta > 0 else "SELL",
                "qty": qty_delta, "price": px, "notional": delta,
                "fee": fee, "slippage": slip, "reason": reason,
            })
        return fills, equity

    def apply_funding(self, funding_rates, prices):
        total = 0.0
        for s, q in list(self.pos.items()):
            if q == 0:
                continue
            px = prices.get(s, 0.0)
            rate = float(funding_rates.get(s, 0.0))
            if px <= 0 or rate == 0:
                continue
            pnl = -q * px * rate
            self.cash += pnl
            total += pnl
        return total
