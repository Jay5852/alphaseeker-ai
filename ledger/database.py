"""SQLite Database Interface for Autonomous Virtual Ledger & Trade Tracking.

100% Free, zero-dependency, local file-based storage.
Manages:
- Active & Historical Trades
- Daily Portfolio Snapshots & Equity Curves
- Audit Logs for automated actions (trailing stops, target executions)
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trading_ledger.db"


def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with dict-like row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initializes SQLite schema if not already created."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'US',
                timeframe TEXT NOT NULL DEFAULT 'SWING',
                direction TEXT NOT NULL DEFAULT 'LONG',
                status TEXT NOT NULL DEFAULT 'OPEN',     -- 'OPEN', 'PARTIAL_T1', 'CLOSED'
                entry_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                shares INTEGER NOT NULL,
                remaining_shares INTEGER NOT NULL,
                initial_stop REAL NOT NULL,
                current_stop REAL NOT NULL,
                target_1 REAL NOT NULL,
                target_2 REAL NOT NULL,
                exit_date TEXT,
                exit_price REAL,
                realized_pnl REAL DEFAULT 0.0,
                return_pct REAL DEFAULT 0.0,
                exit_reason TEXT,                        -- 'TARGET_1', 'TARGET_2', 'STOP_LOSS', 'BREAKEVEN', 'MANUAL'
                pattern TEXT,
                notes TEXT
            );
        """)

        # 2. Portfolio snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cash_balance REAL NOT NULL,
                invested_capital REAL NOT NULL,
                total_portfolio_value REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                active_position_count INTEGER NOT NULL,
                drawdown_pct REAL NOT NULL DEFAULT 0.0
            );
        """)

        # 3. Audit & System logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ledger_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,                -- 'ORDER_OPEN', 'T1_HIT', 'T2_HIT', 'STOP_LOSS', 'TRAIL_STOP', 'MANUAL_CLOSE'
                ticker TEXT,
                message TEXT NOT NULL
            );
        """)

        conn.commit()
        logger.info("Ledger database initialized successfully.")


# Auto-initialize on module load
init_database()
