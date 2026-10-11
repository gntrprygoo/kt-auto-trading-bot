import bisect
import math
import sqlite3
import statistics


MS_HOUR = 60 * 60 * 1000


def _zscore(values):
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    deviation = statistics.pstdev(values)
    if deviation <= 0:
        return 0.0
    return (values[-1] - mean) / deviation


class DerivativesResolver:
    """Leakage-safe as-of resolver for the B7 derivatives SQLite store."""

    def __init__(self, database):
        self.connection = sqlite3.connect(str(database))
        self.connection.row_factory = sqlite3.Row
        self._cache = {}

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def symbols(self):
        rows = self.connection.execute(
            "SELECT DISTINCT symbol FROM metrics_hourly ORDER BY symbol"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def _load_symbol(self, symbol):
        if symbol in self._cache:
            return self._cache[symbol]
        metrics = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT observed_at, open_interest, taker_ratio_median,
                       top_account_ratio, top_position_ratio,
                       global_account_ratio
                FROM metrics_hourly
                WHERE symbol = ?
                ORDER BY observed_at
                """,
                (symbol,),
            )
        ]
        funding = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT event_time, funding_rate
                FROM funding_events
                WHERE symbol = ?
                ORDER BY event_time
                """,
                (symbol,),
            )
        ]
        premium = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT close_time, close
                FROM premium_hourly
                WHERE symbol = ?
                ORDER BY close_time
                """,
                (symbol,),
            )
        ]
        result = {
            "metrics": metrics,
            "metrics_times": [
                int(item["observed_at"])
                for item in metrics
            ],
            "funding": funding,
            "funding_times": [
                int(item["event_time"])
                for item in funding
            ],
            "premium": premium,
            "premium_times": [
                int(item["close_time"])
                for item in premium
            ],
        }
        self._cache[symbol] = result
        return result

    @staticmethod
    def _asof_index(times, timestamp):
        return bisect.bisect_right(times, int(timestamp)) - 1

    def context(
        self,
        symbol,
        timestamp,
        side,
        oi_lookback_hours=12,
        funding_window=90,
        premium_window=168,
    ):
        data = self._load_symbol(symbol)
        metric_index = self._asof_index(
            data["metrics_times"],
            timestamp,
        )
        target_time = int(timestamp) - oi_lookback_hours * MS_HOUR
        prior_index = self._asof_index(
            data["metrics_times"],
            target_time,
        )
        funding_index = self._asof_index(
            data["funding_times"],
            timestamp,
        )
        premium_index = self._asof_index(
            data["premium_times"],
            timestamp,
        )
        complete = (
            metric_index >= 2
            and prior_index >= 0
            and funding_index >= 29
            and premium_index >= 71
        )
        result = {
            "derivatives_complete": complete,
            "derivatives_observed_at": None,
            "oi_change_12h": None,
            "taker_ratio_3h": None,
            "flow_aligned": None,
            "funding_z": None,
            "premium_z": None,
            "crowding_veto": None,
            "oi_flow_score": None,
            "oi_soft_weight": 1.0,
            "oi_hard_confirmed": False,
        }
        if not complete:
            return result

        latest = data["metrics"][metric_index]
        prior = data["metrics"][prior_index]
        observed_at = int(latest["observed_at"])
        prior_observed_at = int(prior["observed_at"])
        if (
            int(timestamp) - observed_at > 2 * MS_HOUR
            or target_time - prior_observed_at > 2 * MS_HOUR
        ):
            return result
        latest_oi = float(latest["open_interest"])
        prior_oi = float(prior["open_interest"])
        if latest_oi <= 0 or prior_oi <= 0:
            return result
        oi_change = latest_oi / prior_oi - 1.0
        taker_values = [
            float(item["taker_ratio_median"])
            for item in data["metrics"][metric_index - 2:metric_index + 1]
        ]
        taker_ratio = statistics.median(taker_values)
        flow_aligned = (
            taker_ratio >= 1.02
            if side == "LONG"
            else taker_ratio <= (1.0 / 1.02)
        )
        flow_opposed = (
            taker_ratio <= (1.0 / 1.02)
            if side == "LONG"
            else taker_ratio >= 1.02
        )

        funding_start = max(0, funding_index - funding_window + 1)
        funding_values = [
            float(item["funding_rate"])
            for item in data["funding"][funding_start:funding_index + 1]
        ]
        premium_start = max(0, premium_index - premium_window + 1)
        premium_values = [
            float(item["close"])
            for item in data["premium"][premium_start:premium_index + 1]
        ]
        funding_z = _zscore(funding_values)
        premium_z = _zscore(premium_values)
        if funding_z is None or premium_z is None:
            return result
        crowding_veto = (
            funding_z > 1.5 or premium_z > 2.0
            if side == "LONG"
            else funding_z < -1.5 or premium_z < -2.0
        )
        oi_rising = oi_change > 0
        score = (
            (1 if oi_rising else -1)
            + (1 if flow_aligned else -1 if flow_opposed else 0)
        )
        if score >= 2:
            weight = 1.10
        elif score == 1:
            weight = 1.05
        elif score == 0:
            weight = 0.95
        else:
            weight = 0.80
        if crowding_veto:
            weight = min(weight, 0.75)

        result.update({
            "derivatives_complete": True,
            "derivatives_observed_at": observed_at,
            "oi_change_12h": oi_change,
            "taker_ratio_3h": taker_ratio,
            "flow_aligned": flow_aligned,
            "funding_z": funding_z,
            "premium_z": premium_z,
            "crowding_veto": crowding_veto,
            "oi_flow_score": score,
            "oi_soft_weight": weight,
            "oi_hard_confirmed": (
                oi_rising
                and flow_aligned
                and not crowding_veto
            ),
        })
        return result


def attach_context(records, database):
    attached = []
    with DerivativesResolver(database) as resolver:
        available = set(resolver.symbols())
        for record in records:
            item = dict(record)
            if item["pair"] in available:
                context = resolver.context(
                    item["pair"],
                    int(item["signal_time"]),
                    item["side"],
                )
            else:
                context = {
                    "derivatives_complete": False,
                    "derivatives_observed_at": None,
                    "oi_change_12h": None,
                    "taker_ratio_3h": None,
                    "flow_aligned": None,
                    "funding_z": None,
                    "premium_z": None,
                    "crowding_veto": None,
                    "oi_flow_score": None,
                    "oi_soft_weight": 1.0,
                    "oi_hard_confirmed": False,
                }
            item.update(context)
            if context["derivatives_complete"]:
                value = float(item["net_R_live"])
                stress = float(item["net_R_live_cost_0_20"])
                item["net_R_oi_soft"] = (
                    value * float(context["oi_soft_weight"])
                )
                item["net_R_oi_soft_cost_0_20"] = (
                    stress * float(context["oi_soft_weight"])
                )
            else:
                item["net_R_oi_soft"] = None
                item["net_R_oi_soft_cost_0_20"] = None
            attached.append(item)
    return attached


def validate_context(context):
    if not context.get("derivatives_complete"):
        return False
    numeric = (
        context.get("oi_change_12h"),
        context.get("taker_ratio_3h"),
        context.get("funding_z"),
        context.get("premium_z"),
        context.get("oi_soft_weight"),
    )
    return all(
        value is not None and math.isfinite(float(value))
        for value in numeric
    )
