import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables if .env file exists
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


@dataclass
class RiskConfig:
    # Portfolio Capital parameters
    default_capital_usd: float = 10000.0
    default_capital_inr: float = 200000.0
    
    # Maximum risk per individual trade (1.0% = 0.01)
    max_risk_pct: float = 0.015
    
    # Maximum portfolio heat (total concurrent risk across all open trades)
    max_portfolio_heat_pct: float = 0.06
    
    # Minimum required Risk-to-Reward ratio to trigger an alert
    min_risk_reward_ratio: float = 2.0
    
    # ATR Multipliers for dynamic stops
    swing_atr_stop_multiplier: float = 1.5
    intraday_atr_stop_multiplier: float = 1.2
    
    # Max open positions
    max_swing_positions: int = 6
    max_intraday_positions: int = 3


@dataclass
class SwingConfig:
    # Minervini Trend Template Thresholds
    min_volume_daily: int = 500_000
    min_price_usd: float = 5.0
    min_price_inr: float = 50.0
    
    # Moving Average parameters
    sma_short: int = 50
    sma_medium: int = 150
    sma_long: int = 200
    
    # Proximity to 52-week High (must be within X% of 52-week high)
    max_pct_from_52w_high: float = 25.0
    
    # Minimum % above 52-week Low
    min_pct_above_52w_low: float = 30.0
    
    # Volatility Contraction Pattern (VCP) threshold (ATR contraction)
    vcp_contraction_ratio: float = 0.65


@dataclass
class IntradayConfig:
    # Relative Volume (RVOL) minimum threshold
    min_rvol: float = 1.8
    
    # Minimum intraday turnover
    min_intraday_volume: int = 1_000_000
    
    # Opening Range Breakout time window (minutes)
    orb_period_minutes: int = 15
    
    # VWAP distance tolerance (% deviation from VWAP for pullback entries)
    vwap_max_pullback_pct: float = 0.8
    
    # Maximum intraday holding time (e.g., auto-exit before market close)
    market_close_buffer_minutes: int = 15


@dataclass
class ConfluenceConfig:
    # Multi-Timeframe Confluence Scoring (Improvement G)
    # Minimum confluence score (0-4) required to approve a trade
    # Spec: "Only trade 3/4 or 4/4 confluence signals"
    min_trade_score: int = 3

    # Master switch to enable/disable the confluence filter
    enabled: bool = True

    # Confidence score bonus awarded for a perfect 4/4 alignment
    perfect_score_bonus: float = 3.0


@dataclass
class TelegramConfig:
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    enabled: bool = bool(os.getenv("TELEGRAM_BOT_TOKEN", ""))


# Export instances
risk_config = RiskConfig()
swing_config = SwingConfig()
intraday_config = IntradayConfig()
confluence_config = ConfluenceConfig()
telegram_config = TelegramConfig()
