import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from homeassistant.util import utcnow


@dataclass(frozen=True, slots=True)
class State:
    value: Optional[float] = None
    last_changed: datetime = field(default_factory=utcnow)


def update_state(previous: State, new_value: float, tolerance=1e-3) -> State:
    """
    Return a new State if the value changed beyond tolerance; otherwise return the existing one.
    Always timezone-aware and safe for float comparisons.
    """
    # Xtreme fork: a value that is missing (not arrived yet after a start-up) keeps the previous one
    if new_value is None:
        return previous

    if previous.value is not None and math.isclose(previous.value, new_value, abs_tol=tolerance):
        # No significant change → preserve timestamp
        return previous

    # Changed or first assignment → create new State
    return State(value=new_value, last_changed=utcnow())
