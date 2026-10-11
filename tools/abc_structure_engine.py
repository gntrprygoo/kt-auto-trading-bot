import math
import statistics
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone


MS_15M = 15 * 60 * 1000
MS_HOUR = 60 * 60 * 1000


@dataclass(frozen=True)
class ABCParameters:
    name: str = "ABC_PRIMARY"
    structure_lookback: int = 60
    pivot_left: int = 2
    pivot_right: int = 2
    cluster_atr: float = 0.35
    zone_atr: float = 0.18
    min_touches: int = 2
    min_range_atr: float = 3.0
    max_range_atr: float = 18.0
    breakout_buffer_atr: float = 0.12
    breakout_volume_min: float = 1.10
    breakout_body_min: float = 0.50
    breakout_close_min: float = 0.68
    breakout_max_distance_atr: float = 1.50
    acceptance_window_bars: int = 4
    acceptance_min_outside: int = 3
    breakout_pending_bars: int = 8
    retest_expiry_bars: int = 64
    retest_tolerance_atr: float = 0.30
    retest_volume_min: float = 0.85
    reaction_volume_min: float = 0.90
    reaction_close_min: float = 0.58
    reaction_wick_min: float = 0.50
    a_efficiency_max: float = 0.40
    a_max_boundary_age: int = 40
    a_max_range_atr: float = 10.0
    sweep_buffer_atr: float = 0.08
    sweep_max_atr: float = 0.90
    sweep_volume_min: float = 1.05
    failure_inside_atr: float = 0.05
    stop_buffer_atr: float = 0.15
    min_risk_pct: float = 0.004
    max_risk_pct: float = 0.030
    min_planned_rr: float = 1.15
    signal_cooldown_bars: int = 16


PRIMARY = ABCParameters()
TIGHT = replace(
    PRIMARY,
    name="ABC_TIGHT",
    cluster_atr=0.30,
    breakout_volume_min=1.20,
    breakout_body_min=0.55,
    breakout_close_min=0.72,
    retest_volume_min=0.95,
    reaction_volume_min=1.00,
    reaction_close_min=0.62,
    reaction_wick_min=0.60,
    a_efficiency_max=0.32,
    a_max_boundary_age=32,
    a_max_range_atr=8.0,
    sweep_volume_min=1.15,
    min_planned_rr=1.30,
)
WIDE = replace(
    PRIMARY,
    name="ABC_WIDE",
    cluster_atr=0.40,
    breakout_volume_min=1.05,
    breakout_body_min=0.45,
    breakout_close_min=0.64,
    retest_volume_min=0.80,
    reaction_volume_min=0.85,
    reaction_close_min=0.55,
    reaction_wick_min=0.40,
    a_efficiency_max=0.48,
    a_max_boundary_age=48,
    a_max_range_atr=12.0,
    sweep_volume_min=1.00,
    min_planned_rr=1.05,
)
VARIANTS = (PRIMARY, TIGHT, WIDE)


@dataclass(frozen=True)
class StructureLevel:
    price: float
    touches: int
    last_index: int
    source_times: tuple


@dataclass(frozen=True)
class StructureRange:
    structure_id: str
    support: float
    resistance: float
    zone_width: float
    atr_4h: float
    support_touches: int
    resistance_touches: int
    support_age_bars: int
    resistance_age_bars: int
    efficiency_20: float
    range_width_atr: float
    built_at: int
    levels: tuple = ()

    @property
    def width(self):
        return self.resistance - self.support


@dataclass
class BreakoutState:
    side: str
    level: float
    started_index: int
    started_time: int
    atr: float
    volume_ratio: float
    outside_flags: list = field(default_factory=list)
    extreme: float = 0.0
    accepted_index: int = None
    accepted_time: int = None


@dataclass(frozen=True)
class ABCEvent:
    path: str
    side: str
    transition: str
    signal_time: int
    level: float
    support: float
    resistance: float
    extreme: float
    atr_15m: float
    volume_ratio: float
    body_ratio: float
    close_position: float
    wick_ratio: float
    planned_target: float
    planned_rr: float
    structure_id: str
    structure_touches: int
    structure_efficiency_20: float
    structure_range_width_atr: float
    structure_boundary_age: int
    breakout_age_bars: int = 0
    calendar_phase: str = ""
    calendar_score: float = 0.0

    def to_dict(self):
        return asdict(self)


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def true_range(previous, current):
    return max(
        float(current["high"]) - float(current["low"]),
        abs(float(current["high"]) - float(previous["close"])),
        abs(float(current["low"]) - float(previous["close"])),
    )


def atr_value(candles, period=14):
    if len(candles) < period + 1:
        return None
    values = [
        true_range(previous, current)
        for previous, current in zip(
            candles[-(period + 1):-1],
            candles[-period:],
        )
    ]
    result = sum(values) / len(values) if values else None
    return result if result and _finite(result) and result > 0 else None


def median_volume(candles, lookback=32):
    sample = [
        float(item.get("volume", 0.0))
        for item in candles[-lookback:]
        if _finite(item.get("volume", 0.0))
        and float(item.get("volume", 0.0)) > 0
    ]
    return statistics.median(sample) if sample else None


def candle_metrics(candle, side):
    high = float(candle["high"])
    low = float(candle["low"])
    open_price = float(candle["open"])
    close = float(candle["close"])
    candle_range = high - low
    if candle_range <= 0:
        return {
            "body_ratio": 0.0,
            "close_position": 0.5,
            "wick_ratio": 0.0,
            "direction_ok": False,
        }
    if side == "LONG":
        close_position = (close - low) / candle_range
        wick = min(open_price, close) - low
        direction_ok = close > open_price
    else:
        close_position = (high - close) / candle_range
        wick = high - max(open_price, close)
        direction_ok = close < open_price
    return {
        "body_ratio": abs(close - open_price) / candle_range,
        "close_position": max(0.0, min(1.0, close_position)),
        "wick_ratio": max(0.0, wick / candle_range),
        "direction_ok": direction_ok,
    }


def _confirmed_pivots(candles, left, right):
    highs = []
    lows = []
    for index in range(left, len(candles) - right):
        candle = candles[index]
        high = float(candle["high"])
        low = float(candle["low"])
        left_highs = [
            float(item["high"])
            for item in candles[index - left:index]
        ]
        right_highs = [
            float(item["high"])
            for item in candles[index + 1:index + right + 1]
        ]
        left_lows = [
            float(item["low"])
            for item in candles[index - left:index]
        ]
        right_lows = [
            float(item["low"])
            for item in candles[index + 1:index + right + 1]
        ]
        source_time = int(candle["close_time"])
        if (
            high >= max(left_highs)
            and high >= max(right_highs)
            and (
                high > min(left_highs)
                or high > min(right_highs)
            )
        ):
            highs.append((high, index, source_time))
        if (
            low <= min(left_lows)
            and low <= min(right_lows)
            and (
                low < max(left_lows)
                or low < max(right_lows)
            )
        ):
            lows.append((low, index, source_time))
    return highs, lows


def _cluster_levels(points, tolerance):
    if not points or tolerance <= 0:
        return []
    clusters = []
    for price, index, source_time in sorted(points):
        if (
            not clusters
            or abs(price - statistics.median(clusters[-1]["prices"]))
            > tolerance
        ):
            clusters.append({
                "prices": [price],
                "indices": [index],
                "times": [source_time],
            })
        else:
            clusters[-1]["prices"].append(price)
            clusters[-1]["indices"].append(index)
            clusters[-1]["times"].append(source_time)
    return [
        StructureLevel(
            price=float(statistics.median(cluster["prices"])),
            touches=len(set(cluster["times"])),
            last_index=max(cluster["indices"]),
            source_times=tuple(sorted(set(cluster["times"]))),
        )
        for cluster in clusters
    ]


def efficiency_ratio(candles, lookback=20):
    if len(candles) < lookback + 1:
        return None
    closes = [
        float(item["close"])
        for item in candles[-(lookback + 1):]
    ]
    path = sum(
        abs(current - previous)
        for previous, current in zip(closes[:-1], closes[1:])
    )
    if path <= 0:
        return 0.0
    return abs(closes[-1] - closes[0]) / path


def build_structure(candles_4h, params=PRIMARY):
    minimum = max(
        params.structure_lookback,
        params.pivot_left + params.pivot_right + 10,
    )
    if len(candles_4h) < minimum:
        return None
    sample = candles_4h[-params.structure_lookback:]
    atr_4h = atr_value(sample)
    if not atr_4h:
        return None
    current = float(sample[-1]["close"])
    highs, lows = _confirmed_pivots(
        sample,
        params.pivot_left,
        params.pivot_right,
    )
    tolerance = params.cluster_atr * atr_4h
    levels = _cluster_levels(highs + lows, tolerance)
    levels = [
        level
        for level in levels
        if level.touches >= params.min_touches
    ]
    supports = [level for level in levels if level.price < current]
    resistances = [level for level in levels if level.price > current]
    candidates = []
    for support in supports:
        for resistance in resistances:
            width_atr = (resistance.price - support.price) / atr_4h
            if not params.min_range_atr <= width_atr <= params.max_range_atr:
                continue
            distance = (
                abs(current - support.price)
                + abs(resistance.price - current)
            ) / atr_4h
            touch_bonus = 0.20 * (
                support.touches + resistance.touches
            )
            recency_bonus = 0.01 * (
                support.last_index + resistance.last_index
            )
            score = distance - touch_bonus - recency_bonus
            candidates.append((score, support, resistance))
    if not candidates:
        return None
    _, support, resistance = min(candidates, key=lambda item: item[0])
    built_at = int(sample[-1]["close_time"])
    efficiency = efficiency_ratio(sample, 20)
    if efficiency is None:
        return None
    support_age = len(sample) - 1 - support.last_index
    resistance_age = len(sample) - 1 - resistance.last_index
    range_width_atr = (
        resistance.price - support.price
    ) / atr_4h
    structure_id = (
        f"{built_at}:"
        f"{support.price:.10g}:{resistance.price:.10g}"
    )
    return StructureRange(
        structure_id=structure_id,
        support=support.price,
        resistance=resistance.price,
        zone_width=params.zone_atr * atr_4h,
        atr_4h=atr_4h,
        support_touches=support.touches,
        resistance_touches=resistance.touches,
        support_age_bars=support_age,
        resistance_age_bars=resistance_age,
        efficiency_20=efficiency,
        range_width_atr=range_width_atr,
        built_at=built_at,
        levels=tuple(sorted(levels, key=lambda item: item.price)),
    )


def calendar_phase(timestamp_ms, utc_offset_hours=7):
    local_tz = timezone(timedelta(hours=utc_offset_hours))
    local = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
    day = local.astimezone(local_tz).day
    if day <= 8:
        return "D01_08"
    if day <= 15:
        return "D09_15"
    if day <= 25:
        return "D16_25"
    return "D26_EOM"


def calendar_context_score(
    side,
    path,
    timestamp_ms,
    month_to_date_return=0.0,
    utc_offset_hours=7,
):
    phase = calendar_phase(timestamp_ms, utc_offset_hours)
    if phase == "D01_08":
        return phase, 1.0 if side == "SHORT" else -1.0
    if phase == "D09_15":
        return phase, 1.0 if side == "LONG" else -1.0
    if phase == "D16_25":
        if path != "B" or abs(month_to_date_return) < 0.02:
            return phase, 0.0
        trend_side = "LONG" if month_to_date_return > 0 else "SHORT"
        return phase, 1.0 if side == trend_side else -1.0
    if abs(month_to_date_return) < 0.02:
        return phase, 0.5 if side == "SHORT" else -0.5
    correction_side = "SHORT" if month_to_date_return > 0 else "LONG"
    return phase, 1.0 if side == correction_side else -1.0


def calendar_risk_weight(score):
    if score >= 0.75:
        return 1.10
    if score <= -0.75:
        return 0.85
    if score > 0:
        return 1.05
    if score < 0:
        return 0.925
    return 1.0


class ABCStateMachine:
    def __init__(self, params=PRIMARY):
        self.params = params
        self.structure = None
        self.mode = "RANGE"
        self.breakout = None
        self.cooldown_until = -1

    def snapshot(self):
        return {
            "mode": self.mode,
            "structure_id": (
                self.structure.structure_id
                if self.structure
                else None
            ),
            "breakout": (
                asdict(self.breakout)
                if self.breakout
                else None
            ),
            "cooldown_until": self.cooldown_until,
        }

    def _adopt_structure(self, structure):
        if structure is None:
            return
        if self.structure is None or self.mode == "RANGE":
            self.structure = structure

    def _outside(self, candle, side, level, atr):
        close = float(candle["close"])
        buffer_value = self.params.breakout_buffer_atr * atr
        return (
            close > level + buffer_value
            if side == "LONG"
            else close < level - buffer_value
        )

    def _inside_old_range(self, candle, side, level, atr):
        close = float(candle["close"])
        inside = self.params.failure_inside_atr * atr
        return (
            close < level - inside
            if side == "LONG"
            else close > level + inside
        )

    def _event(
        self,
        path,
        side,
        transition,
        candle,
        level,
        extreme,
        atr,
        volume_ratio,
        metrics,
        bar_index,
        month_to_date_return,
        breakout_age=0,
    ):
        structure = self.structure
        if not structure:
            return None
        target = (
            structure.resistance
            if side == "LONG"
            else structure.support
        )
        if path == "B":
            external = [
                item.price
                for item in structure.levels
                if (
                    item.price > structure.resistance
                    if side == "LONG"
                    else item.price < structure.support
                )
            ]
            if external:
                target = (
                    min(external)
                    if side == "LONG"
                    else max(external)
                )
            else:
                target = 0.0
        close = float(candle["close"])
        stop = (
            min(
                extreme - 0.10 * atr,
                level - self.params.stop_buffer_atr * atr,
            )
            if side == "LONG"
            else max(
                extreme + 0.10 * atr,
                level + self.params.stop_buffer_atr * atr,
            )
        )
        risk = close - stop if side == "LONG" else stop - close
        if risk <= 0:
            return None
        if target:
            reward = (
                target - close
                if side == "LONG"
                else close - target
            )
            planned_rr = reward / risk
        else:
            planned_rr = 2.0
        if planned_rr < self.params.min_planned_rr:
            return None
        phase, calendar_score = calendar_context_score(
            side,
            path,
            int(candle["close_time"]),
            month_to_date_return,
        )
        touches = (
            structure.support_touches
            if side == "LONG"
            else structure.resistance_touches
        )
        self.cooldown_until = (
            bar_index + self.params.signal_cooldown_bars
        )
        return ABCEvent(
            path=path,
            side=side,
            transition=transition,
            signal_time=int(candle["close_time"]),
            level=float(level),
            support=structure.support,
            resistance=structure.resistance,
            extreme=float(extreme),
            atr_15m=float(atr),
            volume_ratio=float(volume_ratio),
            body_ratio=float(metrics["body_ratio"]),
            close_position=float(metrics["close_position"]),
            wick_ratio=float(metrics["wick_ratio"]),
            planned_target=float(target),
            planned_rr=float(planned_rr),
            structure_id=structure.structure_id,
            structure_touches=int(touches),
            structure_efficiency_20=float(
                structure.efficiency_20
            ),
            structure_range_width_atr=float(
                structure.range_width_atr
            ),
            structure_boundary_age=int(
                max(
                    structure.support_age_bars,
                    structure.resistance_age_bars,
                )
            ),
            breakout_age_bars=int(breakout_age),
            calendar_phase=phase,
            calendar_score=float(calendar_score),
        )

    def _reaction_valid(self, metrics, volume_ratio):
        return (
            volume_ratio >= self.params.reaction_volume_min
            and metrics["close_position"]
            >= self.params.reaction_close_min
            and metrics["wick_ratio"]
            >= self.params.reaction_wick_min
        )

    def _a_range_valid(self):
        structure = self.structure
        return (
            structure is not None
            and structure.efficiency_20
            <= self.params.a_efficiency_max
            and structure.range_width_atr
            <= self.params.a_max_range_atr
            and structure.support_age_bars
            <= self.params.a_max_boundary_age
            and structure.resistance_age_bars
            <= self.params.a_max_boundary_age
        )

    def _sweep_valid(self, metrics, volume_ratio):
        return (
            volume_ratio >= self.params.sweep_volume_min
            and metrics["close_position"]
            >= self.params.reaction_close_min
            and (
                metrics["direction_ok"]
                or metrics["wick_ratio"]
                >= self.params.reaction_wick_min
            )
        )

    def _breakout_candidate(self, candle, side, level, atr, volume_ratio):
        if not self._outside(candle, side, level, atr):
            return False, None
        metrics = candle_metrics(candle, side)
        close = float(candle["close"])
        distance = (
            close - level
            if side == "LONG"
            else level - close
        ) / atr
        valid = (
            volume_ratio >= self.params.breakout_volume_min
            and metrics["direction_ok"]
            and metrics["body_ratio"]
            >= self.params.breakout_body_min
            and metrics["close_position"]
            >= self.params.breakout_close_min
            and distance <= self.params.breakout_max_distance_atr
        )
        return valid, metrics

    def _start_breakout(
        self,
        candle,
        side,
        level,
        atr,
        volume_ratio,
        bar_index,
    ):
        extreme = (
            float(candle["high"])
            if side == "LONG"
            else float(candle["low"])
        )
        self.breakout = BreakoutState(
            side=side,
            level=float(level),
            started_index=bar_index,
            started_time=int(candle["close_time"]),
            atr=float(atr),
            volume_ratio=float(volume_ratio),
            outside_flags=[True],
            extreme=extreme,
        )
        self.mode = "BREAKOUT_PENDING"

    def _reset_range(self, dynamic_structure=None):
        self.mode = "RANGE"
        self.breakout = None
        if dynamic_structure is not None:
            self.structure = dynamic_structure

    def _range_event(
        self,
        candle,
        atr,
        volume_ratio,
        bar_index,
        month_to_date_return,
    ):
        structure = self.structure
        low = float(candle["low"])
        high = float(candle["high"])
        close = float(candle["close"])
        support = structure.support
        resistance = structure.resistance
        sweep_min = self.params.sweep_buffer_atr * atr
        sweep_max = self.params.sweep_max_atr * atr
        reclaim = self.params.failure_inside_atr * atr

        long_metrics = candle_metrics(candle, "LONG")
        short_metrics = candle_metrics(candle, "SHORT")
        support_sweep = (
            support - sweep_max <= low < support - sweep_min
            and close > support + reclaim
        )
        resistance_sweep = (
            resistance + sweep_min < high <= resistance + sweep_max
            and close < resistance - reclaim
        )
        if support_sweep and not resistance_sweep and self._sweep_valid(
            long_metrics,
            volume_ratio,
        ):
            return self._event(
                "C",
                "LONG",
                "RANGE_SUPPORT_SWEEP_RECLAIM",
                candle,
                support,
                low,
                atr,
                volume_ratio,
                long_metrics,
                bar_index,
                month_to_date_return,
            )
        if resistance_sweep and not support_sweep and self._sweep_valid(
            short_metrics,
            volume_ratio,
        ):
            return self._event(
                "C",
                "SHORT",
                "RANGE_RESISTANCE_SWEEP_RECLAIM",
                candle,
                resistance,
                high,
                atr,
                volume_ratio,
                short_metrics,
                bar_index,
                month_to_date_return,
            )

        support_touch = (
            support - sweep_min <= low
            <= support + structure.zone_width
            and close > support + reclaim
        )
        resistance_touch = (
            resistance - structure.zone_width
            <= high <= resistance + sweep_min
            and close < resistance - reclaim
        )
        a_range_valid = self._a_range_valid()
        if (
            a_range_valid
            and support_touch
            and not resistance_touch
            and self._reaction_valid(
            long_metrics,
            volume_ratio,
            )
        ):
            return self._event(
                "A",
                "LONG",
                "SUPPORT_REACTION",
                candle,
                support,
                low,
                atr,
                volume_ratio,
                long_metrics,
                bar_index,
                month_to_date_return,
            )
        if (
            a_range_valid
            and resistance_touch
            and not support_touch
            and self._reaction_valid(
            short_metrics,
            volume_ratio,
            )
        ):
            return self._event(
                "A",
                "SHORT",
                "RESISTANCE_REACTION",
                candle,
                resistance,
                high,
                atr,
                volume_ratio,
                short_metrics,
                bar_index,
                month_to_date_return,
            )
        return None

    def _pending_update(
        self,
        candle,
        atr,
        volume_ratio,
        bar_index,
        dynamic_structure,
        month_to_date_return,
    ):
        pending = self.breakout
        side = pending.side
        level = pending.level
        outside = self._outside(candle, side, level, atr)
        pending.outside_flags.append(outside)
        pending.outside_flags = pending.outside_flags[
            -self.params.acceptance_window_bars:
        ]
        pending.extreme = (
            max(pending.extreme, float(candle["high"]))
            if side == "LONG"
            else min(pending.extreme, float(candle["low"]))
        )
        age = bar_index - pending.started_index
        if self._inside_old_range(candle, side, level, atr):
            reverse_side = "SHORT" if side == "LONG" else "LONG"
            metrics = candle_metrics(candle, reverse_side)
            event = None
            if self._sweep_valid(metrics, volume_ratio):
                event = self._event(
                    "C",
                    reverse_side,
                    "FAILED_BREAKOUT_RECLAIM",
                    candle,
                    level,
                    pending.extreme,
                    atr,
                    volume_ratio,
                    metrics,
                    bar_index,
                    month_to_date_return,
                    breakout_age=age,
                )
            self._reset_range(dynamic_structure)
            return event
        accepted = (
            len(pending.outside_flags)
            >= self.params.acceptance_window_bars
            and sum(pending.outside_flags)
            >= self.params.acceptance_min_outside
            and pending.outside_flags[-1]
        )
        if accepted:
            pending.accepted_index = bar_index
            pending.accepted_time = int(candle["close_time"])
            self.mode = "BREAKOUT_ACCEPTED"
            return None
        if age >= self.params.breakout_pending_bars:
            self._reset_range(dynamic_structure)
        return None

    def _accepted_update(
        self,
        candle,
        atr,
        volume_ratio,
        bar_index,
        dynamic_structure,
        month_to_date_return,
    ):
        pending = self.breakout
        side = pending.side
        level = pending.level
        age = bar_index - pending.started_index
        if self._inside_old_range(candle, side, level, atr):
            reverse_side = "SHORT" if side == "LONG" else "LONG"
            metrics = candle_metrics(candle, reverse_side)
            event = None
            if self._sweep_valid(metrics, volume_ratio):
                event = self._event(
                    "C",
                    reverse_side,
                    "ACCEPTED_BREAKOUT_FAILURE",
                    candle,
                    level,
                    pending.extreme,
                    atr,
                    volume_ratio,
                    metrics,
                    bar_index,
                    month_to_date_return,
                    breakout_age=age,
                )
            self._reset_range(dynamic_structure)
            return event

        tolerance = self.params.retest_tolerance_atr * atr
        close = float(candle["close"])
        low = float(candle["low"])
        high = float(candle["high"])
        if side == "LONG":
            touched = low <= level + tolerance and high >= level
            reclaimed = close > level + self.params.failure_inside_atr * atr
            extreme = low
        else:
            touched = high >= level - tolerance and low <= level
            reclaimed = close < level - self.params.failure_inside_atr * atr
            extreme = high
        metrics = candle_metrics(candle, side)
        valid_retest = (
            touched
            and reclaimed
            and volume_ratio >= self.params.retest_volume_min
            and metrics["close_position"]
            >= self.params.reaction_close_min
            and (
                metrics["direction_ok"]
                or metrics["wick_ratio"]
                >= self.params.reaction_wick_min
            )
        )
        if valid_retest:
            event = self._event(
                "B",
                side,
                "ACCEPTED_BREAKOUT_RETEST",
                candle,
                level,
                extreme,
                atr,
                volume_ratio,
                metrics,
                bar_index,
                month_to_date_return,
                breakout_age=age,
            )
            self._reset_range(dynamic_structure)
            return event
        if (
            pending.accepted_index is not None
            and bar_index - pending.accepted_index
            >= self.params.retest_expiry_bars
        ):
            self._reset_range(dynamic_structure)
        return None

    def update(
        self,
        candle,
        bar_index,
        dynamic_structure,
        atr_15m,
        volume_baseline,
        month_to_date_return=0.0,
    ):
        if (
            dynamic_structure is None
            or not atr_15m
            or atr_15m <= 0
            or not volume_baseline
            or volume_baseline <= 0
        ):
            return None
        self._adopt_structure(dynamic_structure)
        if self.structure is None:
            return None
        volume_ratio = (
            float(candle.get("volume", 0.0))
            / float(volume_baseline)
        )
        if not _finite(volume_ratio):
            return None

        if self.mode == "BREAKOUT_PENDING":
            return self._pending_update(
                candle,
                atr_15m,
                volume_ratio,
                bar_index,
                dynamic_structure,
                month_to_date_return,
            )
        if self.mode == "BREAKOUT_ACCEPTED":
            return self._accepted_update(
                candle,
                atr_15m,
                volume_ratio,
                bar_index,
                dynamic_structure,
                month_to_date_return,
            )

        structure = self.structure
        for side, level in (
            ("LONG", structure.resistance),
            ("SHORT", structure.support),
        ):
            valid, _ = self._breakout_candidate(
                candle,
                side,
                level,
                atr_15m,
                volume_ratio,
            )
            if valid:
                self._start_breakout(
                    candle,
                    side,
                    level,
                    atr_15m,
                    volume_ratio,
                    bar_index,
                )
                return None
        if bar_index < self.cooldown_until:
            return None
        return self._range_event(
            candle,
            atr_15m,
            volume_ratio,
            bar_index,
            month_to_date_return,
        )
