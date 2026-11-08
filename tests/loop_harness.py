"""Test helpers that record what SAT really sends, so a test can run control loops and check the commands.

Two levels:
- CommandLog records what the climate asks the coordinator (setpoint, heater state, modulation, hand-over).
- ServiceCallLog records the Home Assistant service calls that leave SAT (switch and ESPHome gateways), and the
  OpenTherm Gateway tests patch `_publish_command` for the commands on the wire.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, callback

COMMANDS = {
    "async_set_control_setpoint": "setpoint",
    "async_set_heater_state": "heater",
    "async_set_control_max_relative_modulation": "modulation",
    "async_set_control_max_setpoint": "maximum_setpoint",
    "async_set_control_hot_water_setpoint": "hot_water_setpoint",
    "async_set_control_thermostat_setpoint": "thermostat_setpoint",
    "async_release_control_setpoint": "release",
    "async_set_hot_water_keep_warm": "keep_warm",
}


class CommandLog:
    """Record every command the climate sends to the coordinator, and pass it on unchanged."""

    def __init__(self, coordinator: Any) -> None:
        self._coordinator = coordinator
        self.sent: list[tuple[str, Any]] = []

        for method, name in COMMANDS.items():
            original = getattr(coordinator, method)
            setattr(coordinator, method, self._wrap(name, original))

    def _wrap(self, name: str, original: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        async def wrapper(*args, **kwargs) -> None:
            self.sent.append((name, args[0] if args else None))
            await original(*args, **kwargs)

        return wrapper

    def close(self) -> None:
        """Remove the wrappers from the coordinator."""
        for method in COMMANDS:
            self._coordinator.__dict__.pop(method, None)

    def of(self, name: str) -> list[Any]:
        """The values of one kind of command, in order."""
        return [value for kind, value in self.sent if kind == name]

    def clear(self) -> None:
        self.sent.clear()

    def __enter__(self) -> CommandLog:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


class ServiceCallLog:
    """Record the service calls made in Home Assistant, for gateways that are controlled with entities."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.calls: list[tuple[str, str, Optional[str]]] = []
        self._unsub = hass.bus.async_listen(EVENT_CALL_SERVICE, self._called)

    @callback
    def _called(self, event: Event) -> None:
        data = event.data.get("service_data", {})
        entity_id = data.get("entity_id")
        if isinstance(entity_id, list):
            entity_id = entity_id[0] if entity_id else None

        self.calls.append((event.data["domain"], event.data["service"], entity_id))

    def services(self, entity_id: str) -> list[str]:
        """The services called for one entity, in order."""
        return [service for _, service, called in self.calls if called == entity_id]

    def close(self) -> None:
        self._unsub()

    def __enter__(self) -> ServiceCallLog:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


async def run_loops(climate: Any, count: int, between: Optional[Callable[[int], Awaitable[None] | None]] = None) -> None:
    """Run the control loop of the climate `count` times; `between` runs before each loop (for example to move a clock)."""
    for index in range(count):
        if between is not None and (result := between(index)) is not None:
            await result

        await climate.async_control_heating_loop()
