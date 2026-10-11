import hashlib
import math
import statistics
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone


MS_15M = 15 * 60 * 1000
MS_4H = 4 * 60 * 60 * 1000
MS_DAY = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class ABCV2Parameters:
    name: str = "ABC_V2_BTC_STRUCTURE"
    daily_lookback: int = 180
    four_hour_lookback: int = 180
    daily_pivot_left: int = 2
    daily_pivot_right: int = 2
    four_hour_pivot_left: int = 3
    four_hour_pivot_right: int = 3
    level_merge_atr: float = 0.30
    level_zone_atr: float = 0.22
    min_four_hour_touches: int = 3
    min_level_score: float = 4.25
    max_level_age_4h: int = 720
    min_range_atr: float = 3.0
    max_range_atr: float = 18.0
    balance_efficiency_max: float = 0.38
    balance_containment_min: float = 0.72
    balance_lookback_4h: int = 30
    structure_confirmation_updates: int = 2
    min_structure_monitor_bars: int = 16
    breakout_buffer_atr: float = 0.15
    breakout_volume_min: float = 1.15
    breakout_body_min: float = 0.58
    breakout_close_min: float = 0.72
    breakout_max_distance_atr: float = 1.35
    acceptance_window_bars: int = 4
    acceptance_min_outside: int = 3
    breakout_pending_bars: int = 8
    retest_expiry_bars: int = 48
    retest_tolerance_atr: float = 0.25
    retest_volume_min: float = 0.90
    reaction_volume_min: float = 0.95
    reaction_close_min: float = 0.62
    reaction_wick_min: float = 0.45
    a_requires_mss: bool = False
    a_min_range_width_atr: float = 3.0
    a_max_range_width_atr: float = 18.0
    sweep_buffer_atr: float = 0.10
    sweep_max_atr: float = 0.85
    sweep_reclaim_atr: float = 0.05
    sweep_confirmation_bars: int = 4
    sweep_mss_lookback: int = 4
    sweep_mss_buffer_atr: float = 0.04
    sweep_displacement_volume_min: float = 1.05
    sweep_displacement_body_min: float = 0.50
    sweep_displacement_close_min: float = 0.66
    b_hold_monitor_bars: int = 16
    allow_failed_b_c: bool = True
    c_supersedes_a_on_same_level_sweep: bool = False
    stop_buffer_atr: float = 0.15
    min_risk_pct: float = 0.004
    max_risk_pct: float = 0.030
    min_planned_rr: float = 1.15
    signal_cooldown_bars: int = 12


PRIMARY = ABCV2Parameters()
CONFIRMED_A = replace(
    PRIMARY,
    name="ABC_V21_CONFIRMED_A",
    a_requires_mss=True,
)
FASTER_B = replace(
    PRIMARY,
    name="ABC_V21_FASTER_B",
    acceptance_window_bars=3,
    acceptance_min_outside=2,
)
DIRECT_C = replace(
    PRIMARY,
    name="ABC_V21_DIRECT_C",
    allow_failed_b_c=False,
)
COMBINED = replace(
    PRIMARY,
    name="ABC_V21_COMBINED",
    a_requires_mss=True,
    acceptance_window_bars=3,
    acceptance_min_outside=2,
    allow_failed_b_c=False,
)
BALANCED_A = replace(
    COMBINED,
    name="ABC_V23_BALANCED_A",
    a_min_range_width_atr=6.0,
    a_max_range_width_atr=10.0,
)
HUMAN_V24 = replace(
    COMBINED,
    name="ABC_V24_HUMAN_EXCLUSIVE",
    allow_failed_b_c=True,
    c_supersedes_a_on_same_level_sweep=True,
)
V21_VARIANTS = (
    PRIMARY,
    CONFIRMED_A,
    FASTER_B,
    DIRECT_C,
    COMBINED,
)
V24_VARIANTS = (HUMAN_V24,)


@dataclass(frozen=True)
class PivotPoint:
    price: float
    kind: str
    source_tf: str
    source_time: int
    confirmed_time: int
    volume_ratio: float


@dataclass(frozen=True)
class StructureLevel:
    level_id: str
    price: float
    source_tf: str
    pivot_kinds: tuple
    source_times: tuple
    confirmed_time: int
    last_source_time: int
    touches: int
    age_bars_4h: int
    test_count: int
    freshness: str
    volume_at_level_ratio: float
    score: float
    zone_width: float

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class StructureMap:
    range_id: str
    support: StructureLevel
    resistance: StructureLevel
    levels: tuple
    atr_4h: float
    efficiency_4h: float
    containment_ratio: float
    range_width_atr: float
    balance_valid: bool
    macro_bias: str
    built_at: int

    @property
    def width(self):
        return self.resistance.price - self.support.price

    def to_dict(self):
        value = asdict(self)
        value["levels"] = [item.to_dict() for item in self.levels]
        return value


@dataclass
class BreakoutLifecycle:
    transition_id: str
    parent_range_id: str
    level_id: str
    side: str
    level: float
    started_index: int
    started_time: int
    atr: float
    outside_flags: list = field(default_factory=list)
    extreme: float = 0.0
    accepted_index: int = None
    accepted_time: int = None
    b_event_id: str = None
    b_event_index: int = None


@dataclass
class SweepLifecycle:
    transition_id: str
    parent_transition_id: str
    parent_range_id: str
    level_id: str
    side: str
    level: float
    source: str
    started_index: int
    started_time: int
    expires_index: int
    extreme: float
    mss_level: float
    breakout_age_bars: int = 0


@dataclass
class ReactionLifecycle:
    transition_id: str
    parent_range_id: str
    level_id: str
    side: str
    level: float
    started_index: int
    started_time: int
    expires_index: int
    extreme: float
    mss_level: float


@dataclass(frozen=True)
class ABCEvent:
    event_id: str
    path: str
    side: str
    transition: str
    signal_time: int
    parent_transition_id: str
    range_id: str
    level_id: str
    level: float
    level_source_tf: str
    level_touches: int
    level_age_bars_4h: int
    level_test_count: int
    level_freshness: str
    level_volume_ratio: float
    level_score: float
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
    structure_efficiency_4h: float
    structure_containment_ratio: float
    structure_range_width_atr: float
    macro_bias_context: str
    calendar_phase_context: str
    breakout_age_bars: int = 0

    def to_dict(self):
        return asdict(self)


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _median(values):
    clean = [float(value) for value in values if _finite(value)]
    return statistics.median(clean) if clean else None


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


def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


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


def aggregate_daily(candles_4h):
    groups = {}
    for candle in candles_4h:
        key = int(candle["open_time"]) // MS_DAY
        groups.setdefault(key, []).append(candle)
    result = []
    for key in sorted(groups):
        rows = sorted(
            groups[key],
            key=lambda item: int(item["open_time"]),
        )
        unique_slots = {
            int(item["open_time"]) // MS_4H
            for item in rows
        }
        if len(unique_slots) != 6:
            continue
        result.append({
            "open_time": int(rows[0]["open_time"]),
            "close_time": int(rows[-1]["close_time"]),
            "open": float(rows[0]["open"]),
            "high": max(float(item["high"]) for item in rows),
            "low": min(float(item["low"]) for item in rows),
            "close": float(rows[-1]["close"]),
            "volume": sum(float(item.get("volume", 0.0)) for item in rows),
        })
    return result


def _confirmed_pivots(candles, left, right, source_tf):
    points = []
    volumes = [
        float(item.get("volume", 0.0))
        for item in candles
        if _finite(item.get("volume", 0.0))
        and float(item.get("volume", 0.0)) > 0
    ]
    volume_baseline = statistics.median(volumes) if volumes else 1.0
    for index in range(left, len(candles) - right):
        candle = candles[index]
        high = float(candle["high"])
        low = float(candle["low"])
        left_rows = candles[index - left:index]
        right_rows = candles[index + 1:index + right + 1]
        source_time = int(candle["close_time"])
        confirmed_time = int(candles[index + right]["close_time"])
        volume_ratio = (
            float(candle.get("volume", 0.0)) / volume_baseline
            if volume_baseline > 0
            else 1.0
        )
        if (
            high >= max(float(item["high"]) for item in left_rows)
            and high >= max(float(item["high"]) for item in right_rows)
            and any(
                high > float(item["high"])
                for item in left_rows + right_rows
            )
        ):
            points.append(PivotPoint(
                price=high,
                kind="HIGH",
                source_tf=source_tf,
                source_time=source_time,
                confirmed_time=confirmed_time,
                volume_ratio=volume_ratio,
            ))
        if (
            low <= min(float(item["low"]) for item in left_rows)
            and low <= min(float(item["low"]) for item in right_rows)
            and any(
                low < float(item["low"])
                for item in left_rows + right_rows
            )
        ):
            points.append(PivotPoint(
                price=low,
                kind="LOW",
                source_tf=source_tf,
                source_time=source_time,
                confirmed_time=confirmed_time,
                volume_ratio=volume_ratio,
            ))
    return points


def _cluster_points(points, tolerance):
    clusters = []
    for point in sorted(points, key=lambda item: item.price):
        if not clusters:
            clusters.append([point])
            continue
        center = statistics.median(
            item.price for item in clusters[-1]
        )
        if abs(point.price - center) <= tolerance:
            clusters[-1].append(point)
        else:
            clusters.append([point])
    return clusters


def _dedupe_touch_times(points):
    ordered = sorted(points, key=lambda item: item.source_time)
    result = []
    for point in ordered:
        if (
            result
            and point.source_time - result[-1].source_time
            < 12 * 60 * 60 * 1000
        ):
            if (
                point.source_tf == "1D"
                and result[-1].source_tf != "1D"
            ):
                result[-1] = point
            continue
        result.append(point)
    return result


def _touch_episodes(candles, level, zone_width, after_time):
    episodes = 0
    active = False
    for candle in candles:
        if int(candle["close_time"]) <= after_time:
            continue
        intersects = (
            float(candle["low"]) <= level + zone_width
            and float(candle["high"]) >= level - zone_width
        )
        if intersects and not active:
            episodes += 1
        active = intersects
    return episodes


def _level_volume_ratio(candles, level, zone_width):
    baseline = median_volume(candles, min(180, len(candles)))
    if not baseline:
        return 1.0
    touched = [
        float(candle.get("volume", 0.0))
        for candle in candles
        if (
            float(candle["low"]) <= level + zone_width
            and float(candle["high"]) >= level - zone_width
            and float(candle.get("volume", 0.0)) > 0
        )
    ]
    return (
        statistics.median(touched) / baseline
        if touched
        else 1.0
    )


def _level_id(cluster):
    primary = min(
        cluster,
        key=lambda item: (
            0 if item.source_tf == "1D" else 1,
            item.source_time,
            item.kind,
        ),
    )
    raw = (
        f"BTCUSDT|{primary.source_tf}|{primary.kind}|"
        f"{primary.source_time}"
    )
    digest = hashlib.sha1(raw.encode("ascii")).hexdigest()[:10]
    return (
        f"BTC-{primary.source_tf}-{primary.kind}-"
        f"{primary.source_time}-{digest}"
    )


def _build_levels(candles_4h, daily, atr_4h, params):
    sample_4h = candles_4h[-params.four_hour_lookback:]
    sample_daily = daily[-params.daily_lookback:]
    points = _confirmed_pivots(
        sample_daily,
        params.daily_pivot_left,
        params.daily_pivot_right,
        "1D",
    )
    points.extend(_confirmed_pivots(
        sample_4h,
        params.four_hour_pivot_left,
        params.four_hour_pivot_right,
        "4H",
    ))
    zone_width = params.level_zone_atr * atr_4h
    clusters = _cluster_points(
        points,
        params.level_merge_atr * atr_4h,
    )
    built_at = int(candles_4h[-1]["close_time"])
    levels = []
    for cluster in clusters:
        touches = _dedupe_touch_times(cluster)
        has_daily = any(item.source_tf == "1D" for item in cluster)
        has_4h = any(item.source_tf == "4H" for item in cluster)
        if not has_daily and len(touches) < params.min_four_hour_touches:
            continue
        weights = [
            3.0 if item.source_tf == "1D" else 1.0
            for item in cluster
        ]
        price = sum(
            item.price * weight
            for item, weight in zip(cluster, weights)
        ) / sum(weights)
        last_source = max(item.source_time for item in cluster)
        confirmed_time = max(item.confirmed_time for item in cluster)
        age = max(0, (built_at - last_source) // MS_4H)
        if age > params.max_level_age_4h:
            continue
        test_count = _touch_episodes(
            sample_4h,
            price,
            zone_width,
            confirmed_time,
        )
        freshness = (
            "FRESH"
            if test_count == 0
            else "TESTED"
            if test_count <= 2
            else "WEAK"
        )
        volume_ratio = _level_volume_ratio(
            sample_4h,
            price,
            zone_width,
        )
        timeframe_score = (
            4.0
            if has_daily and not has_4h
            else 4.75
            if has_daily and has_4h
            else 1.50
        )
        freshness_score = {
            "FRESH": 1.00,
            "TESTED": 0.35,
            "WEAK": -1.00,
        }[freshness]
        score = (
            timeframe_score
            + 0.65 * min(4, len(touches))
            + 0.40 * min(2.0, volume_ratio)
            + freshness_score
            - max(0, age - 180) / 360
        )
        if score < params.min_level_score:
            continue
        source_tf = (
            "1D+4H"
            if has_daily and has_4h
            else "1D"
            if has_daily
            else "4H"
        )
        levels.append(StructureLevel(
            level_id=_level_id(cluster),
            price=float(price),
            source_tf=source_tf,
            pivot_kinds=tuple(sorted({
                item.kind for item in cluster
            })),
            source_times=tuple(sorted({
                item.source_time for item in cluster
            })),
            confirmed_time=int(confirmed_time),
            last_source_time=int(last_source),
            touches=len(touches),
            age_bars_4h=int(age),
            test_count=int(test_count),
            freshness=freshness,
            volume_at_level_ratio=float(volume_ratio),
            score=float(score),
            zone_width=float(zone_width),
        ))
    return tuple(sorted(levels, key=lambda item: item.price))


def _macro_bias(daily):
    closes = [float(item["close"]) for item in daily]
    fast = ema(closes, 20)
    slow = ema(closes, 50)
    if fast is None or slow is None or not closes:
        return "NEUTRAL"
    if closes[-1] > fast > slow:
        return "BULL"
    if closes[-1] < fast < slow:
        return "BEAR"
    return "NEUTRAL"


def _containment(candles, support, resistance, lookback):
    sample = candles[-lookback:]
    if not sample:
        return 0.0
    inside = sum(
        support <= float(item["close"]) <= resistance
        for item in sample
    )
    return inside / len(sample)


def _range_id(support, resistance):
    raw = f"{support.level_id}|{resistance.level_id}"
    digest = hashlib.sha1(raw.encode("ascii")).hexdigest()[:10]
    return f"RANGE-{digest}"


def build_structure(candles_4h, params=PRIMARY):
    minimum = max(
        60,
        params.four_hour_pivot_left
        + params.four_hour_pivot_right
        + 20,
    )
    if len(candles_4h) < minimum:
        return None
    daily = aggregate_daily(candles_4h)
    if len(daily) < 20:
        return None
    atr_4h = atr_value(candles_4h[-60:])
    if not atr_4h:
        return None
    levels = _build_levels(candles_4h, daily, atr_4h, params)
    current = float(candles_4h[-1]["close"])
    supports = [item for item in levels if item.price < current]
    resistances = [item for item in levels if item.price > current]
    if not supports or not resistances:
        return None
    efficiency = efficiency_ratio(
        candles_4h,
        params.balance_lookback_4h,
    )
    if efficiency is None:
        return None
    candidates = []
    for support in supports:
        for resistance in resistances:
            width_atr = (
                resistance.price - support.price
            ) / atr_4h
            if not params.min_range_atr <= width_atr <= params.max_range_atr:
                continue
            containment = _containment(
                candles_4h,
                support.price - support.zone_width,
                resistance.price + resistance.zone_width,
                params.balance_lookback_4h,
            )
            distance = (
                abs(current - support.price)
                + abs(resistance.price - current)
            ) / atr_4h
            score = (
                support.score
                + resistance.score
                + 4.0 * containment
                - 0.08 * distance
            )
            candidates.append(
                (score, containment, width_atr, support, resistance)
            )
    if not candidates:
        return None
    _, containment, width_atr, support, resistance = max(
        candidates,
        key=lambda item: item[0],
    )
    balance_valid = (
        efficiency <= params.balance_efficiency_max
        and containment >= params.balance_containment_min
        and support.freshness != "WEAK"
        and resistance.freshness != "WEAK"
    )
    return StructureMap(
        range_id=_range_id(support, resistance),
        support=support,
        resistance=resistance,
        levels=levels,
        atr_4h=float(atr_4h),
        efficiency_4h=float(efficiency),
        containment_ratio=float(containment),
        range_width_atr=float(width_atr),
        balance_valid=bool(balance_valid),
        macro_bias=_macro_bias(daily),
        built_at=int(candles_4h[-1]["close_time"]),
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


class ABCStateMachineV2:
    def __init__(self, params=PRIMARY):
        self.params = params
        self.structure = None
        self.mode = "NO_STRUCTURE"
        self.breakout = None
        self.sweep = None
        self.reaction = None
        self.cooldown_until = -1
        self.structure_adopted_index = -1
        self.pending_range_id = None
        self.pending_range_hits = 0
        self.emitted_keys = set()
        self.last_a_event_by_level = {}

    def snapshot(self):
        return {
            "mode": self.mode,
            "range_id": (
                self.structure.range_id
                if self.structure
                else None
            ),
            "support_level_id": (
                self.structure.support.level_id
                if self.structure
                else None
            ),
            "resistance_level_id": (
                self.structure.resistance.level_id
                if self.structure
                else None
            ),
            "breakout": (
                asdict(self.breakout)
                if self.breakout
                else None
            ),
            "sweep": (
                asdict(self.sweep)
                if self.sweep
                else None
            ),
            "reaction": (
                asdict(self.reaction)
                if self.reaction
                else None
            ),
            "cooldown_until": self.cooldown_until,
        }

    def _adopt_structure(self, candidate, bar_index):
        if candidate is None:
            return
        if self.structure is None:
            self.structure = candidate
            self.structure_adopted_index = bar_index
            self.mode = "RANGE"
            return
        if candidate.range_id == self.structure.range_id:
            self.structure = candidate
            self.pending_range_id = None
            self.pending_range_hits = 0
            return
        if self.mode not in {"RANGE", "NO_STRUCTURE"}:
            return
        if self.pending_range_id == candidate.range_id:
            self.pending_range_hits += 1
        else:
            self.pending_range_id = candidate.range_id
            self.pending_range_hits = 1
        if (
            self.pending_range_hits
            >= self.params.structure_confirmation_updates
        ):
            self.structure = candidate
            self.structure_adopted_index = bar_index
            self.pending_range_id = None
            self.pending_range_hits = 0
            self.mode = "RANGE"

    def _level(self, level_id):
        if not self.structure:
            return None
        for level in self.structure.levels:
            if level.level_id == level_id:
                return level
        for level in (
            self.structure.support,
            self.structure.resistance,
        ):
            if level.level_id == level_id:
                return level
        return None

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
        inside = self.params.sweep_reclaim_atr * atr
        return (
            close < level - inside
            if side == "LONG"
            else close > level + inside
        )

    def _breakout_candidate(
        self,
        candle,
        side,
        level,
        atr,
        volume_ratio,
    ):
        if not self._outside(candle, side, level, atr):
            return False
        metrics = candle_metrics(candle, side)
        close = float(candle["close"])
        distance = (
            close - level
            if side == "LONG"
            else level - close
        ) / atr
        return (
            volume_ratio >= self.params.breakout_volume_min
            and metrics["direction_ok"]
            and metrics["body_ratio"]
            >= self.params.breakout_body_min
            and metrics["close_position"]
            >= self.params.breakout_close_min
            and distance <= self.params.breakout_max_distance_atr
        )

    def _reaction_valid(self, metrics, volume_ratio):
        return (
            volume_ratio >= self.params.reaction_volume_min
            and metrics["close_position"]
            >= self.params.reaction_close_min
            and (
                metrics["direction_ok"]
                or metrics["wick_ratio"]
                >= self.params.reaction_wick_min
            )
        )

    def _displacement_valid(self, metrics, volume_ratio):
        return (
            volume_ratio
            >= self.params.sweep_displacement_volume_min
            and metrics["direction_ok"]
            and metrics["body_ratio"]
            >= self.params.sweep_displacement_body_min
            and metrics["close_position"]
            >= self.params.sweep_displacement_close_min
        )

    def _planned_target(self, path, side):
        structure = self.structure
        if path in {"A", "C"}:
            return (
                structure.resistance.price
                if side == "LONG"
                else structure.support.price
            )
        external = [
            item.price
            for item in structure.levels
            if (
                item.price > structure.resistance.price
                if side == "LONG"
                else item.price < structure.support.price
            )
        ]
        if not external:
            return 0.0
        return min(external) if side == "LONG" else max(external)

    def _event(
        self,
        path,
        side,
        transition,
        candle,
        level_id,
        extreme,
        atr,
        volume_ratio,
        metrics,
        bar_index,
        parent_transition_id,
        breakout_age_bars=0,
    ):
        structure = self.structure
        level = self._level(level_id)
        if not structure or not level:
            return None
        close = float(candle["close"])
        stop = (
            min(
                extreme - 0.10 * atr,
                level.price - self.params.stop_buffer_atr * atr,
            )
            if side == "LONG"
            else max(
                extreme + 0.10 * atr,
                level.price + self.params.stop_buffer_atr * atr,
            )
        )
        risk = close - stop if side == "LONG" else stop - close
        if risk <= 0:
            return None
        target = self._planned_target(path, side)
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
        event_key = (
            path,
            transition,
            structure.range_id,
            level.level_id,
            parent_transition_id,
        )
        if event_key in self.emitted_keys:
            return None
        raw_id = (
            f"{path}|{transition}|{level.level_id}|"
            f"{int(candle['close_time'])}|{parent_transition_id}"
        )
        event_id = (
            f"ABC-{path}-"
            f"{hashlib.sha1(raw_id.encode('ascii')).hexdigest()[:12]}"
        )
        self.emitted_keys.add(event_key)
        self.cooldown_until = (
            bar_index + self.params.signal_cooldown_bars
        )
        event = ABCEvent(
            event_id=event_id,
            path=path,
            side=side,
            transition=transition,
            signal_time=int(candle["close_time"]),
            parent_transition_id=parent_transition_id,
            range_id=structure.range_id,
            level_id=level.level_id,
            level=float(level.price),
            level_source_tf=level.source_tf,
            level_touches=int(level.touches),
            level_age_bars_4h=int(level.age_bars_4h),
            level_test_count=int(level.test_count),
            level_freshness=level.freshness,
            level_volume_ratio=float(level.volume_at_level_ratio),
            level_score=float(level.score),
            support=float(structure.support.price),
            resistance=float(structure.resistance.price),
            extreme=float(extreme),
            atr_15m=float(atr),
            volume_ratio=float(volume_ratio),
            body_ratio=float(metrics["body_ratio"]),
            close_position=float(metrics["close_position"]),
            wick_ratio=float(metrics["wick_ratio"]),
            planned_target=float(target),
            planned_rr=float(planned_rr),
            structure_efficiency_4h=float(
                structure.efficiency_4h
            ),
            structure_containment_ratio=float(
                structure.containment_ratio
            ),
            structure_range_width_atr=float(
                structure.range_width_atr
            ),
            macro_bias_context=structure.macro_bias,
            calendar_phase_context=calendar_phase(
                int(candle["close_time"])
            ),
            breakout_age_bars=int(breakout_age_bars),
        )
        if path == "A":
            self.last_a_event_by_level[level.level_id] = event.event_id
        return event

    def _mss_level(self, history, side):
        sample = history[-self.params.sweep_mss_lookback:]
        if not sample:
            return None
        return (
            max(float(item["high"]) for item in sample)
            if side == "LONG"
            else min(float(item["low"]) for item in sample)
        )

    def _start_breakout(
        self,
        candle,
        side,
        level,
        atr,
        bar_index,
    ):
        raw = (
            f"{self.structure.range_id}|{level.level_id}|"
            f"{side}|{int(candle['close_time'])}"
        )
        transition_id = (
            "BREAKOUT-"
            + hashlib.sha1(raw.encode("ascii")).hexdigest()[:12]
        )
        self.breakout = BreakoutLifecycle(
            transition_id=transition_id,
            parent_range_id=self.structure.range_id,
            level_id=level.level_id,
            side=side,
            level=float(level.price),
            started_index=bar_index,
            started_time=int(candle["close_time"]),
            atr=float(atr),
            outside_flags=[True],
            extreme=(
                float(candle["high"])
                if side == "LONG"
                else float(candle["low"])
            ),
        )
        self.mode = "BREAKOUT_PENDING"

    def _start_sweep(
        self,
        candle,
        side,
        level,
        bar_index,
        history,
        source,
        parent_transition_id,
        extreme=None,
        breakout_age_bars=0,
    ):
        mss_level = self._mss_level(history, side)
        if mss_level is None:
            return False
        extreme_value = (
            float(candle["low"])
            if side == "LONG"
            else float(candle["high"])
        ) if extreme is None else float(extreme)
        raw = (
            f"{source}|{level.level_id}|{side}|"
            f"{int(candle['close_time'])}|{parent_transition_id}"
        )
        transition_id = (
            "SWEEP-"
            + hashlib.sha1(raw.encode("ascii")).hexdigest()[:12]
        )
        self.sweep = SweepLifecycle(
            transition_id=transition_id,
            parent_transition_id=parent_transition_id,
            parent_range_id=self.structure.range_id,
            level_id=level.level_id,
            side=side,
            level=float(level.price),
            source=source,
            started_index=bar_index,
            started_time=int(candle["close_time"]),
            expires_index=(
                bar_index + self.params.sweep_confirmation_bars
            ),
            extreme=extreme_value,
            mss_level=float(mss_level),
            breakout_age_bars=int(breakout_age_bars),
        )
        self.breakout = None
        self.reaction = None
        self.mode = "SWEEP_CONFIRMING"
        return True

    def _start_reaction(
        self,
        candle,
        side,
        level,
        bar_index,
        history,
    ):
        mss_level = self._mss_level(history, side)
        if mss_level is None:
            return False
        raw = (
            f"A_REACTION|{self.structure.range_id}|"
            f"{level.level_id}|{side}|{int(candle['close_time'])}"
        )
        transition_id = (
            "A-REACTION-"
            + hashlib.sha1(raw.encode("ascii")).hexdigest()[:12]
        )
        self.reaction = ReactionLifecycle(
            transition_id=transition_id,
            parent_range_id=self.structure.range_id,
            level_id=level.level_id,
            side=side,
            level=float(level.price),
            started_index=bar_index,
            started_time=int(candle["close_time"]),
            expires_index=(
                bar_index + self.params.sweep_confirmation_bars
            ),
            extreme=(
                float(candle["low"])
                if side == "LONG"
                else float(candle["high"])
            ),
            mss_level=float(mss_level),
        )
        self.mode = "A_CONFIRMING"
        return True

    def _reset_range(self, candidate=None):
        self.breakout = None
        self.sweep = None
        self.reaction = None
        self.mode = "RANGE" if self.structure else "NO_STRUCTURE"
        if (
            candidate is not None
            and self.structure is not None
            and candidate.range_id == self.structure.range_id
        ):
            self.structure = candidate

    def _sweep_update(
        self,
        candle,
        bar_index,
        atr,
        volume_ratio,
        candidate,
    ):
        sweep = self.sweep
        if sweep is None:
            self._reset_range(candidate)
            return None
        if sweep.side == "LONG":
            sweep.extreme = min(sweep.extreme, float(candle["low"]))
            reclaimed = (
                float(candle["close"])
                > sweep.level
                + self.params.sweep_reclaim_atr * atr
            )
            mss_confirmed = (
                float(candle["close"])
                > sweep.mss_level
                + self.params.sweep_mss_buffer_atr * atr
            )
            invalidated = (
                float(candle["close"])
                < sweep.level
                - self.params.sweep_max_atr * atr
            )
        else:
            sweep.extreme = max(sweep.extreme, float(candle["high"]))
            reclaimed = (
                float(candle["close"])
                < sweep.level
                - self.params.sweep_reclaim_atr * atr
            )
            mss_confirmed = (
                float(candle["close"])
                < sweep.mss_level
                - self.params.sweep_mss_buffer_atr * atr
            )
            invalidated = (
                float(candle["close"])
                > sweep.level
                + self.params.sweep_max_atr * atr
            )
        if invalidated or bar_index > sweep.expires_index:
            self._reset_range(candidate)
            return None
        metrics = candle_metrics(candle, sweep.side)
        if (
            bar_index > sweep.started_index
            and reclaimed
            and mss_confirmed
            and self._displacement_valid(metrics, volume_ratio)
        ):
            if sweep.source == "A_BOUNDARY":
                transition = "A_BOUNDARY_SWEEP_RECLAIM_MSS"
            elif sweep.source == "A_REACTION":
                transition = "A_REACTION_SWEEP_RECLAIM_MSS"
            else:
                transition = "FAILED_B_RECLAIM_MSS"
            event = self._event(
                "C",
                sweep.side,
                transition,
                candle,
                sweep.level_id,
                sweep.extreme,
                atr,
                volume_ratio,
                metrics,
                bar_index,
                sweep.parent_transition_id,
                sweep.breakout_age_bars,
            )
            self._reset_range(candidate)
            return event
        return None

    def _reaction_update(
        self,
        candle,
        bar_index,
        atr,
        volume_ratio,
        history,
        candidate,
    ):
        reaction = self.reaction
        if reaction is None:
            self._reset_range(candidate)
            return None
        if reaction.side == "LONG":
            reaction.extreme = min(
                reaction.extreme,
                float(candle["low"]),
            )
            mss_confirmed = (
                float(candle["close"])
                > reaction.mss_level
                + self.params.sweep_mss_buffer_atr * atr
            )
            invalidated = (
                float(candle["close"])
                < reaction.level
                - self.params.sweep_max_atr * atr
            )
        else:
            reaction.extreme = max(
                reaction.extreme,
                float(candle["high"]),
            )
            mss_confirmed = (
                float(candle["close"])
                < reaction.mss_level
                - self.params.sweep_mss_buffer_atr * atr
            )
            invalidated = (
                float(candle["close"])
                > reaction.level
                + self.params.sweep_max_atr * atr
            )
        penetration = (
            reaction.level - float(candle["low"])
            if reaction.side == "LONG"
            else float(candle["high"]) - reaction.level
        )
        if self.params.c_supersedes_a_on_same_level_sweep:
            sweep_min = self.params.sweep_buffer_atr * atr
            sweep_max = self.params.sweep_max_atr * atr
            if penetration > sweep_max:
                self._reset_range(candidate)
                return None
            if penetration > sweep_min:
                level = self._level(reaction.level_id)
                if level is not None and self._start_sweep(
                    candle,
                    reaction.side,
                    level,
                    bar_index,
                    history,
                    "A_REACTION",
                    reaction.transition_id,
                    extreme=reaction.extreme,
                ):
                    return None
        if invalidated or bar_index > reaction.expires_index:
            self._reset_range(candidate)
            return None
        metrics = candle_metrics(candle, reaction.side)
        if (
            bar_index > reaction.started_index
            and mss_confirmed
            and self._displacement_valid(metrics, volume_ratio)
        ):
            event = self._event(
                "A",
                reaction.side,
                "VALIDATED_RANGE_REACTION_MSS",
                candle,
                reaction.level_id,
                reaction.extreme,
                atr,
                volume_ratio,
                metrics,
                bar_index,
                reaction.parent_range_id,
            )
            self._reset_range(candidate)
            return event
        return None

    def _failed_breakout_to_sweep(
        self,
        candle,
        bar_index,
        history,
    ):
        if not self.params.allow_failed_b_c:
            return False
        breakout = self.breakout
        if breakout is None:
            return False
        level = self._level(breakout.level_id)
        if level is None:
            return False
        reverse_side = (
            "SHORT" if breakout.side == "LONG" else "LONG"
        )
        parent = breakout.b_event_id or breakout.transition_id
        source = (
            "FAILED_B"
            if breakout.b_event_id
            else "FAILED_BREAKOUT"
        )
        age = bar_index - breakout.started_index
        return self._start_sweep(
            candle,
            reverse_side,
            level,
            bar_index,
            history,
            source,
            parent,
            extreme=breakout.extreme,
            breakout_age_bars=age,
        )

    def _pending_update(
        self,
        candle,
        bar_index,
        atr,
        history,
        candidate,
    ):
        breakout = self.breakout
        side = breakout.side
        outside = self._outside(
            candle,
            side,
            breakout.level,
            atr,
        )
        breakout.outside_flags.append(outside)
        breakout.outside_flags = breakout.outside_flags[
            -self.params.acceptance_window_bars:
        ]
        breakout.extreme = (
            max(breakout.extreme, float(candle["high"]))
            if side == "LONG"
            else min(breakout.extreme, float(candle["low"]))
        )
        age = bar_index - breakout.started_index
        if self._inside_old_range(
            candle,
            side,
            breakout.level,
            atr,
        ):
            if not self._failed_breakout_to_sweep(
                candle,
                bar_index,
                history,
            ):
                self._reset_range(candidate)
            return None
        accepted = (
            len(breakout.outside_flags)
            >= self.params.acceptance_window_bars
            and sum(breakout.outside_flags)
            >= self.params.acceptance_min_outside
            and breakout.outside_flags[-1]
        )
        if accepted:
            breakout.accepted_index = bar_index
            breakout.accepted_time = int(candle["close_time"])
            self.mode = "BREAKOUT_ACCEPTED"
        elif age >= self.params.breakout_pending_bars:
            self._reset_range(candidate)
        return None

    def _accepted_update(
        self,
        candle,
        bar_index,
        atr,
        volume_ratio,
        history,
        candidate,
    ):
        breakout = self.breakout
        side = breakout.side
        age = bar_index - breakout.started_index
        breakout.extreme = (
            max(breakout.extreme, float(candle["high"]))
            if side == "LONG"
            else min(breakout.extreme, float(candle["low"]))
        )
        if self._inside_old_range(
            candle,
            side,
            breakout.level,
            atr,
        ):
            if not self._failed_breakout_to_sweep(
                candle,
                bar_index,
                history,
            ):
                self._reset_range(candidate)
            return None
        tolerance = self.params.retest_tolerance_atr * atr
        close = float(candle["close"])
        low = float(candle["low"])
        high = float(candle["high"])
        if side == "LONG":
            touched = (
                low <= breakout.level + tolerance
                and high >= breakout.level
            )
            held = (
                close
                > breakout.level
                + self.params.sweep_reclaim_atr * atr
            )
            extreme = low
        else:
            touched = (
                high >= breakout.level - tolerance
                and low <= breakout.level
            )
            held = (
                close
                < breakout.level
                - self.params.sweep_reclaim_atr * atr
            )
            extreme = high
        metrics = candle_metrics(candle, side)
        valid_retest = (
            touched
            and held
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
                "ACCEPTED_BREAKOUT_EXACT_LEVEL_RETEST",
                candle,
                breakout.level_id,
                extreme,
                atr,
                volume_ratio,
                metrics,
                bar_index,
                breakout.transition_id,
                age,
            )
            if event:
                breakout.b_event_id = event.event_id
                breakout.b_event_index = bar_index
                self.mode = "B_HOLD_MONITOR"
            return event
        if (
            breakout.accepted_index is not None
            and bar_index - breakout.accepted_index
            >= self.params.retest_expiry_bars
        ):
            self._reset_range(candidate)
        return None

    def _b_hold_update(
        self,
        candle,
        bar_index,
        atr,
        history,
        candidate,
    ):
        breakout = self.breakout
        if self._inside_old_range(
            candle,
            breakout.side,
            breakout.level,
            atr,
        ):
            if not self._failed_breakout_to_sweep(
                candle,
                bar_index,
                history,
            ):
                self._reset_range(candidate)
            return None
        if (
            breakout.b_event_index is not None
            and bar_index - breakout.b_event_index
            >= self.params.b_hold_monitor_bars
        ):
            self._reset_range(candidate)
        return None

    def _range_update(
        self,
        candle,
        bar_index,
        atr,
        volume_ratio,
        history,
    ):
        structure = self.structure
        if (
            not structure.balance_valid
            or bar_index - self.structure_adopted_index
            < self.params.min_structure_monitor_bars
        ):
            return None
        for side, level in (
            ("LONG", structure.resistance),
            ("SHORT", structure.support),
        ):
            if self._breakout_candidate(
                candle,
                side,
                level.price,
                atr,
                volume_ratio,
            ):
                self._start_breakout(
                    candle,
                    side,
                    level,
                    atr,
                    bar_index,
                )
                return None

        low = float(candle["low"])
        high = float(candle["high"])
        close = float(candle["close"])
        sweep_min = self.params.sweep_buffer_atr * atr
        sweep_max = self.params.sweep_max_atr * atr
        reclaim = self.params.sweep_reclaim_atr * atr
        support = structure.support
        resistance = structure.resistance
        support_sweep = (
            support.price - sweep_max
            <= low
            < support.price - sweep_min
            and close > support.price + reclaim
        )
        resistance_sweep = (
            resistance.price + sweep_min
            < high
            <= resistance.price + sweep_max
            and close < resistance.price - reclaim
        )
        if support_sweep and not resistance_sweep:
            parent = self.last_a_event_by_level.get(
                support.level_id,
                structure.range_id,
            )
            self._start_sweep(
                candle,
                "LONG",
                support,
                bar_index,
                history,
                "A_BOUNDARY",
                parent,
            )
            return None
        if resistance_sweep and not support_sweep:
            parent = self.last_a_event_by_level.get(
                resistance.level_id,
                structure.range_id,
            )
            self._start_sweep(
                candle,
                "SHORT",
                resistance,
                bar_index,
                history,
                "A_BOUNDARY",
                parent,
            )
            return None
        if bar_index < self.cooldown_until:
            return None

        support_touch = (
            support.price - sweep_min
            <= low
            <= support.price + support.zone_width
            and close > support.price + reclaim
        )
        resistance_touch = (
            resistance.price - resistance.zone_width
            <= high
            <= resistance.price + sweep_min
            and close < resistance.price - reclaim
        )
        long_metrics = candle_metrics(candle, "LONG")
        short_metrics = candle_metrics(candle, "SHORT")
        a_width_valid = (
            self.params.a_min_range_width_atr
            <= structure.range_width_atr
            <= self.params.a_max_range_width_atr
        )
        if (
            a_width_valid
            and support_touch
            and not resistance_touch
            and self._reaction_valid(long_metrics, volume_ratio)
        ):
            if self.params.a_requires_mss:
                self._start_reaction(
                    candle,
                    "LONG",
                    support,
                    bar_index,
                    history,
                )
                return None
            return self._event(
                "A",
                "LONG",
                "VALIDATED_RANGE_SUPPORT_REACTION",
                candle,
                support.level_id,
                low,
                atr,
                volume_ratio,
                long_metrics,
                bar_index,
                structure.range_id,
            )
        if (
            a_width_valid
            and resistance_touch
            and not support_touch
            and self._reaction_valid(short_metrics, volume_ratio)
        ):
            if self.params.a_requires_mss:
                self._start_reaction(
                    candle,
                    "SHORT",
                    resistance,
                    bar_index,
                    history,
                )
                return None
            return self._event(
                "A",
                "SHORT",
                "VALIDATED_RANGE_RESISTANCE_REACTION",
                candle,
                resistance.level_id,
                high,
                atr,
                volume_ratio,
                short_metrics,
                bar_index,
                structure.range_id,
            )
        return None

    def update(
        self,
        candle,
        bar_index,
        dynamic_structure,
        atr_15m,
        volume_baseline,
        history_15m,
    ):
        if (
            not atr_15m
            or atr_15m <= 0
            or not volume_baseline
            or volume_baseline <= 0
        ):
            return None
        self._adopt_structure(dynamic_structure, bar_index)
        if self.structure is None:
            return None
        volume_ratio = (
            float(candle.get("volume", 0.0))
            / float(volume_baseline)
        )
        if not _finite(volume_ratio):
            return None
        if self.mode == "SWEEP_CONFIRMING":
            return self._sweep_update(
                candle,
                bar_index,
                atr_15m,
                volume_ratio,
                dynamic_structure,
            )
        if self.mode == "A_CONFIRMING":
            return self._reaction_update(
                candle,
                bar_index,
                atr_15m,
                volume_ratio,
                history_15m,
                dynamic_structure,
            )
        if self.mode == "BREAKOUT_PENDING":
            return self._pending_update(
                candle,
                bar_index,
                atr_15m,
                history_15m,
                dynamic_structure,
            )
        if self.mode == "BREAKOUT_ACCEPTED":
            return self._accepted_update(
                candle,
                bar_index,
                atr_15m,
                volume_ratio,
                history_15m,
                dynamic_structure,
            )
        if self.mode == "B_HOLD_MONITOR":
            return self._b_hold_update(
                candle,
                bar_index,
                atr_15m,
                history_15m,
                dynamic_structure,
            )
        return self._range_update(
            candle,
            bar_index,
            atr_15m,
            volume_ratio,
            history_15m,
        )
