"""Quantitative Feature Engineering and Technical Pattern Metrics."""

import numpy as np
import pandas as pd


def compute_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Adds SMAs and EMAs to the dataframe."""
    df = df.copy()
    for period in [10, 20, 50, 150, 200]:
        df[f"SMA_{period}"] = df["Close"].rolling(window=period).mean()
    for period in [9, 21]:
        df[f"EMA_{period}"] = df["Close"].ewm(span=period, adjust=False).mean()
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Computes Average True Range (ATR)."""
    df = df.copy()
    high = df["High"]
    low = df["Low"]
    close_prev = df["Close"].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df["TR"] = tr
    df[f"ATR_{period}"] = tr.rolling(window=period).mean()
    return df


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Computes Relative Strength Index (RSI)."""
    df = df.copy()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    df[f"RSI_{period}"] = 100 - (100 / (1 + rs))
    return df


def compute_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """Computes Bollinger Bands and Bandwidth for Squeeze detection."""
    df = df.copy()
    sma = df["Close"].rolling(window=period).mean()
    std = df["Close"].rolling(window=period).std()

    df["BB_Upper"] = sma + (std_dev * std)
    df["BB_Middle"] = sma
    df["BB_Lower"] = sma - (std_dev * std)
    df["BB_Bandwidth"] = (df["BB_Upper"] - df["BB_Lower"]) / (sma + 1e-9)
    return df


def compute_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Computes Volume Weighted Average Price (VWAP) for intraday data."""
    df = df.copy()
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_vol_price = (typical_price * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum()
    df["VWAP"] = cum_vol_price / (cum_vol + 1e-9)
    return df


def compute_rvol(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Computes Relative Volume (RVOL) compared to trailing average volume."""
    df = df.copy()
    avg_vol = df["Volume"].rolling(window=window).mean()
    df["RVOL"] = df["Volume"] / (avg_vol + 1e-9)
    return df


def compute_all_swing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Generates all features necessary for the Swing Trading Engine."""
    if len(df) < 50:
        return df

    df = compute_moving_averages(df)
    df = compute_atr(df, period=14)
    df = compute_rsi(df, period=14)
    df = compute_bollinger_bands(df, period=20)
    df = compute_rvol(df, window=20)

    # 52-Week High and Low Metrics (approx 252 trading days)
    lookback = min(len(df), 252)
    df["High_52W"] = df["High"].rolling(window=lookback).max()
    df["Low_52W"] = df["Low"].rolling(window=lookback).min()

    # Distance metrics
    df["Pct_From_52W_High"] = ((df["High_52W"] - df["Close"]) / df["High_52W"]) * 100.0
    df["Pct_Above_52W_Low"] = ((df["Close"] - df["Low_52W"]) / df["Low_52W"]) * 100.0

    # Volatility Contraction metric: ATR_14 compared to 30-day average ATR
    if "ATR_14" in df.columns:
        df["ATR_Contract_Ratio"] = df["ATR_14"] / (df["ATR_14"].rolling(30).mean() + 1e-9)

    return df


def compute_all_intraday_features(df: pd.DataFrame) -> pd.DataFrame:
    """Generates all features necessary for the Intraday Engine."""
    if len(df) < 15:
        return df

    df = compute_vwap(df)
    df = compute_moving_averages(df)
    df = compute_atr(df, period=14)
    df = compute_rsi(df, period=14)
    df = compute_bollinger_bands(df, period=20)
    df = compute_rvol(df, window=20)

    # Opening Range (First 3 bars of 5m = 15m ORB)
    if len(df) >= 3:
        orb_high = df["High"].iloc[:3].max()
        orb_low = df["Low"].iloc[:3].min()
        df["ORB_High_15m"] = orb_high
        df["ORB_Low_15m"] = orb_low

    return df
