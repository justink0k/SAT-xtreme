"""Search for the best OPV in steps, for houses where the boiler gives no plateau to learn from.

When the house takes less heat than the boiler gives at its minimum power, the flow keeps rising in every
burn until the boiler switches off, and the OPV is no longer a measurable balance but a choice: a lower OPV
gives shorter burns at a lower flow, a higher OPV longer burns and fewer starts. This search tries a step,
keeps it for a period and compares:

- the score: heating starts per degree hour (an hour with 1 °C between the target and the outside
  temperature), lower is better;
- the comfort, only in stable hours (the target unchanged for at least 3 hours, heating on): the room may not
  be too cold on average, and the spread around the target may not grow clearly.

A step down is kept when the score is not clearly worse (a lower flow is a bonus); a step up only when the
score is clearly better. A real plateau sample always wins: it ends the search and starts it again later.
With the learned OPV in "learn" mode nothing changes: the search only measures and shows the step it would take.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from math import sqrt
from typing import Any, Callable, Optional

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

STEP = 1.0
PERIOD_SECONDS = 48 * 3600
NO_PLATEAU_SECONDS = 3 * 24 * 3600
REST_SECONDS = 7 * 24 * 3600

# How much worse a step down may be, and how much better a step up must be
SCORE_TOLERANCE = 0.15

# Comfort, measured only in stable hours
STABLE_TARGET_SECONDS = 3 * 3600
MAXIMUM_COLD = 0.5
MAXIMUM_SPREAD_GROWTH = 0.5
MINIMUM_SPREAD_INCREASE = 0.1
# The "too cold" abort during a trial waits for at least this many stable seconds
MINIMUM_COLD_CHECK_SECONDS = 3600

# A period only counts with enough data; otherwise it is extended
MINIMUM_STARTS = 20
MINIMUM_STABLE_SECONDS = 12 * 3600

# Longer gaps between two updates (for example a restart) are not counted
MAXIMUM_GAP_SECONDS = 300

PHASE_WAITING = "waiting"
PHASE_BASELINE = "baseline"
PHASE_DOWN = "down"
PHASE_UP = "up"
PHASE_REST = "rest"


@dataclass(frozen=True, slots=True)
class SearchSample:
    """What the search needs from one control loop."""
    time: float
    heating: bool
    flame: bool
    hot_water: bool
    target: Optional[float]
    current: Optional[float]
    outside: Optional[float]
    gas: Optional[float] = None


class Period:
    """The numbers of one measuring period."""

    def __init__(self, start: float, gas: Optional[float] = None) -> None:
        self.start = start
        self.starts = 0
        self.degree_hours = 0.0
        self.stable_seconds = 0.0
        self.error_sum = 0.0
        self.error_square_sum = 0.0
        self.gas_start = gas
        self.gas_last = gas

    @property
    def score(self) -> Optional[float]:
        return self.starts / self.degree_hours if self.degree_hours > 0 else None

    @property
    def mean_error(self) -> Optional[float]:
        return self.error_sum / self.stable_seconds if self.stable_seconds > 0 else None

    @property
    def spread(self) -> Optional[float]:
        if self.stable_seconds <= 0:
            return None

        mean = self.mean_error
        return sqrt(max(0.0, self.error_square_sum / self.stable_seconds - mean * mean))

    @property
    def gas_per_degree_hour(self) -> Optional[float]:
        if self.gas_start is None or self.gas_last is None or self.degree_hours <= 0:
            return None

        return (self.gas_last - self.gas_start) / self.degree_hours

    def complete(self, now: float) -> bool:
        return (
                now - self.start >= PERIOD_SECONDS
                and self.starts >= MINIMUM_STARTS
                and self.stable_seconds >= MINIMUM_STABLE_SECONDS
                and self.score is not None
        )

    def result(self) -> dict[str, Any]:
        return {"score": self.score, "spread": self.spread, "mean_error": self.mean_error}

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Period:
        period = Period(float(data["start"]))
        for key, value in data.items():
            setattr(period, key, value)

        return period


def _timestamp(value: Optional[float]) -> Optional[str]:
    """A Unix time as a local date and time, which Home Assistant shows as a date."""
    return dt_util.as_local(dt_util.utc_from_timestamp(value)).isoformat(timespec="seconds") if value is not None else None


def _round(value: Optional[float], digits: int = 3) -> Optional[float]:
    return round(value, digits) if value is not None else None


class OpvSearch:
    """The state machine of the search; the learned OPV adds `offset` to its value when it is applied."""

    def __init__(self, enabled: bool, applied: bool, allowed: Callable[[float], bool]) -> None:
        self.enabled = enabled
        self._applied = applied
        # Whether an offset still changes the OPV within its limits
        self._allowed = allowed

        self.phase: str = PHASE_WAITING
        self.offset: float = 0.0
        self._best: float = 0.0
        self._moved_down: bool = False
        self._last_plateau: Optional[float] = None
        self._rest_until: Optional[float] = None
        self._baseline: Optional[dict[str, Any]] = None
        self._trial: Optional[dict[str, Any]] = None
        self._period: Optional[Period] = None

        self._previous_time: Optional[float] = None
        self._previous_flame: Optional[bool] = None
        self._target: Optional[float] = None
        self._target_since: Optional[float] = None
        self._last_decision: Optional[str] = None
        self.changed: bool = False

    @property
    def applied_offset(self) -> float:
        """The offset that changes the OPV: only when the search is on and the learned OPV is applied."""
        return self.offset if self.enabled and self._applied else 0.0

    @property
    def would_try(self) -> Optional[float]:
        """In "learn" mode: the offset the search would try next."""
        if not self.enabled or self._applied or self.phase != PHASE_BASELINE or self._baseline is None:
            return None

        return self._next_down() if self._next_down() is not None else self._next_up()

    def attributes(self, value_with: Callable[[float], float]) -> dict[str, Any]:
        if not self.enabled:
            return {"search_phase": None}

        period = self._period
        would_try = self.would_try

        return {
            "search_phase": self.phase,
            "search_value": value_with(self.offset if self._applied else (would_try if would_try is not None else self.offset)),
            "search_offset": self.offset,
            "baseline_score": _round((self._baseline or {}).get("score")),
            "trial_score": _round((self._trial or {}).get("score")),
            "baseline_spread": _round((self._baseline or {}).get("spread")),
            "trial_spread": _round((self._trial or {}).get("spread")),
            "baseline_mean_error": _round((self._baseline or {}).get("mean_error")),
            "trial_mean_error": _round((self._trial or {}).get("mean_error")),
            "stable_hours": round(period.stable_seconds / 3600, 1) if period else None,
            "starts": period.starts if period else None,
            "next_decision": _timestamp(self._next_decision()),
            "last_decision": self._last_decision,
            "search_gas_per_degree_hour": _round(period.gas_per_degree_hour, 4) if period else None,
        }

    def _next_decision(self) -> Optional[float]:
        if self.phase == PHASE_WAITING and self._last_plateau is not None:
            return self._last_plateau + NO_PLATEAU_SECONDS

        if self.phase == PHASE_REST:
            return self._rest_until

        if self._period is not None:
            return self._period.start + PERIOD_SECONDS

        return None

    def on_plateau(self, now: float) -> None:
        """A real measurement: drop the trial step and start waiting again."""
        if self.offset or self.phase != PHASE_WAITING:
            _LOGGER.info("Xtreme profile: OPV plateau sample, the OPV search stops and starts again later.")

        self._reset(now)
        self._last_decision = "plateau"

    def _reset(self, now: float) -> None:
        self.phase = PHASE_WAITING
        self.offset = 0.0
        self._best = 0.0
        self._moved_down = False
        self._last_plateau = now
        self._baseline = None
        self._trial = None
        self._period = None
        self.changed = True

    def update(self, sample: SearchSample) -> None:
        """Process one control loop."""
        if not self.enabled:
            return

        now = sample.time
        if self._last_plateau is None:
            self._last_plateau = now
            self.changed = True

        self._accumulate(sample)

        if self.phase == PHASE_WAITING and now - self._last_plateau >= NO_PLATEAU_SECONDS:
            self._start_period(PHASE_BASELINE, now, sample.gas)
            self._decide("no plateau for 3 days, measuring the baseline")
        elif self.phase == PHASE_REST and self._rest_until is not None and now >= self._rest_until:
            self._last_plateau = now - NO_PLATEAU_SECONDS
            self._start_period(PHASE_BASELINE, now, sample.gas)
            self._decide("rest over, measuring the baseline again")
        elif self.phase in (PHASE_DOWN, PHASE_UP) and self._too_cold():
            self._fail(now, sample.gas, "too cold during the trial")
        elif self._period is not None and self._period.complete(now):
            self._end_period(now, sample.gas)

    def _accumulate(self, sample: SearchSample) -> None:
        now = sample.time
        dt = now - self._previous_time if self._previous_time is not None else 0.0
        self._previous_time = now
        dt = dt if 0 < dt <= MAXIMUM_GAP_SECONDS else 0.0

        if sample.target != self._target:
            self._target = sample.target
            self._target_since = now

        period = self._period
        flame_started = sample.flame and self._previous_flame is False
        self._previous_flame = sample.flame

        if period is None:
            return

        if sample.gas is not None:
            if period.gas_start is None:
                period.gas_start = sample.gas
            period.gas_last = sample.gas

        if flame_started and sample.heating and not sample.hot_water:
            period.starts += 1

        if not sample.heating or dt <= 0:
            return

        if sample.target is not None and sample.outside is not None:
            period.degree_hours += max(0.0, sample.target - sample.outside) * dt / 3600

        stable = self._target_since is not None and now - self._target_since >= STABLE_TARGET_SECONDS
        if stable and sample.target is not None and sample.current is not None:
            error = sample.current - sample.target
            period.stable_seconds += dt
            period.error_sum += error * dt
            period.error_square_sum += error * error * dt

    def _too_cold(self) -> bool:
        period = self._period
        return (
                period is not None
                and period.stable_seconds >= MINIMUM_COLD_CHECK_SECONDS
                and period.mean_error is not None
                and period.mean_error < -MAXIMUM_COLD
        )

    def _start_period(self, phase: str, now: float, gas: Optional[float]) -> None:
        self.phase = phase
        self._period = Period(now, gas)
        self.changed = True

    def _decide(self, reason: str) -> None:
        self._last_decision = reason
        self.changed = True
        _LOGGER.info("Xtreme profile: OPV search %s: %s (offset %+.0f°C).", self.phase, reason, self.offset)

    def _next_down(self) -> Optional[float]:
        candidate = self._best - STEP
        return candidate if self._allowed(candidate) else None

    def _next_up(self) -> Optional[float]:
        candidate = self._best + STEP
        return candidate if self._allowed(candidate) else None

    def _comfort_problem(self, trial: dict[str, Any]) -> Optional[str]:
        if trial["mean_error"] is not None and trial["mean_error"] < -MAXIMUM_COLD:
            return "too cold"

        base, spread = self._baseline.get("spread"), trial["spread"]
        if base is not None and spread is not None and spread > base * (1 + MAXIMUM_SPREAD_GROWTH) and spread - base >= MINIMUM_SPREAD_INCREASE:
            return "temperature less steady"

        return None

    def _end_period(self, now: float, gas: Optional[float]) -> None:
        result = self._period.result()

        if self.phase == PHASE_BASELINE:
            self._baseline = result
            self._trial = None

            # In "learn" mode the search cannot try a step: keep measuring and show the step it would take
            if not self._applied:
                self._start_period(PHASE_BASELINE, now, gas)
                self._decide("baseline measured; in learn mode the step is only shown")
                return

            self._try_down_or_up(now, gas)
            return

        self._trial = result
        problem = self._comfort_problem(result)

        if self.phase == PHASE_DOWN:
            if problem is None and result["score"] <= self._baseline["score"] * (1 + SCORE_TOLERANCE):
                self._accept(now, gas, "step down kept")
                self._moved_down = True
                self._try_down(now, gas) or self._rest(now, "lowest value reached")
            else:
                self._fail(now, gas, problem or "more starts after the step down")
            return

        if problem is None and result["score"] <= self._baseline["score"] * (1 - SCORE_TOLERANCE):
            self._accept(now, gas, "step up kept")
            self._try_up(now, gas) or self._rest(now, "highest value reached")
        else:
            self._fail(now, gas, problem or "no clear gain after the step up")

    def _accept(self, now: float, gas: Optional[float], reason: str) -> None:
        self._best = self.offset
        self._baseline = self._trial
        self._decide(reason)

    def _fail(self, now: float, gas: Optional[float], reason: str) -> None:
        phase = self.phase
        self.offset = self._best
        self._decide(f"step back: {reason}")

        # After a failed step down, try once up, unless the search already went down from there
        if phase == PHASE_DOWN and not self._moved_down and self._try_up(now, gas):
            return

        self._rest(now, "no better value found")

    def _try_down_or_up(self, now: float, gas: Optional[float]) -> None:
        if not self._try_down(now, gas) and not self._try_up(now, gas):
            self._rest(now, "no step possible within the limits")

    def _try_down(self, now: float, gas: Optional[float]) -> bool:
        if (candidate := self._next_down()) is None:
            return False

        self.offset = candidate
        self._start_period(PHASE_DOWN, now, gas)
        self._decide("trying a step down")
        return True

    def _try_up(self, now: float, gas: Optional[float]) -> bool:
        if (candidate := self._next_up()) is None:
            return False

        self.offset = candidate
        self._start_period(PHASE_UP, now, gas)
        self._decide("trying a step up")
        return True

    def _rest(self, now: float, reason: str) -> bool:
        self.phase = PHASE_REST
        self._rest_until = now + REST_SECONDS
        self._period = None
        self._decide(reason)
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "offset": self.offset,
            "best": self._best,
            "moved_down": self._moved_down,
            "last_plateau": self._last_plateau,
            "rest_until": self._rest_until,
            "baseline": self._baseline,
            "trial": self._trial,
            "period": self._period.to_dict() if self._period else None,
            "last_decision": self._last_decision,
        }

    def load(self, data: Optional[dict[str, Any]]) -> None:
        if not data:
            return

        self.phase = data.get("phase", PHASE_WAITING)
        self.offset = float(data.get("offset", 0.0))
        self._best = float(data.get("best", 0.0))
        self._moved_down = bool(data.get("moved_down", False))
        self._last_plateau = data.get("last_plateau")
        self._rest_until = data.get("rest_until")
        self._baseline = data.get("baseline")
        self._trial = data.get("trial")
        self._period = Period.from_dict(data["period"]) if data.get("period") else None
        self._last_decision = data.get("last_decision")
