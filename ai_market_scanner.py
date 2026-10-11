"""Bounded OpenAI market-scanner primitives for research and signal modes.

The model selects at most one market and direction from a point-in-time
snapshot. Position sizing, leverage, stops, targets, and order execution remain
deterministic responsibilities of the application.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from typing import Any, Callable
import urllib.error
import urllib.request


SCANNER_SCHEMA = "KT_AI_MARKET_SCANNER_V1"
SCANNER_PROMPT_FAMILY = "KT_AI_MARKET_PROMPT_TOURNAMENT_V2_2026_08_06"
VALID_ACTIONS = ("TRADE", "NO_TRADE")
VALID_SIDES = ("LONG", "SHORT", "NONE")
VALID_REGIMES = ("TREND", "RANGE", "VOLATILE", "TRANSITION", "UNUSABLE")


DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": list(VALID_ACTIONS)},
        "pair": {"type": "string", "maxLength": 24},
        "side": {"type": "string", "enum": list(VALID_SIDES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "regime": {"type": "string", "enum": list(VALID_REGIMES)},
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
        "invalidation": {"type": "string", "maxLength": 220},
    },
    "required": [
        "action",
        "pair",
        "side",
        "confidence",
        "regime",
        "setup_quality",
        "evidence",
        "risk_flags",
        "thesis",
        "invalidation",
    ],
}


COMMON_POLICY = """You are the market-analysis layer for a crypto futures research system.
Analyze only the point-in-time snapshot supplied by the caller. Select at most one
pair and one direction, or return NO_TRADE. Never assume future prices or missing
data. Do not calculate quantity, leverage, account risk, stop, target, or order
type; deterministic code owns execution geometry and risk. Treat NO_TRADE as the
correct default when evidence conflicts, the market is transitioning, data is
weak, or the setup is late. Confidence measures confidence in this decision, not
a promised win probability. A TRADE decision must identify a pair listed in the
snapshot universe and use LONG or SHORT. A NO_TRADE decision must use pair NONE
and side NONE. Keep evidence, thesis, and invalidation concise and factual."""


COMMON_POLICY_V2 = """You are the market-selection layer for a crypto futures
research system. Analyze only the point-in-time snapshot. Select at most one
pair and direction for the next 12 hours, or return NO_TRADE. The application
will enter at the next 15-minute open with a deterministic volatility stop, 2R
target, and modeled round-trip cost up to 0.20 percent. Never use future data or
invent missing facts. Never calculate quantity, leverage, account risk, entry,
stop, target, or order type.

Use NO_TRADE for genuine absence of positive expectancy, not merely because all
trading contains uncertainty. Across a broad representative sample, actionable
setups may reasonably occur in roughly 10 to 25 percent of snapshots; this is
calibration guidance, never a quota. For TRADE, confidence must be at least 0.60,
setup_quality at least 60, regime cannot be TRANSITION or UNUSABLE, and
risk_flags must be an empty array. Any material blocker requires NO_TRADE and
must be listed in risk_flags. Normal uncertainty belongs in the thesis, not in
risk_flags. Confidence is not a promised win probability. A TRADE pair must be
in the supplied universe and use LONG or SHORT. NO_TRADE must use pair NONE and
side NONE. Keep each evidence item under 120 characters."""


PROMPT_VARIANTS = {
    "P1_REGIME_STRUCTURE": {
        "version": "P1_REGIME_STRUCTURE_V1",
        "instructions": COMMON_POLICY
        + """

Method: regime and structure first. Establish the BTC regime, then compare each
tradable pair's 4h and 24h direction, EMA alignment, distance from trend, range
position, volatility, and relative strength versus BTC. Prefer continuation after
acceptance or an orderly pullback in an established regime. Reject moves that are
already extended at the edge of their range, weakly confirmed, or opposed by the
BTC regime. In ranges, trade only unusually clear rejection evidence; otherwise
return NO_TRADE.""",
    },
    "P2_LIQUIDITY_FLOW": {
        "version": "P2_LIQUIDITY_FLOW_V1",
        "instructions": COMMON_POLICY
        + """

Method: auction, liquidity, and flow first. Compare taker-flow persistence,
relative volume, candle close location, volatility expansion, range position,
and divergence from BTC. Look for evidence of accepted expansion, absorption,
or a sweep-and-reclaim proxy rather than merely a large candle. Do not chase an
exhausted move and do not fade persistent flow without clear rejection evidence.
When flow, price response, and higher-timeframe context disagree, return
NO_TRADE.""",
    },
    "P3_CONSERVATIVE_CONFLUENCE": {
        "version": "P3_CONSERVATIVE_CONFLUENCE_V1",
        "instructions": COMMON_POLICY
        + """

Method: conservative multi-factor confluence. Independently assess five pillars:
BTC regime, pair trend, market structure/location, participation/flow, and
volatility quality. Return TRADE only when at least four pillars align in the
same direction and no material tail-risk flag remains. Penalize crowded extension,
mixed timeframes, thin participation, transition regimes, and one-factor setups.
Prefer missing a trade over accepting a marginal setup.""",
    },
    "P4_LONG_REGIME_PULLBACK": {
        "version": "P4_LONG_REGIME_PULLBACK_V2",
        "instructions": COMMON_POLICY_V2
        + """

Method: long-only crypto regime pullback. Return TRADE only with side LONG.
First require BTC to show a constructive or recovering 12h/24h context without
clear persistent downside flow. Then rank pairs by positive 12h/24h trend,
relative strength versus BTC, EMA condition, and 4h participation. Prefer the
strongest pair after an orderly 1h pullback or pause, while its higher-timeframe
trend remains intact. A slightly negative 1h return can improve location; a
large positive 1h impulse near the 24h or 7d high is chase risk and should be
rejected. Reject weak relative strength, strongly negative 4h taker flow, thin
participation, or a structurally bearish BTC backdrop. Do not issue SHORT.""",
    },
    "P5_BALANCED_TREND_CONTINUATION": {
        "version": "P5_BALANCED_TREND_CONTINUATION_V2",
        "instructions": COMMON_POLICY_V2
        + """

Method: symmetric trend continuation with location discipline. Identify whether
BTC and cross-market breadth support LONG, SHORT, or neither. For each pair,
require coherent 4h, 12h, and 24h direction, compatible EMA spread, persistent
or improving 4h taker flow, and adequate volume. Prefer a pause or shallow
countertrend 1h move followed by a supportive latest close. Reject isolated
one-hour momentum, late entries at an extreme range position, disagreement
between BTC and the candidate, and apparent trend transitions. Select the best
risk-adjusted continuation across the universe, not simply the largest return.""",
    },
    "P6_RANGE_ABSORPTION_REVERSAL": {
        "version": "P6_RANGE_ABSORPTION_REVERSAL_V3_GROUNDED",
        "instructions": COMMON_POLICY_V2
        + """

Method: range-edge absorption and reversion. Use this only when BTC and the
candidate lack a clean persistent trend. Seek LONG near the lower 24h/7d range
after downside pressure fails to produce a weak close and taker flow stabilizes
or improves. Seek SHORT near the upper range after upside pressure fails to
produce a strong close and taker flow deteriorates. The hourly return, flow,
and volume sequences must show exhaustion or absorption rather than continued
one-sided expansion. Reject mid-range entries, high-volume accepted breakouts,
strong EMA trend continuation, and reversals based on range position alone."""
        + """

Numeric grounding is mandatory. In grounded live snapshots, last_close and
range_low/range_high fields are USDT quote prices. Fields ending in _pct are
percentages on a 0-to-100 scale and are never prices. Legacy replay fields named
range_position_24h or range_position_7d are fractions on a 0-to-1 scale and are
also never prices. Never mix values between symbols. Quote a numeric market price
only by copying a price field for the selected pair; otherwise describe the
evidence qualitatively.""",
    },
}


FORBIDDEN_SNAPSHOT_FIELDS = {
    "outcomes",
    "outcome",
    "future",
    "exit_time",
    "exit_price",
    "exit_reason",
    "gross_r",
    "baseline_net_r",
    "stress_net_r",
    "result_r",
    "winner",
    "label",
}


class MarketScannerError(RuntimeError):
    pass


def _finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in (float("inf"), float("-inf"))


def assert_snapshot_has_no_future_data(snapshot: dict) -> None:
    def walk(value: Any, path: str = "root") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).lower()
                if normalized in FORBIDDEN_SNAPSHOT_FIELDS:
                    raise MarketScannerError(
                        f"future field leaked into scanner snapshot: {path}.{key}"
                    )
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    if not isinstance(snapshot, dict):
        raise MarketScannerError("market snapshot must be an object")
    walk(snapshot)


def prompt_definition(prompt_id: str) -> dict:
    prompt = PROMPT_VARIANTS.get(str(prompt_id).upper())
    if not prompt:
        raise MarketScannerError(f"unknown market-scanner prompt: {prompt_id}")
    instructions = str(prompt["instructions"])
    return {
        "id": str(prompt_id).upper(),
        "version": str(prompt["version"]),
        "instructions": instructions,
        "sha256": hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
    }


@dataclass(frozen=True)
class MarketScanDecision:
    action: str
    pair: str
    side: str
    confidence: float
    regime: str
    setup_quality: int
    evidence: tuple[str, ...]
    risk_flags: tuple[str, ...]
    thesis: str
    invalidation: str

    @classmethod
    def from_mapping(
        cls, value: Any, universe: list[str] | tuple[str, ...] | None = None
    ) -> "MarketScanDecision":
        if not isinstance(value, dict):
            raise MarketScannerError("market-scanner decision is not an object")
        expected = set(DECISION_SCHEMA["properties"])
        extra = set(value) - expected
        if extra:
            raise MarketScannerError(
                f"market-scanner decision has unknown fields: {sorted(extra)}"
            )
        action = str(value.get("action", "")).upper()
        pair = str(value.get("pair", "")).upper()
        side = str(value.get("side", "")).upper()
        regime = str(value.get("regime", "")).upper()
        confidence = value.get("confidence")
        quality = value.get("setup_quality")
        if action not in VALID_ACTIONS:
            raise MarketScannerError("action must be TRADE or NO_TRADE")
        if side not in VALID_SIDES:
            raise MarketScannerError("side must be LONG, SHORT, or NONE")
        if regime not in VALID_REGIMES:
            raise MarketScannerError("market regime is invalid")
        if not _finite_number(confidence) or not 0 <= float(confidence) <= 1:
            raise MarketScannerError("confidence is invalid")
        if not isinstance(quality, int) or isinstance(quality, bool) or not 0 <= quality <= 100:
            raise MarketScannerError("setup quality is invalid")
        allowed_pairs = {str(item).upper() for item in (universe or [])}
        if action == "NO_TRADE":
            if pair != "NONE" or side != "NONE":
                raise MarketScannerError("NO_TRADE must use pair NONE and side NONE")
        else:
            if side not in ("LONG", "SHORT"):
                raise MarketScannerError("TRADE must use LONG or SHORT")
            if not pair or pair == "NONE" or (allowed_pairs and pair not in allowed_pairs):
                raise MarketScannerError("TRADE pair is outside the snapshot universe")
        evidence = _clean_text_list(value.get("evidence"), "evidence")
        risk_flags = _clean_text_list(value.get("risk_flags"), "risk_flags")
        thesis = _clean_text(value.get("thesis"), "thesis", 300)
        invalidation = _clean_text(value.get("invalidation"), "invalidation", 220)
        return cls(
            action=action,
            pair=pair,
            side=side,
            confidence=float(confidence),
            regime=regime,
            setup_quality=quality,
            evidence=tuple(evidence),
            risk_flags=tuple(risk_flags),
            thesis=thesis,
            invalidation=invalidation,
        )

    def as_dict(self) -> dict:
        value = asdict(self)
        value["evidence"] = list(self.evidence)
        value["risk_flags"] = list(self.risk_flags)
        return value


def _clean_text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 6:
        raise MarketScannerError(f"{field} is invalid")
    result = []
    for item in value:
        clean = str(item).strip()
        if not clean or len(clean) > 160:
            raise MarketScannerError(f"{field} item is invalid")
        result.append(clean)
    return result


def _clean_text(value: Any, field: str, max_length: int) -> str:
    clean = str(value or "").strip()
    if not clean or len(clean) > max_length:
        raise MarketScannerError(f"{field} is invalid")
    return clean


@dataclass(frozen=True)
class MarketScannerConfig:
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_sec: int = 45
    max_output_tokens: int = 1200

    @property
    def api_key(self) -> str:
        return str(os.getenv(self.api_key_env, "")).strip()


class OpenAIMarketScannerClient:
    def __init__(
        self,
        config: MarketScannerConfig | None = None,
        transport: Callable[[str, dict, dict, int], dict] | None = None,
    ) -> None:
        self.config = config or MarketScannerConfig()
        self.transport = transport or self._default_transport

    @staticmethod
    def _default_transport(url: str, payload: dict, headers: dict, timeout: int) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise MarketScannerError(f"OpenAI HTTP {exc.code}: {body[:500]}") from exc
        except Exception as exc:
            raise MarketScannerError(f"OpenAI request failed: {exc}") from exc

    @staticmethod
    def _output_text(response: dict) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        output = response.get("output")
        for item in output if isinstance(output, list) else []:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            for block in content if isinstance(content, list) else []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "output_text"
                    and isinstance(block.get("text"), str)
                ):
                    return block["text"].strip()
        raise MarketScannerError("OpenAI response has no output text")

    def build_request(self, snapshot: dict, prompt_id: str) -> tuple[dict, dict]:
        assert_snapshot_has_no_future_data(snapshot)
        prompt = prompt_definition(prompt_id)
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
                    "name": "ai_market_scan_decision",
                    "strict": True,
                    "schema": DECISION_SCHEMA,
                },
            },
        }
        return payload, prompt

    def decide(self, snapshot: dict, prompt_id: str) -> tuple[MarketScanDecision, dict]:
        if not self.config.api_key:
            raise MarketScannerError(f"{self.config.api_key_env} is not configured")
        payload, prompt = self.build_request(snapshot, prompt_id)
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        response = self.transport(
            "https://api.openai.com/v1/responses",
            payload,
            {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            self.config.timeout_sec,
        )
        try:
            raw = json.loads(self._output_text(response))
        except json.JSONDecodeError as exc:
            raise MarketScannerError("OpenAI market-scanner output is not valid JSON") from exc
        universe = snapshot.get("universe") if isinstance(snapshot.get("universe"), list) else []
        decision = MarketScanDecision.from_mapping(raw, universe)
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
