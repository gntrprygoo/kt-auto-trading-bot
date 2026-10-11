#!/usr/bin/env python3
"""Structured P6 range setup plans for research shadow tracking only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from typing import Any, Callable

from ai_market_scanner import (
    MarketScannerConfig,
    MarketScannerError,
    OpenAIMarketScannerClient,
    assert_snapshot_has_no_future_data,
)


RANGE_SETUP_PROMPT_ID = "P6_RANGE_ABSORPTION_SETUP"
RANGE_SETUP_PROMPT_VERSION = "P6_RANGE_ABSORPTION_SETUP_V1_SHADOW"
RANGE_SETUP_SCHEMA_VERSION = "KT_AI_RANGE_SETUP_DECISION_V1"
VALID_ACTIONS = ("SETUP", "NO_TRADE")
VALID_SIDES = ("LONG", "SHORT", "NONE")
VALID_REGIMES = ("RANGE", "TREND", "VOLATILE", "TRANSITION", "UNUSABLE")
VALID_RANGE_BASES = ("24H", "7D", "HYBRID", "NONE")
VALID_TRIGGERS = (
    "LOWER_EDGE_ABSORPTION",
    "LOWER_EDGE_SWEEP_RECLAIM",
    "UPPER_EDGE_ABSORPTION",
    "UPPER_EDGE_SWEEP_RECLAIM",
    "NONE",
)


RANGE_SETUP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": list(VALID_ACTIONS)},
        "pair": {"type": "string", "maxLength": 24},
        "side": {"type": "string", "enum": list(VALID_SIDES)},
        "regime": {"type": "string", "enum": list(VALID_REGIMES)},
        "range_basis": {"type": "string", "enum": list(VALID_RANGE_BASES)},
        "range_low": {"type": "number", "minimum": 0},
        "range_high": {"type": "number", "minimum": 0},
        "entry_zone_low": {"type": "number", "minimum": 0},
        "entry_zone_high": {"type": "number", "minimum": 0},
        "entry_trigger": {"type": "string", "enum": list(VALID_TRIGGERS)},
        "invalidation_level": {"type": "number", "minimum": 0},
        "stop_loss": {"type": "number", "minimum": 0},
        "take_profit_1": {"type": "number", "minimum": 0},
        "take_profit_2": {"type": "number", "minimum": 0},
        "expiry_hours": {"type": "integer", "minimum": 0, "maximum": 12},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "setup_quality": {"type": "integer", "minimum": 0, "maximum": 100},
        "evidence": {
            "type": "array",
            "maxItems": 6,
            "items": {"type": "string", "maxLength": 160},
        },
        "risk_flags": {
            "type": "array",
            "maxItems": 6,
            "items": {"type": "string", "maxLength": 160},
        },
        "thesis": {"type": "string", "maxLength": 300},
        "invalidation_reason": {"type": "string", "maxLength": 220},
    },
    "required": [
        "action",
        "pair",
        "side",
        "regime",
        "range_basis",
        "range_low",
        "range_high",
        "entry_zone_low",
        "entry_zone_high",
        "entry_trigger",
        "invalidation_level",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
        "expiry_hours",
        "confidence",
        "setup_quality",
        "evidence",
        "risk_flags",
        "thesis",
        "invalidation_reason",
    ],
}


RANGE_SETUP_PROMPT = """You are P6, the range-absorption setup planner for a
crypto futures research system. Analyze only the supplied confirmed snapshot.
Return at most one SETUP, otherwise return NO_TRADE. This is shadow research:
never calculate position size, leverage, account risk, or place an order.

Use SETUP only when BTC and the candidate are genuinely range-bound rather than
showing accepted trend expansion. The candidate must be at a relevant range edge
and must show a confirmed lower-edge absorption or sweep-reclaim for LONG, or a
confirmed upper-edge absorption or sweep-reclaim for SHORT. Range location alone
is never enough. Reject mid-range entries, persistent one-sided flow, accepted
high-volume breakouts, stale triggers, and contradictory BTC context.

Follow this workflow:
1. Establish regime and reject non-range conditions.
2. Select one pair and one side only after an observable edge trigger.
3. Select range_low and range_high by copying supplied price levels. For 24H or
   7D use those exact boundaries. HYBRID may combine supplied confirmed hourly
   swing levels with a supplied broad boundary. Never invent a range boundary.
4. Build a narrow tick-aligned entry zone supported by the confirmed trigger.
   The zone must overlap at least one supplied recent confirmed 15-minute bar.
   A sweep-reclaim must show a new edge extreme followed by an inward close;
   absorption must show an inward edge close plus volume or flow improvement.
5. Put invalidation at the structural failure level and stop_loss beyond it.
6. Put TP1 at a defensible internal liquidity or range-mean level and TP2 toward
   the opposing range edge. Do not place either target beyond the selected range.
7. Use 1 to 12 hours expiry. Prefer 4 hours unless structure requires otherwise.
8. Ensure conservative, cost-aware geometry is at least 1.0R to TP1 and 1.8R to
   TP2, using the least favorable edge of the entry zone and 0.20% round-trip cost.

Numeric grounding is mandatory. last_close, range_low/range_high, hourly OHLC,
swing levels, and tick_size are USDT quote-price data for their own symbol.
Fields ending in _pct are percentages, not prices. Never mix values across
symbols. Every output price must match tick_size. Confidence is not a promised
win probability.

For SETUP: action=SETUP, regime=RANGE, pair must be in the universe, side must be
LONG or SHORT, confidence >= 0.60, setup_quality >= 60, and risk_flags must be
empty. Include at least two factual evidence items. For NO_TRADE: pair=NONE,
side=NONE, range_basis=NONE,
entry_trigger=NONE, all price fields and expiry_hours must be zero. Explain the
main blockers in at least one risk_flags item. Keep evidence factual and concise."""


def range_setup_prompt_definition(prompt_id: str = RANGE_SETUP_PROMPT_ID) -> dict:
    normalized = str(prompt_id).upper()
    if normalized != RANGE_SETUP_PROMPT_ID:
        raise MarketScannerError(f"unknown range-setup prompt: {prompt_id}")
    return {
        "id": RANGE_SETUP_PROMPT_ID,
        "version": RANGE_SETUP_PROMPT_VERSION,
        "instructions": RANGE_SETUP_PROMPT,
        "sha256": hashlib.sha256(RANGE_SETUP_PROMPT.encode("utf-8")).hexdigest(),
    }


def _finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _text(value: Any, field: str, maximum: int) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise MarketScannerError(f"{field} is invalid")
    return result


def _text_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 6:
        raise MarketScannerError(f"{field} is invalid")
    result = []
    for item in value:
        result.append(_text(item, f"{field} item", 160))
    return tuple(result)


@dataclass(frozen=True)
class RangeSetupDecision:
    action: str
    pair: str
    side: str
    regime: str
    range_basis: str
    range_low: float
    range_high: float
    entry_zone_low: float
    entry_zone_high: float
    entry_trigger: str
    invalidation_level: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    expiry_hours: int
    confidence: float
    setup_quality: int
    evidence: tuple[str, ...]
    risk_flags: tuple[str, ...]
    thesis: str
    invalidation_reason: str

    @classmethod
    def from_mapping(
        cls, value: Any, universe: list[str] | tuple[str, ...] | None = None
    ) -> "RangeSetupDecision":
        if not isinstance(value, dict):
            raise MarketScannerError("range-setup decision is not an object")
        expected = set(RANGE_SETUP_SCHEMA["properties"])
        extra = set(value) - expected
        missing = expected - set(value)
        if extra or missing:
            raise MarketScannerError(
                f"range-setup fields mismatch missing={sorted(missing)} extra={sorted(extra)}"
            )
        action = str(value["action"]).upper()
        pair = str(value["pair"]).upper()
        side = str(value["side"]).upper()
        regime = str(value["regime"]).upper()
        range_basis = str(value["range_basis"]).upper()
        trigger = str(value["entry_trigger"]).upper()
        if action not in VALID_ACTIONS or side not in VALID_SIDES:
            raise MarketScannerError("range-setup action or side is invalid")
        if regime not in VALID_REGIMES or range_basis not in VALID_RANGE_BASES:
            raise MarketScannerError("range-setup regime or range basis is invalid")
        if trigger not in VALID_TRIGGERS:
            raise MarketScannerError("range-setup trigger is invalid")
        numeric_fields = (
            "range_low",
            "range_high",
            "entry_zone_low",
            "entry_zone_high",
            "invalidation_level",
            "stop_loss",
            "take_profit_1",
            "take_profit_2",
            "confidence",
        )
        if any(not _finite(value[field]) for field in numeric_fields):
            raise MarketScannerError("range-setup contains a non-finite number")
        prices = {field: float(value[field]) for field in numeric_fields[:-1]}
        if any(number < 0 for number in prices.values()):
            raise MarketScannerError("range-setup prices cannot be negative")
        confidence = float(value["confidence"])
        quality = value["setup_quality"]
        expiry = value["expiry_hours"]
        if not 0 <= confidence <= 1:
            raise MarketScannerError("range-setup confidence is invalid")
        if not isinstance(quality, int) or isinstance(quality, bool) or not 0 <= quality <= 100:
            raise MarketScannerError("range-setup quality is invalid")
        if not isinstance(expiry, int) or isinstance(expiry, bool) or not 0 <= expiry <= 12:
            raise MarketScannerError("range-setup expiry is invalid")
        allowed_pairs = {str(item).upper() for item in (universe or [])}
        if action == "NO_TRADE":
            if pair != "NONE" or side != "NONE":
                raise MarketScannerError("NO_TRADE identity is invalid")
            if range_basis != "NONE" or trigger != "NONE" or expiry != 0:
                raise MarketScannerError("NO_TRADE setup fields must be neutral")
            if any(number != 0 for number in prices.values()):
                raise MarketScannerError("NO_TRADE price fields must be zero")
        else:
            if pair not in allowed_pairs or side not in ("LONG", "SHORT"):
                raise MarketScannerError("SETUP pair or side is invalid")
            if regime != "RANGE" or range_basis == "NONE" or trigger == "NONE":
                raise MarketScannerError("SETUP must contain a range and trigger")
            if confidence < 0.60 or quality < 60:
                raise MarketScannerError("SETUP confidence or quality is below policy")
            if expiry < 1:
                raise MarketScannerError("SETUP expiry must be at least one hour")
        evidence = _text_list(value["evidence"], "evidence")
        risk_flags = _text_list(value["risk_flags"], "risk_flags")
        if action == "SETUP" and risk_flags:
            raise MarketScannerError("SETUP cannot contain material risk flags")
        if action == "SETUP" and len(evidence) < 2:
            raise MarketScannerError("SETUP requires at least two factual evidence items")
        if action == "NO_TRADE" and not risk_flags:
            raise MarketScannerError("NO_TRADE requires at least one blocker")
        return cls(
            action=action,
            pair=pair,
            side=side,
            regime=regime,
            range_basis=range_basis,
            entry_trigger=trigger,
            expiry_hours=expiry,
            confidence=confidence,
            setup_quality=quality,
            evidence=evidence,
            risk_flags=risk_flags,
            thesis=_text(value["thesis"], "thesis", 300),
            invalidation_reason=_text(
                value["invalidation_reason"], "invalidation_reason", 220
            ),
            **prices,
        )

    def as_dict(self) -> dict:
        value = asdict(self)
        value["evidence"] = list(self.evidence)
        value["risk_flags"] = list(self.risk_flags)
        return value


def _tick_aligned(value: float, tick_size: float) -> bool:
    try:
        value_d = Decimal(str(value))
        tick_d = Decimal(str(tick_size))
        if value_d <= 0 or tick_d <= 0:
            return False
        quotient = value_d / tick_d
        return quotient == quotient.to_integral_value()
    except (InvalidOperation, ZeroDivisionError):
        return False


def _matches_level(value: float, candidates: list[float], tick_size: float) -> bool:
    tolerance = max(tick_size * 0.51, abs(value) * 1e-9)
    return any(abs(value - candidate) <= tolerance for candidate in candidates)


def _candidate_levels(features: dict, side: str) -> list[float]:
    keys = (
        ("range_low_24h", "range_low_7d", "recent_swing_lows_1h")
        if side == "LOW"
        else ("range_high_24h", "range_high_7d", "recent_swing_highs_1h")
    )
    result: list[float] = []
    for key in keys[:2]:
        if _finite(features.get(key)):
            result.append(float(features[key]))
    swings = features.get(keys[2])
    for item in swings if isinstance(swings, list) else []:
        price = item.get("price") if isinstance(item, dict) else item
        if _finite(price):
            result.append(float(price))
    return result


def _claimed_trigger_is_grounded(
    decision: RangeSetupDecision,
    features: dict,
    atr: float,
    tick: float,
) -> bool:
    bars = features.get("recent_15m_bars")
    if not isinstance(bars, list) or len(bars) < 2:
        return False
    usable = [row for row in bars if isinstance(row, dict)]
    if len(usable) < 2:
        return False
    edge = decision.range_low if decision.side == "LONG" else decision.range_high
    lower = decision.side == "LONG"
    edge_distance = max(atr * 0.35, tick * 2.0)

    def near_edge(row: dict) -> bool:
        probe = float(row["low"] if lower else row["high"])
        return probe <= edge + edge_distance if lower else probe >= edge - edge_distance

    if "SWEEP_RECLAIM" in decision.entry_trigger:
        for index, row in enumerate(usable):
            probe = float(row["low"] if lower else row["high"])
            close = float(row["close"])
            close_location = float(row.get("close_location", 0.5) or 0.5)
            touched = probe <= edge + tick if lower else probe >= edge - tick
            reclaimed = close > edge + tick if lower else close < edge - tick
            closed_inward = close_location >= 0.55 if lower else close_location <= 0.45
            earlier = usable[:index]
            made_new_extreme = any(
                float(item["low"] if lower else item["high"])
                > edge + tick
                if lower
                else float(item["high"]) < edge - tick
                for item in earlier
            )
            if touched and reclaimed and closed_inward and made_new_extreme:
                return True
        return False

    touches = [row for row in usable if near_edge(row)]
    if not touches:
        return False
    for index, row in enumerate(usable):
        if row not in touches:
            continue
        close_location = float(row.get("close_location", 0.5) or 0.5)
        volume_ratio = float(row.get("volume_ratio", 0) or 0)
        flow = float(row.get("taker_flow", 0) or 0)
        previous_flow = (
            float(usable[index - 1].get("taker_flow", 0) or 0)
            if index > 0
            else flow
        )
        closed_inward = close_location >= 0.55 if lower else close_location <= 0.45
        flow_recovered = flow > previous_flow if lower else flow < previous_flow
        if closed_inward and (volume_ratio >= 1.0 or flow_recovered):
            return True
    return False


def validate_range_setup(
    decision: RangeSetupDecision,
    snapshot: dict,
    round_trip_cost_pct: float = 0.002,
    min_rr_tp1: float = 1.0,
    min_rr_tp2: float = 1.8,
) -> dict | None:
    """Validate AI-selected levels without choosing or changing those levels."""
    if decision.action == "NO_TRADE":
        return None
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    features = market.get(decision.pair)
    if not isinstance(features, dict):
        raise MarketScannerError("selected setup pair has no market features")
    tick_size = features.get("tick_size")
    if not _finite(tick_size) or float(tick_size) <= 0:
        raise MarketScannerError("selected setup pair has no valid Binance tick size")
    tick = float(tick_size)
    price_fields = (
        "range_low",
        "range_high",
        "entry_zone_low",
        "entry_zone_high",
        "invalidation_level",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
    )
    for field in price_fields:
        if not _tick_aligned(float(getattr(decision, field)), tick):
            raise MarketScannerError(f"{field} is not aligned to Binance tick size")
    low_candidates = _candidate_levels(features, "LOW")
    high_candidates = _candidate_levels(features, "HIGH")
    if not _matches_level(decision.range_low, low_candidates, tick):
        raise MarketScannerError("range_low is not grounded in supplied structure")
    if not _matches_level(decision.range_high, high_candidates, tick):
        raise MarketScannerError("range_high is not grounded in supplied structure")
    if decision.range_basis == "24H":
        if not _matches_level(decision.range_low, [float(features["range_low_24h"])], tick):
            raise MarketScannerError("24H range_low does not match the supplied boundary")
        if not _matches_level(decision.range_high, [float(features["range_high_24h"])], tick):
            raise MarketScannerError("24H range_high does not match the supplied boundary")
    elif decision.range_basis == "7D":
        if not _matches_level(decision.range_low, [float(features["range_low_7d"])], tick):
            raise MarketScannerError("7D range_low does not match the supplied boundary")
        if not _matches_level(decision.range_high, [float(features["range_high_7d"])], tick):
            raise MarketScannerError("7D range_high does not match the supplied boundary")
    elif decision.range_basis == "HYBRID":
        low_broad = _matches_level(
            decision.range_low,
            [float(features["range_low_24h"]), float(features["range_low_7d"])],
            tick,
        )
        high_broad = _matches_level(
            decision.range_high,
            [float(features["range_high_24h"]), float(features["range_high_7d"])],
            tick,
        )
        low_swings = _candidate_levels(features, "LOW")[2:]
        high_swings = _candidate_levels(features, "HIGH")[2:]
        low_swing = _matches_level(decision.range_low, low_swings, tick)
        high_swing = _matches_level(decision.range_high, high_swings, tick)
        if not ((low_broad and high_swing) or (low_swing and high_broad)):
            raise MarketScannerError(
                "HYBRID range must combine one broad boundary and one confirmed swing"
            )
    if not decision.range_low < decision.range_high:
        raise MarketScannerError("selected range is inverted")
    range_width = decision.range_high - decision.range_low
    atr = float(features.get("atr_price") or 0)
    if atr <= 0 or range_width < 2.0 * atr:
        raise MarketScannerError("selected range is too narrow relative to ATR")
    if not decision.range_low <= decision.entry_zone_low <= decision.entry_zone_high <= decision.range_high:
        raise MarketScannerError("entry zone is outside the selected range")
    zone_width = decision.entry_zone_high - decision.entry_zone_low
    if zone_width < tick or zone_width > atr:
        raise MarketScannerError("entry zone width is invalid relative to tick/ATR")
    last_close = float(features["last_close"])
    distance_to_zone = max(
        decision.entry_zone_low - last_close,
        last_close - decision.entry_zone_high,
        0.0,
    )
    if distance_to_zone > 1.5 * atr:
        raise MarketScannerError("entry zone is stale or too far from current price")
    recent_bars = features.get("recent_15m_bars")
    if not isinstance(recent_bars, list) or not any(
        isinstance(row, dict)
        and float(row["low"]) <= decision.entry_zone_high
        and float(row["high"]) >= decision.entry_zone_low
        for row in recent_bars
    ):
        raise MarketScannerError("entry zone is not grounded in recent confirmed bars")
    if not _claimed_trigger_is_grounded(decision, features, atr, tick):
        raise MarketScannerError("claimed edge trigger is not grounded in recent bars")
    midpoint = (decision.entry_zone_low + decision.entry_zone_high) / 2.0
    location = (midpoint - decision.range_low) / range_width
    if decision.side == "LONG":
        if decision.entry_trigger not in (
            "LOWER_EDGE_ABSORPTION",
            "LOWER_EDGE_SWEEP_RECLAIM",
        ):
            raise MarketScannerError("LONG setup uses an upper-edge trigger")
        if location > 0.35:
            raise MarketScannerError("LONG entry is not near the lower range edge")
        if not (
            decision.stop_loss <= decision.invalidation_level - tick
            and decision.invalidation_level <= decision.range_low
        ):
            raise MarketScannerError("LONG invalidation/stop is not below the range")
        if not decision.entry_zone_high < decision.take_profit_1 < decision.take_profit_2 <= decision.range_high:
            raise MarketScannerError("LONG targets are inconsistent with the range")
        conservative_entry = decision.entry_zone_high
        gross_risk = conservative_entry - decision.stop_loss
        reward_tp1 = decision.take_profit_1 - conservative_entry
        reward_tp2 = decision.take_profit_2 - conservative_entry
    else:
        if decision.entry_trigger not in (
            "UPPER_EDGE_ABSORPTION",
            "UPPER_EDGE_SWEEP_RECLAIM",
        ):
            raise MarketScannerError("SHORT setup uses a lower-edge trigger")
        if location < 0.65:
            raise MarketScannerError("SHORT entry is not near the upper range edge")
        if not (
            decision.stop_loss >= decision.invalidation_level + tick
            and decision.invalidation_level >= decision.range_high
        ):
            raise MarketScannerError("SHORT invalidation/stop is not above the range")
        if not decision.entry_zone_low > decision.take_profit_1 > decision.take_profit_2 >= decision.range_low:
            raise MarketScannerError("SHORT targets are inconsistent with the range")
        conservative_entry = decision.entry_zone_low
        gross_risk = decision.stop_loss - conservative_entry
        reward_tp1 = conservative_entry - decision.take_profit_1
        reward_tp2 = conservative_entry - decision.take_profit_2
    if gross_risk <= 0:
        raise MarketScannerError("setup risk distance is invalid")
    if gross_risk > max(3.0 * atr, conservative_entry * 0.03):
        raise MarketScannerError("setup stop distance exceeds the safety bound")
    estimated_cost = conservative_entry * float(round_trip_cost_pct)
    cost_adjusted_risk = gross_risk + estimated_cost
    rr_tp1 = (reward_tp1 - estimated_cost) / cost_adjusted_risk
    rr_tp2 = (reward_tp2 - estimated_cost) / cost_adjusted_risk
    if rr_tp1 < min_rr_tp1 or rr_tp2 < min_rr_tp2:
        raise MarketScannerError(
            f"cost-adjusted R:R below gate: TP1={rr_tp1:.2f} TP2={rr_tp2:.2f}"
        )
    return {
        "schema": "KT_AI_RANGE_SETUP_VALIDATION_V1",
        "status": "VALIDATED_SHADOW_ONLY",
        "orders_allowed": False,
        "pair": decision.pair,
        "side": decision.side,
        "tick_size": tick,
        "last_close": last_close,
        "conservative_entry": conservative_entry,
        "gross_risk_per_unit": gross_risk,
        "round_trip_cost_pct": float(round_trip_cost_pct),
        "cost_adjusted_rr_tp1": round(rr_tp1, 4),
        "cost_adjusted_rr_tp2": round(rr_tp2, 4),
        "range_position_pct": round(location * 100.0, 2),
        "expiry_hours": decision.expiry_hours,
    }


class OpenAIRangeSetupClient:
    def __init__(
        self,
        config: MarketScannerConfig | None = None,
        transport: Callable[[str, dict, dict, int], dict] | None = None,
    ) -> None:
        self.base = OpenAIMarketScannerClient(config, transport)
        self.config = self.base.config

    def decide(
        self, snapshot: dict, prompt_id: str = RANGE_SETUP_PROMPT_ID
    ) -> tuple[RangeSetupDecision, dict]:
        if not self.config.api_key:
            raise MarketScannerError(f"{self.config.api_key_env} is not configured")
        assert_snapshot_has_no_future_data(snapshot)
        prompt = range_setup_prompt_definition(prompt_id)
        payload = {
            "model": self.config.model,
            "store": False,
            "instructions": prompt["instructions"],
            "input": json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
            "reasoning": {"effort": self.config.reasoning_effort},
            "max_output_tokens": self.config.max_output_tokens,
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "ai_range_setup_decision",
                    "strict": True,
                    "schema": RANGE_SETUP_SCHEMA,
                },
            },
        }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        response = self.base.transport(
            "https://api.openai.com/v1/responses",
            payload,
            {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            self.config.timeout_sec,
        )
        try:
            raw = json.loads(self.base._output_text(response))
        except json.JSONDecodeError as exc:
            raise MarketScannerError("OpenAI range-setup output is not valid JSON") from exc
        universe = snapshot.get("universe") if isinstance(snapshot.get("universe"), list) else []
        decision = RangeSetupDecision.from_mapping(raw, universe)
        metadata = {
            "response_id": response.get("id"),
            "model": response.get("model") or self.config.model,
            "request_hash": request_hash,
            "prompt_id": prompt["id"],
            "prompt_version": prompt["version"],
            "prompt_sha256": prompt["sha256"],
            "usage": response.get("usage") if isinstance(response.get("usage"), dict) else {},
        }
        return decision, metadata
