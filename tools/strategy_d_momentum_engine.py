import math
from dataclasses import asdict, dataclass


MS_4H = 4 * 60 * 60 * 1000
MS_DAY = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class D1Parameters:
    name: str = "D1_TSMOM_7_30_90"
    momentum_days: tuple = (7, 30, 90)
    atr_bars: int = 20
    initial_stop_atr: float = 2.0
    trailing_stop_atr: float = 3.0
    max_hold_bars: int = 1080
    baseline_cost_pct: float = 0.0014
    stress_cost_pct: float = 0.0020
    adverse_funding_daily_pct: float = 0.0003


D1 = D1Parameters()


def contiguous(candles, start, end):
    if start < 0 or end >= len(candles) or start > end:
        return False
    expected = (end - start) * MS_4H
    actual = (
        int(candles[end]["open_time"])
        - int(candles[start]["open_time"])
    )
    return actual == expected


def true_range(candle, previous_close):
    high = float(candle["high"])
    low = float(candle["low"])
    return max(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close),
    )


def build_atr_cache(candles, bars):
    result = [None] * len(candles)
    seed = []
    previous_atr = None
    for index in range(1, len(candles)):
        if not contiguous(candles, index - 1, index):
            seed = []
            previous_atr = None
            continue
        value = true_range(
            candles[index],
            float(candles[index - 1]["close"]),
        )
        if previous_atr is None:
            seed.append(value)
            if len(seed) < bars:
                continue
            if len(seed) > bars:
                seed = seed[-bars:]
            previous_atr = sum(seed) / bars
        else:
            previous_atr = (
                previous_atr * (bars - 1) + value
            ) / bars
        if math.isfinite(previous_atr) and previous_atr > 0:
            result[index] = previous_atr
    return result


def atr_at(candles, index, bars):
    return build_atr_cache(candles, bars)[index]


def momentum_state(candles, index, params=D1):
    returns = {}
    current = float(candles[index]["close"])
    for days in params.momentum_days:
        bars = int(days * 6)
        previous_index = index - bars
        if (
            previous_index < 0
            or not contiguous(candles, previous_index, index)
        ):
            return None
        previous = float(candles[previous_index]["close"])
        if previous <= 0:
            return None
        returns[str(days)] = current / previous - 1.0
    values = tuple(returns.values())
    if all(value > 0 for value in values):
        state = "LONG"
    elif all(value < 0 for value in values):
        state = "SHORT"
    else:
        state = "NEUTRAL"
    return {
        "state": state,
        "returns": returns,
    }


def _exit_price_for_stop(candle, side, stop):
    open_price = float(candle["open"])
    if side == "LONG":
        if open_price <= stop:
            return open_price
        if float(candle["low"]) <= stop:
            return stop
    else:
        if open_price >= stop:
            return open_price
        if float(candle["high"]) >= stop:
            return stop
    return None


def _finish(position, candle, exit_index, exit_price, reason, params):
    side = position["side"]
    entry = float(position["entry"])
    risk = float(position["initial_risk"])
    gross_r = (
        (exit_price - entry) / risk
        if side == "LONG"
        else (entry - exit_price) / risk
    )
    risk_pct = risk / entry
    hold_ms = max(
        0,
        int(candle["open_time"]) - int(position["entry_time"]),
    )
    hold_days = hold_ms / MS_DAY
    baseline_cost_r = params.baseline_cost_pct / risk_pct
    stress_cost_r = params.stress_cost_pct / risk_pct
    funding_stress_r = (
        params.adverse_funding_daily_pct
        * hold_days
        / risk_pct
    )
    return {
        "strategy": params.name,
        "pair": "BTCUSDT",
        "signal_time": int(position["signal_time"]),
        "entry_time": int(position["entry_time"]),
        "exit_time": int(candle["open_time"]),
        "entry_index": int(position["entry_index"]),
        "exit_index": int(exit_index),
        "side": side,
        "entry": entry,
        "initial_stop": float(position["initial_stop"]),
        "exit": float(exit_price),
        "exit_reason": reason,
        "initial_risk": risk,
        "risk_pct": risk_pct,
        "hold_bars": int(exit_index - position["entry_index"]),
        "hold_days": hold_days,
        "MFE_R": float(position["mfe"] / risk),
        "MAE_R": float(position["mae"] / risk),
        "gross_R": gross_r,
        "baseline_cost_R": baseline_cost_r,
        "stress_cost_R": stress_cost_r,
        "funding_stress_R": funding_stress_r,
        "net_R": gross_r - baseline_cost_r,
        "stress_net_R": (
            gross_r - stress_cost_r - funding_stress_r
        ),
        "signal_returns": dict(position["signal_returns"]),
    }


def simulate(
    candles,
    start_ms,
    end_ms,
    params=D1,
    allowed_sides=None,
    finalize=True,
    return_state=False,
):
    admitted = (
        set(allowed_sides)
        if allowed_sides is not None
        else {"LONG", "SHORT"}
    )
    records = []
    diagnostics = {
        "bars": 0,
        "invalid_clock": 0,
        "invalid_execution_clock": 0,
        "invalid_atr": 0,
        "state_LONG": 0,
        "state_SHORT": 0,
        "state_NEUTRAL": 0,
        "entries_LONG": 0,
        "entries_SHORT": 0,
        "exits_STOP": 0,
        "exits_MOMENTUM_FLIP": 0,
        "exits_MAX_HOLD": 0,
        "exits_END_OF_DATA": 0,
    }
    warmup = max(params.momentum_days) * 6
    atr_cache = build_atr_cache(candles, params.atr_bars)
    position = None
    previous_state = None

    for index in range(warmup, len(candles)):
        candle = candles[index]
        close_time = int(candle["close_time"])
        if close_time < start_ms:
            state_data = momentum_state(candles, index, params)
            previous_state = (
                state_data["state"] if state_data else None
            )
            continue
        if close_time > end_ms:
            break
        diagnostics["bars"] += 1
        state_data = momentum_state(candles, index, params)
        if state_data is None:
            diagnostics["invalid_clock"] += 1
            previous_state = None
            continue
        state = state_data["state"]
        diagnostics[f"state_{state}"] += 1
        atr = atr_cache[index]
        exited = False
        next_candle = None
        if (
            index + 1 < len(candles)
            and contiguous(candles, index, index + 1)
            and int(candles[index + 1]["open_time"]) <= end_ms
        ):
            next_candle = candles[index + 1]

        if position is not None and index >= position["entry_index"]:
            if position["side"] == "LONG":
                position["mfe"] = max(
                    position["mfe"],
                    float(candle["high"]) - position["entry"],
                )
                position["mae"] = max(
                    position["mae"],
                    position["entry"] - float(candle["low"]),
                )
            else:
                position["mfe"] = max(
                    position["mfe"],
                    position["entry"] - float(candle["low"]),
                )
                position["mae"] = max(
                    position["mae"],
                    float(candle["high"]) - position["entry"],
                )
            stop_exit = _exit_price_for_stop(
                candle,
                position["side"],
                position["stop"],
            )
            if stop_exit is not None:
                records.append(_finish(
                    position,
                    candle,
                    index,
                    stop_exit,
                    "STOP",
                    params,
                ))
                diagnostics["exits_STOP"] += 1
                position = None
                exited = True
            elif atr is not None:
                close = float(candle["close"])
                if position["side"] == "LONG":
                    position["best_close"] = max(
                        position["best_close"],
                        close,
                    )
                    position["stop"] = max(
                        position["stop"],
                        position["best_close"]
                        - params.trailing_stop_atr * atr,
                    )
                    momentum_flip = (
                        state_data["returns"][
                            str(params.momentum_days[0])
                        ] < 0
                    )
                else:
                    position["best_close"] = min(
                        position["best_close"],
                        close,
                    )
                    position["stop"] = min(
                        position["stop"],
                        position["best_close"]
                        + params.trailing_stop_atr * atr,
                    )
                    momentum_flip = (
                        state_data["returns"][
                            str(params.momentum_days[0])
                        ] > 0
                    )
                hold_bars = index - position["entry_index"] + 1
                reason = None
                if momentum_flip:
                    reason = "MOMENTUM_FLIP"
                elif hold_bars >= params.max_hold_bars:
                    reason = "MAX_HOLD"
                if reason and next_candle is not None:
                    records.append(_finish(
                        position,
                        next_candle,
                        index + 1,
                        float(next_candle["open"]),
                        reason,
                        params,
                    ))
                    diagnostics[f"exits_{reason}"] += 1
                    position = None
                    exited = True

        if (
            position is None
            and not exited
            and state in ("LONG", "SHORT")
            and state in admitted
            and state != previous_state
        ):
            if next_candle is None:
                diagnostics["invalid_execution_clock"] += 1
            elif atr is None:
                diagnostics["invalid_atr"] += 1
            else:
                entry_index = index + 1
                entry_candle = next_candle
                entry = float(entry_candle["open"])
                risk = params.initial_stop_atr * atr
                stop = (
                    entry - risk
                    if state == "LONG"
                    else entry + risk
                )
                position = {
                    "side": state,
                    "signal_time": close_time,
                    "entry_time": int(entry_candle["open_time"]),
                    "entry_index": entry_index,
                    "entry": entry,
                    "initial_stop": stop,
                    "stop": stop,
                    "initial_risk": risk,
                    "best_close": entry,
                    "mfe": 0.0,
                    "mae": 0.0,
                    "signal_returns": state_data["returns"],
                }
                diagnostics[f"entries_{state}"] += 1
        previous_state = state

    if position is not None and finalize:
        final_index = min(
            len(candles) - 1,
            max(
                position["entry_index"],
                next(
                    (
                        index
                        for index in range(
                            position["entry_index"],
                            len(candles),
                        )
                        if int(candles[index]["close_time"])
                        > end_ms
                    ),
                    len(candles) - 1,
                ) - 1,
            ),
        )
        final_candle = candles[final_index]
        records.append(_finish(
            position,
            final_candle,
            final_index,
            float(final_candle["close"]),
            "END_OF_DATA",
            params,
        ))
        diagnostics["exits_END_OF_DATA"] += 1
        position = None
    if return_state:
        return records, diagnostics, position
    return records, diagnostics


def parameters_dict(params=D1):
    return asdict(params)
