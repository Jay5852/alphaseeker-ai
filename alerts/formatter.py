from typing import Optional
from risk.manager import TradeOrderTicket
from ml.time_predictor import HoldingPrediction
from ml.meta_labeler import MetaLabelResult
from engines.confluence_scorer import ConfluenceResult


def format_trade_ticket_text(
    ticket: TradeOrderTicket,
    pattern_name: str,
    notes: str = "",
    time_prediction: Optional[HoldingPrediction] = None,
    meta_label: Optional[MetaLabelResult] = None,
    confluence: Optional[ConfluenceResult] = None
) -> str:
    """Formats a TradeOrderTicket into a structured markdown message suitable for Telegram, Discord, or UI."""
    is_long = ticket.direction.upper() == "LONG"
    direction_emoji = "🟢 LONG / BUY" if is_long else "🔴 SHORT / SELL"
    timeframe_tag = f"#{ticket.timeframe}"

    currency = "₹" if ".NS" in ticket.ticker else "$"
    clean_ticker = ticket.ticker.replace(".NS", "")

    header = f"🚨 **ALPHA TRADE SIGNAL: {clean_ticker}** | {timeframe_tag}"
    divider = "────────────────────────────"

    lines = [
        header,
        divider,
        f"**Direction:** {direction_emoji}",
        f"**Setup Pattern:** `{pattern_name}`",
        f"**Market Entry:** `{currency}{ticket.entry_price:.2f}`",
        f"**Stop Loss:** `{currency}{ticket.stop_loss:.2f}` (Risk: `{currency}{ticket.risk_per_share:.2f}`/sh)",
        f"**Target 1 (2.0R):** `{currency}{ticket.target_1:.2f}` [R:R `{ticket.risk_reward_ratio_t1:.1f}:1`]",
        f"**Target 2 (3.5R):** `{currency}{ticket.target_2:.2f}` [R:R `{ticket.risk_reward_ratio_t2:.1f}:1`]",
        divider,
        "**RISK & POSITION SIZING:**",
        f"• **Recommended Qty:** `{ticket.recommended_shares}` shares",
        f"• **Capital Required:** `{currency}{ticket.capital_required:,.2f}`",
        f"• **Max Capital at Risk:** `{currency}{ticket.dollar_risk_amount:,.2f}` (`{ticket.risk_pct_of_capital}%`)",
    ]

    if time_prediction:
        lines.append(divider)
        lines.append(f"⏱️ **TIMELINE & HOLDING PREDICTION:**")
        lines.append(f"• **Est. Hold:** `{time_prediction.hold_q25} – {time_prediction.hold_q75} {time_prediction.unit}` (median ~{time_prediction.hold_median})")
        lines.append(f"• **Target 1 ETA:** `{time_prediction.target_1_eta}` ({time_prediction.target_1_eta_range})")
        lines.append(f"• **Target 2 ETA:** `{time_prediction.target_2_eta}` ({time_prediction.target_2_eta_range})")
        lines.append(f"• **Time-Stop:** If no T1 by `{time_prediction.time_stop_date}` → **AUTO EXIT**")
        lines.append(f"• **Target 1 Probability:** `{time_prediction.survival_prob_t1:.0%}`")

    if meta_label:
        lines.append(divider)
        lines.append(f"🤖 **QUANT ML META-LABEL (Upgrade B):**")
        lines.append(f"• **Win Probability:** `{meta_label.win_probability:.1%}` [{meta_label.confidence_tier}]")
        if meta_label.top_positive_factors:
            lines.append(f"• **Primary Edge:** {', '.join(meta_label.top_positive_factors[:2])}")

    if confluence:
        lines.append(divider)
        lines.append(f"📊 **MULTI-TIMEFRAME CONFLUENCE (Improvement G):**")
        lines.append(f"• **Score:** `{confluence.score}/{confluence.max_score}` — {confluence.badge}")
        for chk in confluence.checks:
            icon = "✅" if chk.aligned else "❌"
            lines.append(f"  {icon} **{chk.timeframe}**: {chk.reason}")

    if notes:
        lines.append(divider)
        lines.append(f"• **Catalyst / Context:** {notes}")

    lines.append(divider)
    lines.append("⚠️ *Disciplined execution: Exit immediately if Stop Loss triggers. Trail stops after Target 1.*")

    return "\n".join(lines)
