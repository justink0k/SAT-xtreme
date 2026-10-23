"""Draw docs/images/pwm-block.svg: one PWM block with SAT 4.2.1 and with SAT-xtreme (setpoint priming).

The data are two blocks measured on the tested setup (Intergas Xtreme 30, OpenTherm Gateway, Nest on the bus)
on 21 October 2026. Times are seconds after the heating demand was turned on.

Usage: python dev/make_pwm_chart.py docs/images/pwm-block.svg
"""
import sys
from datetime import datetime
from pathlib import Path


def seconds(start: str, time: str) -> float:
    fmt = "%H:%M:%S"
    return (datetime.strptime(time, fmt) - datetime.strptime(start, fmt)).total_seconds()


# SAT 4.2.1: the setpoint is 10 °C in the pause and reaches the boiler only with the next message of the thermostat
UPSTREAM = {
    "title": "SAT 4.2.1",
    "demand": (0, seconds("09:32:50", "09:39:21")),
    "flame": (seconds("09:32:50", "09:34:56"), seconds("09:32:50", "09:39:26")),
    "setpoint": [(0, 10), (seconds("09:32:50", "09:34:53"), 10), (seconds("09:32:50", "09:34:53"), 46)],
    "note": "waiting for the setpoint: 2 min lost",
}

# SAT-xtreme with setpoint priming: the setpoint stays at 46 °C, only the heating demand changes
XTREME = {
    "title": "SAT-xtreme (setpoint priming)",
    "demand": (0, seconds("17:39:06", "17:49:40")),
    "flame": (seconds("17:39:06", "17:39:11"), seconds("17:39:06", "17:49:45")),
    "setpoint": [(0, 46)],
    "note": "flame after 5 s",
}

WIDTH, LEFT, RIGHT = 760, 150, 30
PANEL, GAP, TOP = 150, 40, 20
MINUTES = 11
SPAN = WIDTH - LEFT - RIGHT
SETPOINT_RANGE = (0, 60)


def x(t: float) -> float:
    return LEFT + SPAN * t / (MINUTES * 60)


def panel(data: dict, top: float) -> str:
    rows = {"demand": top + 30, "setpoint": top + 72, "flame": top + 120}
    end = MINUTES * 60
    parts = [f'<text class="title" x="{LEFT}" y="{top + 8}">{data["title"]}</text>']

    for key, label in (("demand", "Heating demand"), ("setpoint", "Setpoint (°C)"), ("flame", "Flame")):
        parts.append(f'<text class="label" x="{LEFT - 12}" y="{rows[key] + 4}" text-anchor="end">{label}</text>')

    for key in ("demand", "flame"):
        start, stop = data[key]
        y = rows[key]
        parts.append(f'<rect class="track" x="{x(0):.1f}" y="{y - 7}" width="{SPAN:.1f}" height="14" rx="3"/>')
        parts.append(f'<rect class="{key}" x="{x(start):.1f}" y="{y - 7}" width="{x(stop) - x(start):.1f}" height="14" rx="3"/>')

    low, high = SETPOINT_RANGE
    base = rows["setpoint"]

    def sy(value: float) -> float:
        return base + 18 - 36 * (value - low) / (high - low)

    points = data["setpoint"] + [(end, data["setpoint"][-1][1])]
    path = " ".join(f'{"M" if i == 0 else "L"}{x(t):.1f},{sy(v):.1f}' for i, (t, v) in enumerate(points))
    parts.append(f'<path class="setpoint" d="{path}"/>')
    for t, v in data["setpoint"]:
        if t == 0 or v == data["setpoint"][-1][1]:
            parts.append(f'<text class="value" x="{x(t) + 4:.1f}" y="{sy(v) - 5:.1f}">{v} °C</text>')

    flame_start = data["flame"][0]
    note_y = top + 146
    parts.append(f'<path class="bracket" d="M{x(0):.1f},{note_y - 6} V{note_y} H{x(flame_start):.1f} V{note_y - 6}"/>')
    parts.append(f'<text class="note" x="{x(0) + 2:.1f}" y="{note_y + 16}">{data["note"]}</text>')
    return "\n".join(parts)


def axis(top: float) -> str:
    parts = []
    for minute in range(0, MINUTES + 1):
        parts.append(f'<line class="grid" x1="{x(minute * 60):.1f}" y1="{TOP}" x2="{x(minute * 60):.1f}" y2="{top - 14}"/>')
        if minute % 2 == 0:
            parts.append(f'<text class="tick" x="{x(minute * 60):.1f}" y="{top}" text-anchor="middle">{minute}</text>')
    parts.append(f'<text class="tick" x="{x(MINUTES * 60):.1f}" y="{top + 18}" text-anchor="end">minutes after the heating demand</text>')
    return "\n".join(parts)


def svg() -> str:
    second = TOP + PANEL + GAP
    axis_top = second + PANEL + 30
    height = axis_top + 30
    style = """
  text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: #1f2328; }
  .title { font-size: 15px; font-weight: 600; }
  .label, .value, .tick { font-size: 12px; fill: #59636e; }
  .note { font-size: 12px; font-weight: 600; fill: #bc4c00; }
  .track { fill: #eff2f5; }
  .demand { fill: #0969da; }
  .flame { fill: #fb8500; }
  .setpoint { fill: none; stroke: #8250df; stroke-width: 2.5; }
  .bracket { fill: none; stroke: #bc4c00; stroke-width: 1.5; }
  .grid { stroke: #d1d9e0; stroke-width: 1; }
  @media (prefers-color-scheme: dark) {
    text { fill: #f0f6fc; }
    .label, .value, .tick { fill: #9198a1; }
    .note { fill: #ffa657; }
    .track { fill: #262c36; }
    .demand { fill: #4493f8; }
    .flame { fill: #ffa657; }
    .setpoint { stroke: #ab7df8; }
    .bracket { stroke: #ffa657; }
    .grid { stroke: #3d444d; }
  }"""
    body = "\n".join([axis(axis_top), panel(UPSTREAM, TOP), panel(XTREME, second)])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
            f'role="img" aria-label="One PWM block: with SAT 4.2.1 the flame starts 2 minutes after the heating demand, '
            f'with SAT-xtreme after 5 seconds">\n<style>{style}\n</style>\n{body}\n</svg>\n')


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg())
