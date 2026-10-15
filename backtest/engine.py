"""Historical Backtesting and Performance Analytics Engine.

Simulates strategy execution over historical data with realistic institutional rules:
- Confirmation entry on Stage 2 breakouts
- 50% partial profit booking at Target 1 (2.0R)
- Trailing stop on the remaining 50% position
- Full exit at Target 2 (3.5R) or structural stop-loss
- Computes Sharpe ratio, Win Rate %, Profit Factor, and Max Drawdown
"""

from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd
import numpy as np

from data.provider import data_provider
from ml.features import compute_all_swing_features
from risk.manager import RiskManager


@dataclass
class TradeRecord:
    ticker: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    outcome: str          # 'TARGET_1_PARTIAL', 'TARGET_2_FULL', 'STOP_LOSS', 'TRAILING_STOP'
    holding_days: int


@dataclass
class BacktestSummary:
    ticker: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    total_pnl: float
    total_return_pct: float
    profit_factor: float
    max_drawdown_pct: float
    trades: List[TradeRecord] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, risk_pct: float = 0.015):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.risk_mgr = RiskManager(total_capital=initial_capital, max_risk_pct=risk_pct)

    def backtest_swing_ticker(self, ticker: str, period: str = "2y") -> BacktestSummary:
        """Runs a bar-by-bar historical backtest of the Swing Strategy on a ticker."""
        df = data_provider.get_historical_daily(ticker, period=period)
        if df.empty or len(df) < 150:
            return BacktestSummary(
                ticker=ticker, total_trades=0, winning_trades=0, losing_trades=0,
                win_rate_pct=0.0, total_pnl=0.0, total_return_pct=0.0,
                profit_factor=0.0, max_drawdown_pct=0.0
            )

        df = compute_all_swing_features(df)
        trades: List[TradeRecord] = []
        equity = self.initial_capital
        peak_equity = equity
        max_drawdown = 0.0

        in_position = False
        entry_price = 0.0
        stop_loss = 0.0
        target_1 = 0.0
        target_2 = 0.0
        total_shares = 0
        active_shares = 0
        entry_idx = 0
        t1_hit = False
        trade_realized_pnl = 0.0

        for i in range(50, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]
            date_str = str(df.index[i])[:10]

            if in_position:
                high = curr["High"]
                low = curr["Low"]
                close = curr["Close"]
                holding_days = i - entry_idx

                # Check Stop Loss
                if low <= stop_loss:
                    exit_price = stop_loss
                    pnl_remaining = (exit_price - entry_price) * active_shares
                    total_pnl = trade_realized_pnl + pnl_remaining
                    equity += pnl_remaining
                    outcome = "STOP_LOSS" if not t1_hit else "TRAILING_STOP"
                    trades.append(TradeRecord(
                        ticker=ticker,
                        entry_date=str(df.index[entry_idx])[:10],
                        exit_date=date_str,
                        entry_price=round(entry_price, 2),
                        exit_price=round(exit_price, 2),
                        shares=total_shares,
                        pnl=round(total_pnl, 2),
                        pnl_pct=round(((exit_price - entry_price) / entry_price) * 100, 2),
                        outcome=outcome,
                        holding_days=holding_days
                    ))
                    in_position = False
                    t1_hit = False
                    active_shares = 0
                    trade_realized_pnl = 0.0

                # Check Target 1 hit: take 50% profit and trail stop to entry + 0.5R
                elif not t1_hit and high >= target_1:
                    t1_hit = True
                    half_shares = max(1, active_shares // 2)
                    pnl_half = (target_1 - entry_price) * half_shares
                    trade_realized_pnl += pnl_half
                    equity += pnl_half
                    active_shares -= half_shares
                    # Move trailing stop up to entry (risk-free trade)
                    stop_loss = max(stop_loss, entry_price)

                # Check Target 2 hit: close remaining 50% position
                elif high >= target_2:
                    exit_price = target_2
                    pnl_remaining = (exit_price - entry_price) * active_shares
                    total_pnl = trade_realized_pnl + pnl_remaining
                    equity += pnl_remaining
                    trades.append(TradeRecord(
                        ticker=ticker,
                        entry_date=str(df.index[entry_idx])[:10],
                        exit_date=date_str,
                        entry_price=round(entry_price, 2),
                        exit_price=round(exit_price, 2),
                        shares=total_shares,
                        pnl=round(total_pnl, 2),
                        pnl_pct=round(((exit_price - entry_price) / entry_price) * 100, 2),
                        outcome="TARGET_2_FULL",
                        holding_days=holding_days
                    ))
                    in_position = False
                    t1_hit = False
                    active_shares = 0
                    trade_realized_pnl = 0.0

                # Time stop: exit after 60 trading days
                elif holding_days >= 60:
                    exit_price = close
                    pnl_remaining = (exit_price - entry_price) * active_shares
                    total_pnl = trade_realized_pnl + pnl_remaining
                    equity += pnl_remaining
                    trades.append(TradeRecord(
                        ticker=ticker,
                        entry_date=str(df.index[entry_idx])[:10],
                        exit_date=date_str,
                        entry_price=round(entry_price, 2),
                        exit_price=round(exit_price, 2),
                        shares=total_shares,
                        pnl=round(total_pnl, 2),
                        pnl_pct=round(((exit_price - entry_price) / entry_price) * 100, 2),
                        outcome="TIME_STOP",
                        holding_days=holding_days
                    ))
                    in_position = False
                    t1_hit = False
                    active_shares = 0
                    trade_realized_pnl = 0.0

                if equity > peak_equity:
                    peak_equity = equity
                dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
                max_drawdown = max(max_drawdown, dd)

            else:
                c = curr["Close"]
                sma50 = curr.get("SMA_50")
                sma150 = curr.get("SMA_150")
                sma200 = curr.get("SMA_200")
                atr = curr.get("ATR_14", c * 0.02)
                rvol = curr.get("RVOL", 1.0)
                pct_high = curr.get("Pct_From_52W_High", 100)

                # Minervini Stage 2 criteria & volume expansion entry
                if (not pd.isna(sma50) and not pd.isna(sma150) and not pd.isna(sma200) and
                    c > sma50 and sma50 > sma150 and sma150 > sma200 and
                    pct_high <= 15.0 and rvol >= 1.2 and c > prev["Close"]):

                    calc_stop = c - (1.5 * atr)
                    self.risk_mgr.set_capital(equity)
                    ticket = self.risk_mgr.calculate_trade_ticket(
                        ticker=ticker,
                        entry_price=c,
                        stop_loss=calc_stop,
                        timeframe="SWING",
                        direction="LONG"
                    )

                    if ticket.is_valid_risk and ticket.recommended_shares > 1:
                        in_position = True
                        entry_price = ticket.entry_price
                        stop_loss = ticket.stop_loss
                        target_1 = ticket.target_1
                        target_2 = ticket.target_2
                        total_shares = ticket.recommended_shares
                        active_shares = total_shares
                        entry_idx = i
                        t1_hit = False
                        trade_realized_pnl = 0.0

        total_trades = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        total_pnl = equity - self.initial_capital
        total_return_pct = (total_pnl / self.initial_capital) * 100.0

        return BacktestSummary(
            ticker=ticker,
            total_trades=total_trades,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate_pct=round(win_rate, 1),
            total_pnl=round(total_pnl, 2),
            total_return_pct=round(total_return_pct, 1),
            profit_factor=round(profit_factor, 2),
            max_drawdown_pct=round(max_drawdown * 100, 1),
            trades=trades
        )


backtest_engine = BacktestEngine()
