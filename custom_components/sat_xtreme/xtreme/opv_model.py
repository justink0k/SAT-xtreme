"""Choose the OPV from a model of the burn, for houses where the boiler gives no plateau to learn from.

When the house takes less heat than the boiler gives at its minimum power, the flow rises in every burn until
the boiler switches itself off a little above the OPV. The OPV then decides how long a burn lasts: the heat a
house needs per day does not depend on it, so longer burns mean fewer starts.

The model is the typical heating curve of a burn in this house: for every whole degree, the median time from
ignition until the flow reached it, over the heating burns of the last 7 days. Above the highest measured
degree the curve is extended for at most 3 °C, with a flow that approaches a balance temperature (the real
OPV) when the curve flattens. The burn time at an OPV is the time the curve needs to reach the OPV plus the
point where this boiler normally switches itself off.

The choice is the lowest OPV at which a burn lasts at least the minimum burn time of boiler timing. The model
only chooses when it applies (most heating burns end with the boiler switching itself off, most heating time is
in PWM, there is a flow temperature, no heat pump) and when it predicts the real burns well enough. It changes
the OPV at most 1 °C per day, only with the learned OPV on "apply", and goes back when the comfort gets worse.

The idea of tracking burns comes from the closed upstream pull request Alexwijn/SAT#124 (GPL-3.0); this module
is written for the fork and takes no code from it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from math import ceil, floor, inf, log, sqrt
from statistics import median
from typing import Any, Callable, Optional

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

WINDOW_SECONDS = 7 * 24 * 3600
MINIMUM_BURNS = 30
MINIMUM_BURN_SECONDS = 60
MAXIMUM_BURNS = 2000

# A degree belongs to the measured curve when at least 80 % of the burns that started below it reached it
LEVEL_REACHED_SHARE = 0.8
LEVEL_MINIMUM_BURNS = 10
EXTRAPOLATION_LEVELS = 5
MAXIMUM_EXTRAPOLATION = 3.0

# When the model applies
MINIMUM_SELF_SHUT_OFF_SHARE = 0.6
MINIMUM_PWM_SHARE = 0.5

# How well the model must predict the real burns: the median error over the last 24 hours
MAXIMUM_ERROR = 0.20
ERROR_WINDOW_SECONDS = 24 * 3600
MINIMUM_ERRORS = 5

# Changes and comfort
CHANGE_INTERVAL_SECONDS = 24 * 3600
COMFORT_SECONDS = 48 * 3600
BLOCK_SECONDS = 7 * 24 * 3600
STABLE_TARGET_SECONDS = 3 * 3600
MAXIMUM_COLD = 0.5
MINIMUM_COLD_CHECK_SECONDS = 3600
MAXIMUM_SPREAD_GROWTH = 0.5
MINIMUM_SPREAD_INCREASE = 0.1

# The action to try another OPV
TEST_MAXIMUM_OFFSET = 3
TEST_MAXIMUM_HOURS = 72

MAXIMUM_GAP_SECONDS = 300
HOT_WATER_QUIET_SECONDS = 300.0

STATUS_COLLECTING = "collecting"
STATUS_ACTIVE = "active"
STATUS_POOR_FIT = "poor_fit"
STATUS_CONTINUOUS = "not_applicable_continuous"
STATUS_NO_SELF_SHUT_OFF = "not_applicable_no_self_shut_off"
STATUS_NO_FLOW = "not_applicable_no_flow_temperature"
STATUS_HEAT_PUMP = "not_applicable_heat_pump"


@dataclass(frozen=True, slots=True)
class ModelSample:
    """What the model needs from one control loop."""
    time: float
    heating: bool
    flame: bool
    hot_water: bool
    seconds_since_hot_water: Optional[float]
    heating_demand: bool
    flow: Optional[float]
    setpoint: Optional[float]
    pwm: bool
    target: Optional[float]
    current: Optional[float]
    outside: Optional[float] = None
    gas: Optional[float] = None


def _timestamp(value: Optional[float]) -> Optional[str]:
    return dt_util.as_local(dt_util.utc_from_timestamp(value)).isoformat(timespec="seconds") if value is not None else None


def _round(value: Optional[float], digits: int = 1) -> Optional[float]:
    return round(value, digits) if value is not None and value != inf else value


class Curve:
    """The median heating curve of the recent burns: seconds from ignition per whole degree."""

    def __init__(self, burns: list[dict[str, Any]]) -> None:
        self.levels: dict[int, float] = {}
        self.balance: Optional[float] = None
        self._rate: Optional[float] = None
        self._k: Optional[float] = None

        if not burns:
            return

        lowest = min(floor(burn["t0"]) + 1 for burn in burns)
        highest = max(int(level) for burn in burns for level in burn["crossings"]) if any(burn["crossings"] for burn in burns) else lowest

        for level in range(lowest, highest + 1):
            started_below = [burn for burn in burns if burn["t0"] < level]
            times = [burn["crossings"][str(level)] for burn in started_below if str(level) in burn["crossings"]]
            if len(times) < LEVEL_MINIMUM_BURNS or len(times) < LEVEL_REACHED_SHARE * len(started_below):
                if self.levels:
                    break
                continue

            # The curve may not go back in time
            value = median(times)
            if self.levels:
                value = max(value, self.levels[max(self.levels)])
            self.levels[level] = value

        self._fit_tail()

    @property
    def top(self) -> Optional[int]:
        return max(self.levels) if self.levels else None

    def _fit_tail(self) -> None:
        """Fit the rise of the last degrees: rate = a - k * flow; the flow approaches a / k."""
        levels = sorted(self.levels)[-(EXTRAPOLATION_LEVELS + 1):]
        points = []
        for low, high in zip(levels, levels[1:]):
            seconds = self.levels[high] - self.levels[low]
            if seconds > 0:
                points.append((low + 0.5, 1.0 / seconds))

        if not points:
            return

        self._rate = points[-1][1]
        if len(points) < 3:
            return

        mean_t = sum(t for t, _ in points) / len(points)
        mean_r = sum(r for _, r in points) / len(points)
        variance = sum((t - mean_t) ** 2 for t, _ in points)
        if variance <= 0:
            return

        slope = sum((t - mean_t) * (r - mean_r) for t, r in points) / variance
        if slope >= 0:
            return

        k = -slope
        balance = (mean_r + k * mean_t) / k
        if balance > self.top:
            self._k = k
            self.balance = balance

    def seconds_to(self, temperature: float) -> Optional[float]:
        """Seconds from ignition until the flow reaches the temperature; inf when it never does; None when unknown."""
        if not self.levels:
            return None

        levels = sorted(self.levels)
        if temperature <= levels[0]:
            return self.levels[levels[0]]

        top = levels[-1]
        if temperature <= top:
            low = floor(temperature)
            high = low + 1
            if high not in self.levels:
                return self.levels[low]
            return self.levels[low] + (temperature - low) * (self.levels[high] - self.levels[low])

        if temperature > top + MAXIMUM_EXTRAPOLATION:
            return None

        if self._k is not None and self.balance is not None:
            if temperature >= self.balance:
                return inf
            return self.levels[top] + log((self.balance - top) / (self.balance - temperature)) / self._k

        if self._rate:
            return self.levels[top] + (temperature - top) / self._rate

        return None


class OpvModel:
    """Learns the heating curve of the burns and chooses the OPV from it."""

    def __init__(self, enabled: bool, applied: bool, heat_pump: bool, minimum_burn_seconds: float,
                 limits: Callable[[], tuple[float, float]]) -> None:
        self.enabled = enabled
        self._applied = applied
        self._heat_pump = heat_pump
        self._minimum_burn_seconds = float(minimum_burn_seconds)
        # The lowest and highest OPV allowed (the lowest learned OPV, and 55 °C or the maximum setpoint)
        self._limits = limits

        self._burns: list[dict[str, Any]] = []
        self._errors: list[tuple[float, float]] = []
        self._days: dict[str, list[float]] = {}
        self._hours: dict[str, list[float]] = {}

        self.applied_value: Optional[float] = None
        self._previous_value: Optional[float] = None
        self._changed_at: Optional[float] = None
        self._next_change: Optional[float] = None
        self._blocked: dict[str, float] = {}

        self.test_offset: float = 0.0
        self._test: Optional[dict[str, Any]] = None
        self._last_test: Optional[dict[str, Any]] = None

        self._burn: Optional[dict[str, Any]] = None
        self._previous_flame: Optional[bool] = None
        self._previous_time: Optional[float] = None
        self._previous_flow: Optional[float] = None
        self._previous_gas: Optional[float] = None
        self._target: Optional[float] = None
        self._target_since: Optional[float] = None
        self._no_flow: bool = False
        self._last_decision: Optional[str] = None
        self._curve: Optional[Curve] = None
        self.changed: bool = False

    # Status and prediction

    def _recent(self, now: float) -> list[dict[str, Any]]:
        return [burn for burn in self._burns if burn["end"] >= now - WINDOW_SECONDS]

    def curve(self, now: float) -> Curve:
        if self._curve is None:
            self._curve = Curve(self._recent(now))
        return self._curve

    def shut_off_offset(self, now: float) -> float:
        """Where this boiler normally switches itself off, as flow minus setpoint."""
        offsets = [burn["end_flow"] - burn["setpoint"] for burn in self._recent(now) if burn["self"] and burn["setpoint"] is not None]
        return median(offsets) if offsets else 0.0

    def predict(self, opv: float, now: float) -> Optional[float]:
        return self.curve(now).seconds_to(opv + self.shut_off_offset(now))

    def pwm_share(self, now: float) -> Optional[float]:
        days = [value for key, value in self._days.items() if float(key) >= now - WINDOW_SECONDS]
        heating = sum(day[0] for day in days)
        return sum(day[1] for day in days) / heating if heating > 0 else None

    def self_shut_off_share(self, now: float) -> Optional[float]:
        burns = self._recent(now)
        return sum(1 for burn in burns if burn["self"]) / len(burns) if burns else None

    def error(self, now: float) -> Optional[float]:
        errors = [value for time, value in self._errors if time >= now - ERROR_WINDOW_SECONDS]
        return median(errors) if len(errors) >= MINIMUM_ERRORS else None

    def status(self, now: float) -> str:
        if self._heat_pump:
            return STATUS_HEAT_PUMP
        if self._no_flow:
            return STATUS_NO_FLOW
        if len(self._recent(now)) < MINIMUM_BURNS:
            return STATUS_COLLECTING
        if (share := self.self_shut_off_share(now)) is not None and share < MINIMUM_SELF_SHUT_OFF_SHARE:
            return STATUS_NO_SELF_SHUT_OFF
        if (share := self.pwm_share(now)) is not None and share < MINIMUM_PWM_SHARE:
            return STATUS_CONTINUOUS
        if (error := self.error(now)) is None:
            return STATUS_COLLECTING
        if error > MAXIMUM_ERROR:
            return STATUS_POOR_FIT
        return STATUS_ACTIVE

    def choice(self, now: float) -> Optional[float]:
        """The lowest OPV with a predicted burn of at least the minimum burn time, within the limits."""
        low, high = self._limits()
        best = None

        for opv in range(ceil(low), floor(high) + 1):
            if self._blocked.get(str(opv), 0) > now:
                continue

            seconds = self.predict(opv, now)
            if seconds is None:
                continue
            if seconds >= self._minimum_burn_seconds:
                return float(opv)
            best = float(opv)

        return best

    def attributes(self, current_opv: float) -> dict[str, Any]:
        if not self.enabled:
            return {"model_status": None}

        now = _now()
        curve = self.curve(now)
        predictions = {}
        for offset in (-1, 0, 1):
            seconds = self.predict(current_opv + offset, now)
            # "never": the flow does not reach the shut-off point, the burn lasts until PWM ends it
            predictions[f"{offset:+d}"] = "never" if seconds == inf else _round(seconds, 0)

        return {
            "model_status": self.status(now),
            "model_burns": len(self._recent(now)),
            "model_choice": self.choice(now),
            "model_value": self.applied_value,
            "predicted_burn_seconds": predictions,
            "minimum_burn_seconds": self._minimum_burn_seconds,
            "model_error": _round(self.error(now), 3),
            "balance_temperature": _round(curve.balance),
            "curve_top": curve.top,
            "self_shut_off_share": _round(self.self_shut_off_share(now), 2),
            "pwm_share": _round(self.pwm_share(now), 2),
            "next_change": _timestamp(self._next_change),
            "last_decision": self._last_decision,
            "test": self._test_attributes(self._test) if self._test else None,
            "last_test": self._test_attributes(self._last_test) if self._last_test else None,
            "gas_per_degree_hour": _round(self.gas_per_degree_hour(now), 4),
        }

    @staticmethod
    def _test_attributes(test: dict[str, Any]) -> dict[str, Any]:
        actual = median(test["burns"]) if test["burns"] else None
        return {
            "offset": test["offset"],
            "until": _timestamp(test["until"]),
            "predicted_seconds": "never" if test["predicted"] == inf else _round(test["predicted"], 0),
            "actual_seconds": _round(actual, 0),
            "burns": len(test["burns"]),
        }

    def gas_per_degree_hour(self, now: float) -> Optional[float]:
        days = [value for key, value in self._days.items() if float(key) >= now - WINDOW_SECONDS]
        degree_hours = sum(day[2] for day in days)
        gas = sum(day[3] for day in days)
        return gas / degree_hours if degree_hours > 0 and gas > 0 else None

    # Updates

    def update(self, sample: ModelSample, base_value: float) -> None:
        """Process one control loop; base_value is the learned OPV without the model."""
        if not self.enabled:
            return

        now = sample.time
        dt = now - self._previous_time if self._previous_time is not None else 0.0
        dt = dt if 0 < dt <= MAXIMUM_GAP_SECONDS else 0.0
        self._previous_time = now

        self._accumulate(sample, dt)
        self._follow_burn(sample)
        self._check_test(now)

        if self._applied and self._test is None:
            self._control(now, base_value)

    def _accumulate(self, sample: ModelSample, dt: float) -> None:
        now = sample.time
        if sample.target != self._target:
            self._target = sample.target
            self._target_since = now

        if sample.flame:
            self._no_flow = sample.flow is None

        gas_used = 0.0
        if sample.gas is not None:
            if self._previous_gas is not None and 0 < sample.gas - self._previous_gas < 1:
                gas_used = sample.gas - self._previous_gas
            self._previous_gas = sample.gas

        if dt <= 0 or not sample.heating:
            return

        day = self._days.setdefault(str(float(int(now // 86400) * 86400)), [0.0, 0.0, 0.0, 0.0])
        day[0] += dt
        if sample.pwm:
            day[1] += dt
        if sample.target is not None and sample.outside is not None:
            day[2] += max(0.0, sample.target - sample.outside) * dt / 3600
        day[3] += gas_used

        stable = self._target_since is not None and now - self._target_since >= STABLE_TARGET_SECONDS
        if stable and sample.target is not None and sample.current is not None:
            error = sample.current - sample.target
            hour = self._hours.setdefault(str(float(int(now // 3600) * 3600)), [0.0, 0.0, 0.0])
            hour[0] += dt
            hour[1] += error * dt
            hour[2] += error * error * dt

        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS - 86400
        self._days = {key: value for key, value in self._days.items() if float(key) >= cutoff}
        self._hours = {key: value for key, value in self._hours.items() if float(key) >= cutoff}

    def _follow_burn(self, sample: ModelSample) -> None:
        now = sample.time
        quiet = not sample.hot_water and (sample.seconds_since_hot_water is None or sample.seconds_since_hot_water >= HOT_WATER_QUIET_SECONDS)
        previous, self._previous_flame = self._previous_flame, sample.flame

        if previous is None:
            return

        if sample.flame and not previous:
            self._burn = {"start": now, "t0": sample.flow, "crossings": {}, "end_flow": sample.flow, "heating": quiet and sample.heating_demand, "setpoint": sample.setpoint}
            self._previous_flow = sample.flow
            return

        burn = self._burn
        if burn is None:
            return

        if sample.flame:
            if not quiet:
                burn["heating"] = False
            if sample.setpoint is not None:
                burn["setpoint"] = sample.setpoint
            if sample.flow is not None:
                if burn["t0"] is None:
                    burn["t0"] = sample.flow
                    burn["end_flow"] = sample.flow
                self._cross(burn, now, sample.flow)
            return

        # The flame went out; the flow it reports now is where the boiler switched off
        self._burn = None
        if sample.flow is not None and burn["t0"] is not None:
            self._cross(burn, now, sample.flow)
        duration = now - burn["start"]
        if not burn["heating"] or burn["t0"] is None or duration < MINIMUM_BURN_SECONDS:
            return

        record = {
            "end": now,
            "duration": duration,
            "t0": burn["t0"],
            "end_flow": burn["end_flow"],
            "setpoint": burn["setpoint"],
            "self": bool(sample.heating_demand and quiet),
            "crossings": burn["crossings"],
        }

        # How well did the model predict this burn, from the burns before it?
        if record["self"] and record["setpoint"] is not None:
            predicted = self.predict(record["setpoint"], now)
            if predicted is not None and predicted != inf:
                self._errors.append((now, abs(predicted - duration) / duration))
                self._errors = [item for item in self._errors if item[0] >= now - ERROR_WINDOW_SECONDS]

        if self._test is not None and record["self"]:
            self._test["burns"].append(duration)

        self._burns = (self._burns + [record])[-MAXIMUM_BURNS:]
        self._burns = [item for item in self._burns if item["end"] >= now - WINDOW_SECONDS]
        self._curve = None
        self.changed = True

    def _cross(self, burn: dict[str, Any], now: float, flow: float) -> None:
        """Note when the flow first reached every whole degree, interpolated between two readings."""
        previous_flow = self._previous_flow if self._previous_flow is not None else flow
        previous_time = burn.get("last_time", burn["start"])

        if flow > previous_flow:
            for level in range(floor(previous_flow) + 1, floor(flow) + 1):
                key = str(level)
                if key not in burn["crossings"] and level > burn["t0"]:
                    share = (level - previous_flow) / (flow - previous_flow)
                    burn["crossings"][key] = round(previous_time + share * (now - previous_time) - burn["start"], 1)

        burn["end_flow"] = max(burn["end_flow"], flow) if burn["end_flow"] is not None else flow
        burn["last_time"] = now
        self._previous_flow = flow

    def _comfort(self, start: float, end: float) -> dict[str, Optional[float]]:
        hours = [value for key, value in self._hours.items() if start <= float(key) < end]
        seconds = sum(hour[0] for hour in hours)
        if seconds <= 0:
            return {"seconds": 0.0, "mean": None, "spread": None}

        mean = sum(hour[1] for hour in hours) / seconds
        spread = sqrt(max(0.0, sum(hour[2] for hour in hours) / seconds - mean * mean))
        return {"seconds": seconds, "mean": mean, "spread": spread}

    def _control(self, now: float, base_value: float) -> None:
        if self.applied_value is None:
            self.applied_value = base_value

        # Watch the comfort after a change
        if self._changed_at is not None and now - self._changed_at <= COMFORT_SECONDS:
            after = self._comfort(self._changed_at, now + 3600)
            if after["seconds"] >= MINIMUM_COLD_CHECK_SECONDS and after["mean"] is not None and after["mean"] < -MAXIMUM_COLD:
                self._revert(now, "too cold after the change")
                return

            if now - self._changed_at >= COMFORT_SECONDS - 60:
                before = self._comfort(self._changed_at - COMFORT_SECONDS, self._changed_at)
                if (before["spread"] is not None and after["spread"] is not None
                        and after["spread"] > before["spread"] * (1 + MAXIMUM_SPREAD_GROWTH)
                        and after["spread"] - before["spread"] >= MINIMUM_SPREAD_INCREASE):
                    self._revert(now, "temperature less steady after the change")
                    return

        if self.status(now) != STATUS_ACTIVE or (self._next_change is not None and now < self._next_change):
            return

        if (choice := self.choice(now)) is None or choice == self.applied_value:
            return

        step = 1.0 if choice > self.applied_value else -1.0
        new_value = self.applied_value + step
        if self._blocked.get(str(int(round(new_value))), 0) > now:
            return

        self._previous_value = self.applied_value
        self.applied_value = new_value
        self._changed_at = now
        self._next_change = now + CHANGE_INTERVAL_SECONDS
        self._decide(f"OPV {self._previous_value:.0f} -> {new_value:.0f} °C, towards {choice:.0f} °C")

    def _revert(self, now: float, reason: str) -> None:
        bad = self.applied_value
        self.applied_value = self._previous_value
        self._blocked[str(int(round(bad)))] = now + BLOCK_SECONDS
        self._changed_at = None
        self._next_change = now + CHANGE_INTERVAL_SECONDS
        self._decide(f"back to {self.applied_value:.0f} °C: {reason}; {bad:.0f} °C blocked for 7 days")

    def _decide(self, reason: str) -> None:
        self._last_decision = reason
        self.changed = True
        _LOGGER.info("Xtreme profile: OPV model: %s.", reason)

    def on_plateau(self) -> None:
        """A real plateau sample: the learned value is used again."""
        if self.applied_value is not None:
            self.applied_value = None
            self._changed_at = None
            self._decide("plateau sample, the learned value is used again")

    # The action to try another OPV

    def start_test(self, offset: float, hours: float, opv: float) -> None:
        now = _now()
        offset = max(-TEST_MAXIMUM_OFFSET, min(TEST_MAXIMUM_OFFSET, round(offset)))
        hours = max(1.0, min(TEST_MAXIMUM_HOURS, hours))

        self.test_offset = float(offset)
        self._test = {"offset": offset, "until": now + hours * 3600, "predicted": self.predict(opv + offset, now), "burns": []}
        self._decide(f"test with the OPV {offset:+.0f} °C for {hours:.0f} hours")

    def _check_test(self, now: float) -> None:
        if self._test is not None and now >= self._test["until"]:
            self._last_test = self._test
            self._test = None
            self.test_offset = 0.0
            self._decide("test ended")

    # Storage

    def to_dict(self) -> dict[str, Any]:
        return {
            "burns": self._burns,
            "errors": self._errors,
            "days": self._days,
            "hours": self._hours,
            "applied_value": self.applied_value,
            "previous_value": self._previous_value,
            "changed_at": self._changed_at,
            "next_change": self._next_change,
            "blocked": self._blocked,
            "test": self._test,
            "test_offset": self.test_offset,
            "last_test": self._last_test,
            "last_decision": self._last_decision,
        }

    def load(self, data: Optional[dict[str, Any]]) -> None:
        if not data:
            return

        self._burns = list(data.get("burns", []))
        self._errors = [tuple(item) for item in data.get("errors", [])]
        self._days = dict(data.get("days", {}))
        self._hours = dict(data.get("hours", {}))
        self.applied_value = data.get("applied_value")
        self._previous_value = data.get("previous_value")
        self._changed_at = data.get("changed_at")
        self._next_change = data.get("next_change")
        self._blocked = dict(data.get("blocked", {}))
        self._test = data.get("test")
        self.test_offset = float(data.get("test_offset", 0.0))
        self._last_test = data.get("last_test")
        self._last_decision = data.get("last_decision")
        self._curve = None


def _now() -> float:
    return dt_util.utcnow().timestamp()
