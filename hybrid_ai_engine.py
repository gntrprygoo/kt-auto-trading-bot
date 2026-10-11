"""Fail-closed Hybrid AI review and execution-routing primitives.

The model is a bounded reviewer. It cannot choose direction, prices, quantity,
or account risk. Binance execution stays in the main bot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request


ENGINE_SCHEMA = "KT_HYBRID_AI_STATE_V1"
LIVE_GATE_SCHEMA = "KT_HYBRID_AI_GATE_V1"
PROMPT_VERSION = "KT_HYBRID_REVIEW_V1_2026_08_05"
VALID_MODES = ("AI_SHADOW", "AI_APPROVAL", "AI_LIVE")
VALID_ACTIONS = ("TRADE", "SKIP")
VALID_REGIMES = ("TREND", "RANGE", "VOLATILE", "TRANSITION", "UNUSABLE")


DECISION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": list(VALID_ACTIONS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "regime": {"type": "string", "enum": list(VALID_REGIMES)},
        "setup_quality": {"type": "integer", "minimum": 0, "maximum": 100},
        "risk_flags": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "maxLength": 80},
        },
        "thesis": {"type": "string", "maxLength": 240},
        "invalidation": {"type": "string", "maxLength": 200},
    },
    "required": [
        "action",
        "confidence",
        "regime",
        "setup_quality",
        "risk_flags",
        "thesis",
        "invalidation",
    ],
}


SYSTEM_INSTRUCTIONS = """You are the risk-first review layer for a crypto futures system.
You may only accept or veto the deterministic candidate supplied by the caller.
You must not change or invent its side, entry, stop, targets, quantity, leverage,
or risk. Use only data present in the snapshot and never assume future prices.
Return TRADE only when direction, regime, flow, structure, and reward-to-risk are
coherent and the evidence is sufficient. Return SKIP for ambiguity, conflict,
stale or missing evidence, transition regimes, crowded conditions, or avoidable
tail risk. Confidence is confidence in the TRADE/SKIP decision, not a promised
win probability. Keep the thesis and invalidation concise and factual."""


class HybridAIError(RuntimeError):
    pass


class HybridAIStateError(HybridAIError):
    pass


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def candidate_id(candidate: dict) -> str:
    identity = {
        "pair": str(candidate.get("pair", "")).upper(),
        "side": str(candidate.get("side", "")).upper(),
        "signal_time_ms": int(candidate.get("signal_time_ms", 0) or 0),
        "entry": float(candidate.get("entry", 0) or 0),
        "sl": float(candidate.get("sl", 0) or 0),
        "tp2": float(candidate.get("tp2", candidate.get("tp", 0)) or 0),
        "strategy": str(candidate.get("strategy", "")),
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "AI-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


@dataclass(frozen=True)
class HybridAIConfig:
    enabled: bool = False
    initial_mode: str = "AI_SHADOW"
    preserve_baseline_in_shadow: bool = True
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"
    api_key_env: str = "OPENAI_API_KEY"
    request_timeout_sec: int = 30
    max_parallel_calls: int = 2
    min_confidence: float = 0.72
    min_setup_quality: int = 65
    min_rr: float = 1.50
    max_stop_pct: float = 0.03
    max_account_risk_pct: float = 0.0025
    max_notional_usdt: float = 10.0
    max_open_positions: int = 1
    max_daily_loss_r: float = -1.0
    max_candidate_age_sec: int = 20 * 60
    approval_ttl_sec: int = 5 * 60
    max_price_deviation_pct: float = 0.003
    allow_live: bool = False
    state_path: str = ""
    live_gate_path: str = ""

    @classmethod
    def from_mapping(cls, value: Any, data_dir: str | Path) -> "HybridAIConfig":
        raw = value if isinstance(value, dict) else {}
        data_root = Path(data_dir)
        initial_mode = str(raw.get("mode", "AI_SHADOW")).upper()
        if initial_mode not in VALID_MODES:
            initial_mode = "AI_SHADOW"
        return cls(
            enabled=bool(raw.get("enabled", False)),
            initial_mode=initial_mode,
            preserve_baseline_in_shadow=bool(raw.get("preserve_baseline_in_shadow", True)),
            model=str(raw.get("model", "gpt-5.6-luna")).strip() or "gpt-5.6-luna",
            reasoning_effort=str(raw.get("reasoning_effort", "low")).strip() or "low",
            api_key_env=str(raw.get("api_key_env", "OPENAI_API_KEY")).strip() or "OPENAI_API_KEY",
            request_timeout_sec=max(5, min(120, int(raw.get("request_timeout_sec", 30)))),
            max_parallel_calls=max(1, min(4, int(raw.get("max_parallel_calls", 2)))),
            min_confidence=max(0.5, min(0.99, float(raw.get("min_confidence", 0.72)))),
            min_setup_quality=max(0, min(100, int(raw.get("min_setup_quality", 65)))),
            min_rr=max(1.0, float(raw.get("min_rr", 1.50))),
            max_stop_pct=max(0.003, min(0.10, float(raw.get("max_stop_pct", 0.03)))),
            max_account_risk_pct=max(
                0.0001, min(0.01, float(raw.get("max_account_risk_pct", 0.0025)))
            ),
            max_notional_usdt=max(5.0, float(raw.get("max_notional_usdt", 10.0))),
            max_open_positions=max(1, min(5, int(raw.get("max_open_positions", 1)))),
            max_daily_loss_r=min(-0.1, float(raw.get("max_daily_loss_r", -1.0))),
            max_candidate_age_sec=max(60, int(raw.get("max_candidate_age_sec", 20 * 60))),
            approval_ttl_sec=max(30, min(30 * 60, int(raw.get("approval_ttl_sec", 5 * 60)))),
            max_price_deviation_pct=max(
                0.0005, min(0.02, float(raw.get("max_price_deviation_pct", 0.003)))
            ),
            allow_live=bool(raw.get("allow_live", False)),
            state_path=str(raw.get("state_path") or data_root / "hybrid_ai_state.json"),
            live_gate_path=str(raw.get("live_gate_path") or data_root / "hybrid_ai_live_gate.json"),
        )

    @property
    def api_key(self) -> str:
        return str(os.getenv(self.api_key_env, "")).strip()


@dataclass(frozen=True)
class AITradeDecision:
    action: str
    confidence: float
    regime: str
    setup_quality: int
    risk_flags: tuple[str, ...]
    thesis: str
    invalidation: str

    @classmethod
    def from_mapping(cls, value: Any) -> "AITradeDecision":
        if not isinstance(value, dict):
            raise HybridAIError("AI decision is not an object")
        extra = set(value) - set(DECISION_JSON_SCHEMA["properties"])
        if extra:
            raise HybridAIError(f"AI decision contains unknown fields: {sorted(extra)}")
        action = str(value.get("action", "")).upper()
        regime = str(value.get("regime", "")).upper()
        if action not in VALID_ACTIONS:
            raise HybridAIError("AI action must be TRADE or SKIP")
        if regime not in VALID_REGIMES:
            raise HybridAIError("AI regime is invalid")
        confidence = value.get("confidence")
        quality = value.get("setup_quality")
        if not _is_number(confidence) or not 0 <= float(confidence) <= 1:
            raise HybridAIError("AI confidence is invalid")
        if not isinstance(quality, int) or isinstance(quality, bool) or not 0 <= quality <= 100:
            raise HybridAIError("AI setup quality is invalid")
        risk_flags = value.get("risk_flags")
        if not isinstance(risk_flags, list) or len(risk_flags) > 8:
            raise HybridAIError("AI risk flags are invalid")
        clean_flags = []
        for flag in risk_flags:
            if not isinstance(flag, str) or not flag.strip() or len(flag) > 80:
                raise HybridAIError("AI risk flag is invalid")
            clean_flags.append(flag.strip())
        thesis = str(value.get("thesis", "")).strip()
        invalidation = str(value.get("invalidation", "")).strip()
        if not thesis or len(thesis) > 240:
            raise HybridAIError("AI thesis is invalid")
        if not invalidation or len(invalidation) > 200:
            raise HybridAIError("AI invalidation is invalid")
        return cls(
            action=action,
            confidence=float(confidence),
            regime=regime,
            setup_quality=quality,
            risk_flags=tuple(clean_flags),
            thesis=thesis,
            invalidation=invalidation,
        )


class OpenAIResponsesClient:
    def __init__(
        self,
        config: HybridAIConfig,
        transport: Callable[[str, dict, dict, int], dict] | None = None,
    ) -> None:
        self.config = config
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
            raise HybridAIError(f"OpenAI HTTP {exc.code}: {body[:300]}") from exc
        except Exception as exc:
            raise HybridAIError(f"OpenAI request failed: {exc}") from exc

    @staticmethod
    def _extract_output_text(response: dict) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        for item in response.get("output", []) if isinstance(response.get("output"), list) else []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"].strip()
        raise HybridAIError("OpenAI response has no output text")

    def build_request(self, snapshot: dict) -> dict:
        return {
            "model": self.config.model,
            "store": False,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
            "reasoning": {"effort": self.config.reasoning_effort},
            "max_output_tokens": 1000,
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "hybrid_trade_decision",
                    "strict": True,
                    "schema": DECISION_JSON_SCHEMA,
                },
            },
        }

    def decide(self, snapshot: dict) -> tuple[AITradeDecision, dict]:
        api_key = self.config.api_key
        if not api_key:
            raise HybridAIError(f"{self.config.api_key_env} is not configured")
        payload = self.build_request(snapshot)
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        response = self.transport(
            "https://api.openai.com/v1/responses",
            payload,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            self.config.request_timeout_sec,
        )
        text = self._extract_output_text(response)
        try:
            raw_decision = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HybridAIError("OpenAI output is not valid JSON") from exc
        decision = AITradeDecision.from_mapping(raw_decision)
        metadata = {
            "response_id": response.get("id"),
            "model": response.get("model") or self.config.model,
            "request_hash": request_hash,
            "usage": response.get("usage") if isinstance(response.get("usage"), dict) else {},
        }
        return decision, metadata


@dataclass(frozen=True)
class RiskGateResult:
    allowed: bool
    reasons: tuple[str, ...]
    metrics: dict


class HybridRiskGateway:
    def __init__(self, config: HybridAIConfig) -> None:
        self.config = config

    def evaluate(self, candidate: dict, decision: AITradeDecision, runtime: dict) -> RiskGateResult:
        reasons: list[str] = []
        now_ms = int(runtime.get("now_ms", time.time() * 1000))
        signal_time = int(candidate.get("signal_time_ms", 0) or 0)
        pair = str(candidate.get("pair", "")).upper()
        side = str(candidate.get("side", "")).upper()
        entry = candidate.get("entry")
        stop = candidate.get("sl")
        tp2 = candidate.get("tp2", candidate.get("tp"))
        rr = candidate.get("actual_rr")
        notional = candidate.get("notional_usdt")
        risk_usdt = candidate.get("risk_usdt")
        equity = float(runtime.get("equity", 0) or 0)
        age_sec = max(0.0, (now_ms - signal_time) / 1000.0) if signal_time else float("inf")

        if decision.action != "TRADE":
            reasons.append("ai_skip")
        if decision.confidence < self.config.min_confidence:
            reasons.append("confidence_below_floor")
        if decision.setup_quality < self.config.min_setup_quality:
            reasons.append("quality_below_floor")
        if decision.risk_flags:
            reasons.append("ai_risk_flags")
        if decision.regime in ("TRANSITION", "UNUSABLE"):
            reasons.append("regime_not_tradeable")
        if side not in ("LONG", "SHORT") or not pair:
            reasons.append("candidate_identity_invalid")
        if not all(_is_number(value) and float(value) > 0 for value in (entry, stop, tp2)):
            reasons.append("price_geometry_invalid")
            stop_pct = float("inf")
        else:
            entry_f, stop_f, tp_f = float(entry), float(stop), float(tp2)
            stop_pct = abs(entry_f - stop_f) / entry_f
            geometry_ok = (
                side == "LONG" and stop_f < entry_f < tp_f
            ) or (
                side == "SHORT" and tp_f < entry_f < stop_f
            )
            if not geometry_ok:
                reasons.append("price_geometry_invalid")
        if not _is_number(rr) or float(rr) < self.config.min_rr:
            reasons.append("rr_below_floor")
        if stop_pct > self.config.max_stop_pct:
            reasons.append("stop_too_wide")
        if not _is_number(notional) or float(notional) <= 0:
            reasons.append("notional_invalid")
        elif float(notional) > self.config.max_notional_usdt + 1e-9:
            reasons.append("notional_above_cap")
        if not _is_number(risk_usdt) or float(risk_usdt) <= 0:
            reasons.append("risk_invalid")
            account_risk_pct = float("inf")
        elif equity <= 0:
            reasons.append("equity_unavailable")
            account_risk_pct = float("inf")
        else:
            account_risk_pct = float(risk_usdt) / equity
            if account_risk_pct > self.config.max_account_risk_pct:
                reasons.append("account_risk_above_cap")
        if age_sec > self.config.max_candidate_age_sec:
            reasons.append("candidate_stale")
        if bool(runtime.get("entry_paused", False)):
            reasons.append("entry_paused")
        open_positions = int(runtime.get("open_positions", 0) or 0)
        if open_positions >= self.config.max_open_positions:
            reasons.append("max_ai_positions")
        open_pairs = {str(value).upper() for value in runtime.get("open_pairs", [])}
        if pair in open_pairs:
            reasons.append("pair_already_open")
        daily_r = float(runtime.get("daily_r", 0) or 0)
        if daily_r <= self.config.max_daily_loss_r:
            reasons.append("daily_ai_loss_limit")

        return RiskGateResult(
            allowed=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            metrics={
                "age_sec": round(age_sec, 3),
                "stop_pct": stop_pct,
                "account_risk_pct": account_risk_pct,
                "notional_usdt": float(notional) if _is_number(notional) else None,
                "risk_usdt": float(risk_usdt) if _is_number(risk_usdt) else None,
                "equity": equity,
                "open_positions": open_positions,
                "daily_r": daily_r,
            },
        )


class HybridAIStateStore:
    def __init__(self, path: str | Path, initial_mode: str = "AI_SHADOW") -> None:
        self.path = Path(path)
        self.initial_mode = initial_mode if initial_mode in VALID_MODES else "AI_SHADOW"
        self.lock = threading.RLock()

    def _default(self) -> dict:
        return {
            "schema": ENGINE_SCHEMA,
            "mode": self.initial_mode,
            "updated_at_ms": 0,
            "proposals": [],
        }

    def _read_unlocked(self) -> dict:
        if not self.path.exists():
            return self._default()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise HybridAIStateError(f"hybrid state cannot be read: {exc}") from exc
        if not isinstance(value, dict) or value.get("schema") != ENGINE_SCHEMA:
            raise HybridAIStateError("hybrid state schema is invalid")
        if value.get("mode") not in VALID_MODES or not isinstance(value.get("proposals"), list):
            raise HybridAIStateError("hybrid state content is invalid")
        return value

    def load(self) -> dict:
        with self.lock:
            return self._read_unlocked()

    def _save_unlocked(self, state: dict) -> None:
        state["schema"] = ENGINE_SCHEMA
        state["updated_at_ms"] = int(time.time() * 1000)
        state["proposals"] = list(state.get("proposals", []))[-1000:]
        _atomic_json_write(self.path, state)

    def find(self, proposal_id: str) -> dict | None:
        with self.lock:
            state = self._read_unlocked()
            for proposal in state["proposals"]:
                if proposal.get("id") == proposal_id:
                    return dict(proposal)
        return None

    def add_if_absent(self, proposal: dict) -> tuple[dict, bool]:
        with self.lock:
            state = self._read_unlocked()
            for existing in state["proposals"]:
                if existing.get("id") == proposal.get("id"):
                    return dict(existing), False
            state["proposals"].append(proposal)
            self._save_unlocked(state)
            return dict(proposal), True

    def update(self, proposal_id: str, mutate: Callable[[dict], None]) -> dict:
        with self.lock:
            state = self._read_unlocked()
            for proposal in state["proposals"]:
                if proposal.get("id") == proposal_id:
                    mutate(proposal)
                    proposal["updated_at_ms"] = int(time.time() * 1000)
                    self._save_unlocked(state)
                    return dict(proposal)
        raise HybridAIStateError("proposal not found")

    def set_mode(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise HybridAIStateError("invalid hybrid mode")
        with self.lock:
            state = self._read_unlocked()
            state["mode"] = mode
            self._save_unlocked(state)

    def pending(self, now_ms: int | None = None) -> list[dict]:
        current = int(now_ms or time.time() * 1000)
        with self.lock:
            state = self._read_unlocked()
            return [
                dict(proposal)
                for proposal in state["proposals"]
                if proposal.get("status") == "PENDING_APPROVAL"
                and int(proposal.get("expires_at_ms", 0) or 0) > current
            ]


@dataclass(frozen=True)
class ReviewOutcome:
    proposal_id: str | None
    mode: str
    route: str
    status: str
    created: bool
    reason: str
    proposal: dict | None = None


class HybridAIEngine:
    def __init__(
        self,
        config: HybridAIConfig,
        client: OpenAIResponsesClient | None = None,
        now_ms_fn: Callable[[], int] | None = None,
    ) -> None:
        self.config = config
        self.client = client or OpenAIResponsesClient(config)
        self.store = HybridAIStateStore(config.state_path, config.initial_mode)
        self.risk_gateway = HybridRiskGateway(config)
        self.now_ms_fn = now_ms_fn or (lambda: int(time.time() * 1000))
        self.call_slots = threading.BoundedSemaphore(config.max_parallel_calls)

    def current_mode(self) -> str:
        return str(self.store.load().get("mode", self.config.initial_mode))

    def live_gate(self) -> dict:
        path = Path(self.config.live_gate_path)
        if not path.exists():
            return {"passed": False, "reason": "gate_file_missing"}
        try:
            gate = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return {"passed": False, "reason": f"gate_file_invalid:{exc}"}
        checks = [
            gate.get("schema") == LIVE_GATE_SCHEMA,
            gate.get("status") == "PASSED",
            gate.get("prompt_version") == PROMPT_VERSION,
            gate.get("model") == self.config.model,
            bool(gate.get("development", {}).get("passed")),
            bool(gate.get("validation", {}).get("passed")),
        ]
        return {
            "passed": all(checks),
            "reason": "passed" if all(checks) else "gate_checks_failed",
            "artifact": gate,
        }

    def set_mode(self, mode: str) -> str:
        normalized = str(mode).upper()
        if normalized not in VALID_MODES:
            raise HybridAIError("mode must be AI_SHADOW, AI_APPROVAL, or AI_LIVE")
        if not self.config.enabled:
            raise HybridAIError("Hybrid AI is disabled in config")
        # Returning to the non-intervening safe mode must never depend on an
        # external credential being available.
        if normalized != "AI_SHADOW" and not self.config.api_key:
            raise HybridAIError(f"{self.config.api_key_env} is not configured")
        if normalized == "AI_LIVE":
            if not self.config.allow_live:
                raise HybridAIError("AI_LIVE is locked by allow_live=false")
            gate = self.live_gate()
            if not gate["passed"]:
                raise HybridAIError(f"AI_LIVE gate is locked: {gate['reason']}")
        self.store.set_mode(normalized)
        return normalized

    @staticmethod
    def _existing_outcome(proposal: dict, mode: str) -> ReviewOutcome:
        status = str(proposal.get("status", "UNKNOWN"))
        if status in ("PENDING_APPROVAL", "APPROVED"):
            route = "DEFER"
        elif status == "READY_LIVE":
            route = "EXECUTE"
        elif status.startswith("SHADOW_"):
            route = "RECORD_ONLY"
        else:
            route = "BLOCK"
        return ReviewOutcome(
            proposal_id=proposal.get("id"),
            mode=mode,
            route=route,
            status=status,
            created=False,
            reason="duplicate_candidate",
            proposal=proposal,
        )

    def review(self, candidate: dict, runtime: dict, execution: dict | None = None) -> ReviewOutcome:
        if not self.config.enabled:
            return ReviewOutcome(None, "DISABLED", "PASSTHROUGH", "DISABLED", False, "disabled")
        mode = self.current_mode()
        identifier = candidate_id(candidate)
        existing = self.store.find(identifier)
        if existing:
            return self._existing_outcome(existing, mode)

        snapshot = {
            "schema": "KT_HYBRID_CANDIDATE_V1",
            "prompt_version": PROMPT_VERSION,
            "candidate_id": identifier,
            "candidate": candidate,
        }
        try:
            with self.call_slots:
                decision, metadata = self.client.decide(snapshot)
            error = None
        except Exception as exc:
            decision = None
            metadata = {"model": self.config.model}
            error = str(exc)[:300]

        created_at = self.now_ms_fn()
        if decision is None:
            proposal = {
                "id": identifier,
                "created_at_ms": created_at,
                "updated_at_ms": created_at,
                "expires_at_ms": 0,
                "mode": mode,
                "status": "AI_ERROR",
                "candidate": candidate,
                "execution": execution,
                "decision": None,
                "risk_gate": {"allowed": False, "reasons": ["ai_error"], "metrics": {}},
                "openai": metadata,
                "error": error,
            }
            stored, created = self.store.add_if_absent(proposal)
            route = "RECORD_ONLY" if mode == "AI_SHADOW" else "BLOCK"
            return ReviewOutcome(identifier, mode, route, stored["status"], created, "ai_error", stored)

        gate = self.risk_gateway.evaluate(candidate, decision, runtime)
        if mode == "AI_SHADOW":
            status = "SHADOW_ACCEPTED" if gate.allowed else "SHADOW_SKIPPED"
            route = "RECORD_ONLY"
            expires_at = 0
        elif mode == "AI_APPROVAL":
            status = "PENDING_APPROVAL" if gate.allowed else "RISK_BLOCKED"
            route = "DEFER" if gate.allowed else "BLOCK"
            expires_at = created_at + self.config.approval_ttl_sec * 1000 if gate.allowed else 0
        else:
            live_gate = self.live_gate()
            live_allowed = self.config.allow_live and live_gate["passed"]
            if gate.allowed and live_allowed:
                status = "READY_LIVE"
                route = "EXECUTE"
            else:
                status = "LIVE_GATE_BLOCKED" if gate.allowed else "RISK_BLOCKED"
                route = "BLOCK"
            expires_at = created_at + self.config.approval_ttl_sec * 1000 if route == "EXECUTE" else 0

        proposal = {
            "id": identifier,
            "created_at_ms": created_at,
            "updated_at_ms": created_at,
            "expires_at_ms": expires_at,
            "mode": mode,
            "status": status,
            "candidate": candidate,
            "execution": execution,
            "decision": asdict(decision),
            "risk_gate": {
                "allowed": gate.allowed,
                "reasons": list(gate.reasons),
                "metrics": gate.metrics,
            },
            "openai": metadata,
            "error": None,
        }
        stored, created = self.store.add_if_absent(proposal)
        return ReviewOutcome(
            identifier,
            mode,
            route,
            stored["status"],
            created,
            "allowed" if gate.allowed else ",".join(gate.reasons),
            stored,
        )

    def approve(self, proposal_id: str, approved_by: str) -> dict:
        current = self.now_ms_fn()
        expired = [False]

        def mutate(proposal: dict) -> None:
            if proposal.get("status") != "PENDING_APPROVAL":
                raise HybridAIStateError("proposal is not pending approval")
            if int(proposal.get("expires_at_ms", 0) or 0) <= current:
                proposal["status"] = "EXPIRED"
                expired[0] = True
                return
            else:
                proposal["status"] = "APPROVED"
                proposal["approved_by"] = str(approved_by)
                proposal["approved_at_ms"] = current

        updated = self.store.update(proposal_id, mutate)
        if expired[0]:
            raise HybridAIStateError("proposal has expired")
        return updated

    def reject(self, proposal_id: str, rejected_by: str) -> dict:
        def mutate(proposal: dict) -> None:
            if proposal.get("status") not in ("PENDING_APPROVAL", "APPROVED"):
                raise HybridAIStateError("proposal cannot be rejected")
            proposal["status"] = "REJECTED"
            proposal["rejected_by"] = str(rejected_by)

        return self.store.update(proposal_id, mutate)

    def claim_for_execution(self, proposal_id: str) -> dict:
        current = self.now_ms_fn()
        expired = [False]

        def mutate(proposal: dict) -> None:
            if proposal.get("status") not in ("APPROVED", "READY_LIVE"):
                raise HybridAIStateError("proposal is not executable")
            if int(proposal.get("expires_at_ms", 0) or 0) <= current:
                proposal["status"] = "EXPIRED"
                expired[0] = True
                return
            else:
                proposal["status"] = "EXECUTING"
                proposal["execution_started_at_ms"] = current

        updated = self.store.update(proposal_id, mutate)
        if expired[0]:
            raise HybridAIStateError("proposal has expired")
        return updated

    def finish_execution(self, proposal_id: str, success: bool, detail: dict | str) -> dict:
        def mutate(proposal: dict) -> None:
            if proposal.get("status") != "EXECUTING":
                raise HybridAIStateError("proposal is not executing")
            proposal["status"] = "EXECUTED" if success else "EXECUTION_FAILED"
            proposal["execution_result"] = detail

        return self.store.update(proposal_id, mutate)

    def summary(self) -> dict:
        state = self.store.load()
        statuses: dict[str, int] = {}
        for proposal in state["proposals"]:
            status = str(proposal.get("status", "UNKNOWN"))
            statuses[status] = statuses.get(status, 0) + 1
        return {
            "enabled": self.config.enabled,
            "mode": state["mode"],
            "model": self.config.model,
            "prompt_version": PROMPT_VERSION,
            "api_key_present": bool(self.config.api_key),
            "allow_live": self.config.allow_live,
            "live_gate": self.live_gate(),
            "statuses": statuses,
            "pending": len(self.store.pending(self.now_ms_fn())),
            "total": len(state["proposals"]),
        }
