"""Institutional Risk Management and Position Sizing Engine.

Enforces strict capital preservation rules:
- Max risk per trade (e.g., 1.0% - 1.5% of total capital)
- Dynamic ATR-based Stop Loss & Profit Targets
- Minimum Risk-to-Reward ratio filtering (>= 1:2.0)
- Capital allocation limits (prevents over-concentrated position sizing)
"""

from dataclasses import dataclass
from typing import Optional
from config.settings import risk_config


@dataclass
class CircuitBreakerStatus:
    level: str               # 'GREEN', 'YELLOW_5PCT', 'ORANGE_10PCT', 'RED_15PCT_LOCKOUT'
    drawdown_pct: float
    is_locked: bool
    risk_multiplier: float
    message: str


@dataclass
class TradeOrderTicket:
    ticker: str
    timeframe: str         # 'SWING' or 'INTRADAY'
    direction: str         # 'LONG' or 'SHORT'
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_per_share: float
    reward_per_share_t1: float
    reward_per_share_t2: float
    risk_reward_ratio_t1: float
    risk_reward_ratio_t2: float
    recommended_shares: int
    capital_required: float
    dollar_risk_amount: float
    risk_pct_of_capital: float
    is_valid_risk: bool
    rejection_reason: Optional[str] = None


class RiskManager:
    def __init__(self, total_capital: Optional[float] = None, max_risk_pct: Optional[float] = None):
        self.total_capital = total_capital or risk_config.default_capital_usd
        self.max_risk_pct = max_risk_pct or risk_config.max_risk_pct
        self.min_rr = risk_config.min_risk_reward_ratio

    def set_capital(self, capital: float):
        """Update active account capital (e.g., switching between USD and INR)."""
        self.total_capital = max(1.0, capital)

    def calculate_trade_ticket(
        self,
        ticker: str,
        entry_price: float,
        stop_loss: float,
        timeframe: str = "SWING",
        direction: str = "LONG",
        target_override: Optional[float] = None
    ) -> TradeOrderTicket:
        """
        Calculates exact shares, targets, and verifies if the trade meets risk criteria.
        """
        if direction.upper() == "LONG":
            if stop_loss >= entry_price:
                return TradeOrderTicket(
                    ticker=ticker,
                    timeframe=timeframe,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target_1=0.0,
                    target_2=0.0,
                    risk_per_share=0.0,
                    reward_per_share_t1=0.0,
                    reward_per_share_t2=0.0,
                    risk_reward_ratio_t1=0.0,
                    risk_reward_ratio_t2=0.0,
                    recommended_shares=0,
                    capital_required=0.0,
                    dollar_risk_amount=0.0,
                    risk_pct_of_capital=0.0,
                    is_valid_risk=False,
                    rejection_reason=f"Invalid Stop Loss ({stop_loss:.2f}) must be strictly below Entry ({entry_price:.2f})"
                )

            risk_per_share = entry_price - stop_loss
            
            # Dynamic targets based on multiples of Risk (R)
            t1 = target_override if target_override else entry_price + (2.0 * risk_per_share)
            t2 = entry_price + (3.5 * risk_per_share)
            
            reward_t1 = t1 - entry_price
            reward_t2 = t2 - entry_price
            rr_t1 = reward_t1 / risk_per_share if risk_per_share > 0 else 0
            rr_t2 = reward_t2 / risk_per_share if risk_per_share > 0 else 0

        else: # SHORT
            if stop_loss <= entry_price:
                return TradeOrderTicket(
                    ticker=ticker,
                    timeframe=timeframe,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target_1=0.0,
                    target_2=0.0,
                    risk_per_share=0.0,
                    reward_per_share_t1=0.0,
                    reward_per_share_t2=0.0,
                    risk_reward_ratio_t1=0.0,
                    risk_reward_ratio_t2=0.0,
                    recommended_shares=0,
                    capital_required=0.0,
                    dollar_risk_amount=0.0,
                    risk_pct_of_capital=0.0,
                    is_valid_risk=False,
                    rejection_reason=f"Invalid Stop Loss ({stop_loss:.2f}) must be strictly above Entry ({entry_price:.2f})"
                )

            risk_per_share = stop_loss - entry_price
            t1 = target_override if target_override else entry_price - (2.0 * risk_per_share)
            t2 = entry_price - (3.5 * risk_per_share)
            reward_t1 = entry_price - t1
            reward_t2 = entry_price - t2
            rr_t1 = reward_t1 / risk_per_share if risk_per_share > 0 else 0
            rr_t2 = reward_t2 / risk_per_share if risk_per_share > 0 else 0

        # Maximum dollar amount allowed to lose on this trade
        allowed_dollar_risk = self.total_capital * self.max_risk_pct

        # Position sizing: quantity = allowed_risk / risk_per_share
        if risk_per_share > 0:
            raw_shares = allowed_dollar_risk / risk_per_share
            # Cap shares if total capital required exceeds account size (no excessive leverage)
            max_shares_by_capital = self.total_capital / entry_price if entry_price > 0 else 0
            recommended_shares = int(min(raw_shares, max_shares_by_capital))
        else:
            recommended_shares = 0

        capital_required = round(recommended_shares * entry_price, 2)
        actual_dollar_risk = round(recommended_shares * risk_per_share, 2)
        actual_risk_pct = round((actual_dollar_risk / self.total_capital) * 100, 2) if self.total_capital > 0 else 0

        # Risk-to-Reward validity check
        is_valid = True
        rejection_reason = None

        if recommended_shares <= 0:
            is_valid = False
            rejection_reason = "Insufficient capital to purchase minimum 1 share at this risk level."
        elif rr_t1 < self.min_rr:
            is_valid = False
            rejection_reason = f"Risk:Reward ratio ({rr_t1:.2f}) is below minimum threshold ({self.min_rr:.1f})."

        return TradeOrderTicket(
            ticker=ticker,
            timeframe=timeframe,
            direction=direction,
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_1=round(t1, 2),
            target_2=round(t2, 2),
            risk_per_share=round(risk_per_share, 2),
            reward_per_share_t1=round(reward_t1, 2),
            reward_per_share_t2=round(reward_t2, 2),
            risk_reward_ratio_t1=round(rr_t1, 2),
            risk_reward_ratio_t2=round(rr_t2, 2),
            recommended_shares=recommended_shares,
            capital_required=capital_required,
            dollar_risk_amount=actual_dollar_risk,
            risk_pct_of_capital=actual_risk_pct,
            is_valid_risk=is_valid,
            rejection_reason=rejection_reason
        )

    # ==========================================
    # P0 INSTITUTIONAL CAPITAL PRESERVATION GUARDS
    # ==========================================

    def evaluate_circuit_breaker(self, peak_equity: float, current_equity: float) -> CircuitBreakerStatus:
        """
        Monitors account-level drawdown against high-water mark.
        Enforces 3 institutional circuit breaker tiers:
        - Tier 1 (Yellow, -5% DD): Cut risk by 50%
        - Tier 2 (Orange, -10% DD): Cut risk by 65%, halt intraday momentum
        - Tier 3 (Red, -15% DD): Full desk lockout, block new positions
        """
        if peak_equity <= 0:
            return CircuitBreakerStatus("GREEN", 0.0, False, 1.0, "Normal operating parameters.")

        dd_pct = ((current_equity - peak_equity) / peak_equity) * 100.0

        if dd_pct <= -15.0:
            return CircuitBreakerStatus(
                level="RED_15PCT_LOCKOUT",
                drawdown_pct=round(dd_pct, 2),
                is_locked=True,
                risk_multiplier=0.0,
                message="🚨 RED CIRCUIT BREAKER: Account drawdown exceeds -15%. Trading desk locked out to preserve capital."
            )
        elif dd_pct <= -10.0:
            return CircuitBreakerStatus(
                level="ORANGE_10PCT",
                drawdown_pct=round(dd_pct, 2),
                is_locked=False,
                risk_multiplier=0.35,
                message="⚠️ ORANGE CIRCUIT BREAKER: Account drawdown at -10%. Intraday halted; position risk reduced by 65%."
            )
        elif dd_pct <= -5.0:
            return CircuitBreakerStatus(
                level="YELLOW_5PCT",
                drawdown_pct=round(dd_pct, 2),
                is_locked=False,
                risk_multiplier=0.50,
                message="🟡 YELLOW CIRCUIT BREAKER: Account drawdown at -5%. Max trade risk cut by 50% until recovery."
            )

        return CircuitBreakerStatus(
            level="GREEN",
            drawdown_pct=round(dd_pct, 2),
            is_locked=False,
            risk_multiplier=1.0,
            message="✅ Operations Normal: Capital within safe risk boundaries."
        )

    def check_portfolio_guard(
        self,
        candidate_ticker: str,
        open_positions: list,
        max_concurrent: int = 6
    ) -> tuple[bool, Optional[str]]:
        """
        Prevents account overconcentration across open trades.
        - Capped max concurrent open positions (default: 6)
        - Prevents duplicate positions in the same ticker
        """
        cand_clean = candidate_ticker.upper()

        # 1. Duplicate check
        for p in open_positions:
            t = p["ticker"] if isinstance(p, dict) else getattr(p, "ticker", "")
            if t.upper() == cand_clean:
                return False, f"Position for {cand_clean} is already active in portfolio."

        # 2. Maximum concurrent positions check
        if len(open_positions) >= max_concurrent:
            return False, f"Maximum concurrent positions ({max_concurrent}) reached. Close a position before opening new trades."

        return True, None
