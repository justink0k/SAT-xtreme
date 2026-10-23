"""Take screenshots of the SAT Xtreme dashboard in the light and dark theme with Playwright.

The Home Assistant URL and a long-lived access token come from environment variables, so the token never ends
up in the repository or in a file:

    HA_URL=http://127.0.0.1:8123 HA_TOKEN=... python dev/screenshot_dashboard.py docs/images

Requires `pip install playwright` and `python -m playwright install chromium`.
"""
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD = "sat-xtreme"
VIEWPORT = {"width": 1280, "height": 1100}


def main(out: Path) -> None:
    url = os.environ["HA_URL"].rstrip("/")
    token = os.environ["HA_TOKEN"]
    out.mkdir(parents=True, exist_ok=True)

    # The frontend reads its tokens from local storage; a long-lived token works as access token
    tokens = json.dumps({
        "access_token": token, "token_type": "Bearer", "expires_in": 1800, "hassUrl": url,
        "clientId": f"{url}/", "expires": 9999999999999, "refresh_token": "",
    })

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for scheme in ("light", "dark"):
            page = browser.new_page(viewport=VIEWPORT, color_scheme=scheme, device_scale_factor=2)
            page.goto(f"{url}/?auth_callback=1")
            page.evaluate("tokens => window.localStorage.setItem('hassTokens', tokens)", tokens)
            page.goto(f"{url}/{DASHBOARD}/0?kiosk")
            page.wait_for_timeout(8000)
            page.screenshot(path=str(out / f"dashboard-{scheme}.png"), full_page=False)
            page.close()
        browser.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
