"""Virtual Broker & Paper Execution Ledger Engine.

Automates the trade lifecycle with zero financial risk:
- Tracks positions opened via screener or manual execution
- Monitors live market prices
- Automatically books 50% profit at Target 1 and trails stop-loss to Break-Even (entry price)
- Closes remaining position at Target 2
- Cuts losses at Stop-Loss
- Calculates live portfolio equity, win rate, and profit factor
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from ledger.database import get_connection
from data.provider import data_provider
from risk.manager import RiskManager

logger = logging.getLogger(__name__)


class VirtualBroker:
    def __init__(self, initial_cash: float = 10000.0):
        self.initial_cash = initial_cash
        self.risk_manager = RiskManager(total_capital=initial_cash)

    # ==========================================
    # 1. ORDER EXECUTION & MANAGEMENT
    # ==========================================

    def open_position(
        self,
        ticker: str,
        entry_price: float,
        shares: int,
        stop_loss: float,
        target_1: float,
        target_2: float,
        market: str = "US",
        timeframe: str = "SWING",
        direction: str = "LONG",
        pattern: str = "Minervini Stage 2",
        notes: str = ""
    ) -> Dict[str, Any]:
        """Opens a new tracked trade position."""
        if shares <= 0 or entry_price <= 0:
            return {"success": False, "message": "Invalid shares or entry price."}

        # 1. Evaluate Circuit Breaker Status
        summary = self.get_portfolio_summary()
        cb = self.risk_manager.evaluate_circuit_breaker(
            peak_equity=max(summary["initial_cash"], summary["current_equity"]),
            current_equity=summary["current_equity"]
        )
        if cb.is_locked:
            return {"success": False, "message": cb.message}

        # 2. Evaluate Portfolio Concentration Guard
        active_positions = self.get_active_positions()
        can_open, reason = self.risk_manager.check_portfolio_guard(
            candidate_ticker=ticker,
            open_positions=active_positions,
            max_concurrent=6
        )
        if not can_open:
            return {"success": False, "message": f"🛡️ Risk Guard: {reason}"}

        # 3. Check database
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM trades WHERE ticker = ? AND status IN ('OPEN', 'PARTIAL_T1')",
                (ticker.upper(),)
            )
            existing = cursor.fetchone()
            if existing:
                return {"success": False, "message": f"Active position for {ticker.upper()} already exists."}

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO trades (
                    ticker, market, timeframe, direction, status,
                    entry_date, entry_price, shares, remaining_shares,
                    initial_stop, current_stop, target_1, target_2,
                    pattern, notes
                ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker.upper(), market.upper(), timeframe.upper(), direction.upper(),
                now_str, entry_price, shares, shares,
                stop_loss, stop_loss, target_1, target_2,
                pattern, notes
            ))
            trade_id = cursor.lastrowid

            # Log audit event
            cursor.execute("""
                INSERT INTO ledger_logs (timestamp, event_type, ticker, message)
                VALUES (?, 'ORDER_OPEN', ?, ?)
            """, (
                now_str, ticker.upper(),
                f"Bought {shares} shares at {entry_price:.2f}. Initial stop: {stop_loss:.2f}, T1: {target_1:.2f}, T2: {target_2:.2f}"
            ))
            conn.commit()

        logger.info(f"Opened trade #{trade_id} for {ticker} ({shares} shares @ {entry_price})")
        return {"success": True, "trade_id": trade_id, "message": f"Successfully tracking {ticker.upper()}!"}

    def close_position_manually(self, trade_id: int, exit_price: Optional[float] = None) -> Dict[str, Any]:
        """Manually closes an active position at market price."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
            trade = cursor.fetchone()
            if not trade or trade["status"] == "CLOSED":
                return {"success": False, "message": "Trade not found or already closed."}

            ticker = trade["ticker"]
            if exit_price is None or exit_price <= 0:
                quote = data_provider.get_latest_quote(ticker)
                exit_price = quote.get("last_price", trade["entry_price"])

            rem_shares = trade["remaining_shares"]
            entry_price = trade["entry_price"]
            prev_realized = trade["realized_pnl"]

            # Calculate PnL for remaining shares
            additional_pnl = (exit_price - entry_price) * rem_shares if trade["direction"] == "LONG" else (entry_price - exit_price) * rem_shares
            total_pnl = prev_realized + additional_pnl
            total_invested = entry_price * trade["shares"]
            return_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                UPDATE trades SET
                    status = 'CLOSED',
                    remaining_shares = 0,
                    exit_date = ?,
                    exit_price = ?,
                    realized_pnl = ?,
                    return_pct = ?,
                    exit_reason = 'MANUAL'
                WHERE id = ?
            """, (now_str, exit_price, total_pnl, return_pct, trade_id))

            cursor.execute("""
                INSERT INTO ledger_logs (timestamp, event_type, ticker, message)
                VALUES (?, 'MANUAL_CLOSE', ?, ?)
            """, (
                now_str, ticker,
                f"Manually closed trade #{trade_id} at {exit_price:.2f}. Realized PnL: {total_pnl:+.2f} ({return_pct:+.2f}%)"
            ))
            conn.commit()

        return {"success": True, "message": f"Closed {ticker} at {exit_price:.2f}. Total PnL: {total_pnl:+.2f}"}

    # ==========================================
    # 2. STATE MACHINE: AUTOMATED LIFECYCLE UPDATE
    # ==========================================

    def update_all_positions(self) -> List[Dict[str, Any]]:
        """
        Polls live prices for all open positions, updates trailing stops,
        and triggers profit-taking or stop-loss exits.
        Returns a list of event messages.
        """
        events = []
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE status IN ('OPEN', 'PARTIAL_T1')")
            active_trades = cursor.fetchall()

            for trade in active_trades:
                trade_id = trade["id"]
                ticker = trade["ticker"]
                status = trade["status"]
                entry_price = trade["entry_price"]
                current_stop = trade["current_stop"]
                target_1 = trade["target_1"]
                target_2 = trade["target_2"]
                shares = trade["shares"]
                remaining_shares = trade["remaining_shares"]
                realized_pnl = trade["realized_pnl"]

                quote = data_provider.get_latest_quote(ticker)
                curr_price = quote.get("last_price", 0.0)
                if curr_price <= 0:
                    continue

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Case A: STOP LOSS or BREAK-EVEN STOP HIT
                if curr_price <= current_stop:
                    # Position is stopped out
                    loss_for_rem = (current_stop - entry_price) * remaining_shares
                    total_pnl = realized_pnl + loss_for_rem
                    total_invested = entry_price * shares
                    ret_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0
                    reason = "BREAKEVEN_STOP" if status == "PARTIAL_T1" else "STOP_LOSS"

                    cursor.execute("""
                        UPDATE trades SET
                            status = 'CLOSED',
                            remaining_shares = 0,
                            exit_date = ?,
                            exit_price = ?,
                            realized_pnl = ?,
                            return_pct = ?,
                            exit_reason = ?
                        WHERE id = ?
                    """, (now_str, current_stop, total_pnl, ret_pct, reason, trade_id))

                    event_msg = f"🛑 {ticker} hit stop at {current_stop:.2f}! Total PnL: {total_pnl:+.2f} ({ret_pct:+.2f}%)"
                    cursor.execute("""
                        INSERT INTO ledger_logs (timestamp, event_type, ticker, message)
                        VALUES (?, ?, ?, ?)
                    """, (now_str, reason, ticker, event_msg))
                    events.append({"ticker": ticker, "type": reason, "message": event_msg})
                    continue

                # Case B: TARGET 1 REACHED (Lock in 50% profit & move Stop to Break-Even)
                if status == "OPEN" and curr_price >= target_1:
                    shares_to_sell = max(1, shares // 2)
                    rem = shares - shares_to_sell
                    t1_pnl = (target_1 - entry_price) * shares_to_sell
                    new_realized = realized_pnl + t1_pnl
                    # Move stop to entry_price (Break-Even!)
                    new_stop = entry_price

                    cursor.execute("""
                        UPDATE trades SET
                            status = 'PARTIAL_T1',
                            remaining_shares = ?,
                            current_stop = ?,
                            realized_pnl = ?
                        WHERE id = ?
                    """, (rem, new_stop, new_realized, trade_id))

                    event_msg = (
                        f"🎯 {ticker} hit Target 1 at {curr_price:.2f}! "
                        f"Booked 50% profit (+{t1_pnl:.2f}). "
                        f"Stop-Loss auto-trailed to Break-Even ({new_stop:.2f})!"
                    )
                    cursor.execute("""
                        INSERT INTO ledger_logs (timestamp, event_type, ticker, message)
                        VALUES (?, 'T1_HIT', ?, ?)
                    """, (now_str, ticker, event_msg))
                    events.append({"ticker": ticker, "type": "T1_HIT", "message": event_msg})
                    continue

                # Case C: TARGET 2 REACHED (100% Exit at Max Target)
                if status == "PARTIAL_T1" and curr_price >= target_2:
                    t2_pnl = (target_2 - entry_price) * remaining_shares
                    total_pnl = realized_pnl + t2_pnl
                    total_invested = entry_price * shares
                    ret_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0

                    cursor.execute("""
                        UPDATE trades SET
                            status = 'CLOSED',
                            remaining_shares = 0,
                            exit_date = ?,
                            exit_price = ?,
                            realized_pnl = ?,
                            return_pct = ?,
                            exit_reason = 'TARGET_2'
                        WHERE id = ?
                    """, (now_str, target_2, total_pnl, ret_pct, trade_id))

                    event_msg = (
                        f"🏆 {ticker} hit Target 2 at {curr_price:.2f}! "
                        f"Full position closed! Total PnL: +{total_pnl:.2f} (+{ret_pct:.2f}%)"
                    )
                    cursor.execute("""
                        INSERT INTO ledger_logs (timestamp, event_type, ticker, message)
                        VALUES (?, 'T2_HIT', ?, ?)
                    """, (now_str, ticker, event_msg))
                    events.append({"ticker": ticker, "type": "T2_HIT", "message": event_msg})

            conn.commit()

        return events

    # ==========================================
    # 3. QUERIES & REPORTING
    # ==========================================

    def get_active_positions(self) -> List[Dict[str, Any]]:
        """Returns live active positions with current market quotes and unrealized PnL."""
        positions = []
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE status IN ('OPEN', 'PARTIAL_T1') ORDER BY entry_date DESC")
            rows = cursor.fetchall()

            for row in rows:
                p = dict(row)
                ticker = p["ticker"]
                quote = data_provider.get_latest_quote(ticker)
                curr_price = quote.get("last_price", p["entry_price"])
                p["current_price"] = curr_price

                # Unrealized PnL on remaining shares
                rem_shares = p["remaining_shares"]
                entry_price = p["entry_price"]
                unrealized = (curr_price - entry_price) * rem_shares
                unrealized_pct = ((curr_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0

                p["unrealized_pnl"] = unrealized
                p["unrealized_pct"] = unrealized_pct
                p["total_pnl_so_far"] = p["realized_pnl"] + unrealized
                p["is_breakeven"] = p["current_stop"] >= p["entry_price"]
                positions.append(p)

        return positions

    def get_closed_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns closed trades history."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_date DESC LIMIT ?",
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Calculates aggregate portfolio metrics and track record stats."""
        with get_connection() as conn:
            cursor = conn.cursor()

            # Active positions
            active_positions = self.get_active_positions()
            invested_capital = sum(p["entry_price"] * p["remaining_shares"] for p in active_positions)
            unrealized_pnl = sum(p["unrealized_pnl"] for p in active_positions)

            # Closed trades
            cursor.execute("SELECT realized_pnl, return_pct FROM trades WHERE status = 'CLOSED'")
            closed = cursor.fetchall()

            total_closed = len(closed)
            winning_trades = sum(1 for c in closed if c["realized_pnl"] > 0)
            losing_trades = sum(1 for c in closed if c["realized_pnl"] < 0)
            win_rate = (winning_trades / total_closed * 100.0) if total_closed > 0 else 0.0

            total_realized_pnl = sum(c["realized_pnl"] for c in closed)
            total_gains = sum(c["realized_pnl"] for c in closed if c["realized_pnl"] > 0)
            total_losses = abs(sum(c["realized_pnl"] for c in closed if c["realized_pnl"] < 0))
            profit_factor = (total_gains / total_losses) if total_losses > 0 else (total_gains if total_gains > 0 else 1.0)

            # Total equity
            current_equity = self.initial_cash + total_realized_pnl + unrealized_pnl
            cash_balance = current_equity - invested_capital

            return {
                "initial_cash": self.initial_cash,
                "current_equity": current_equity,
                "cash_balance": cash_balance,
                "invested_capital": invested_capital,
                "realized_pnl": total_realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_trades": total_closed + len(active_positions),
                "closed_trades_count": total_closed,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "active_positions_count": len(active_positions)
            }

    def get_recent_logs(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Returns recent system and audit actions."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ledger_logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]


# Singleton instance
virtual_broker = VirtualBroker()
