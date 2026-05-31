import atexit
import json
from typing import Optional

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

# ── Singleton state ───────────────────────────────────────────────────────────
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None


def _get_page() -> Page:
    """Return the shared page, lazily launching the browser if needed."""
    global _playwright, _browser, _page
    if _playwright is None:
        _playwright = sync_playwright().start()
    if _browser is None:
        with open("config.json", "r") as f:
            config = json.load(f)
        headless = config.get("browser_headless", True)
        _browser = _playwright.chromium.launch(headless=headless)
    if _page is None:
        _page = _browser.new_page()
    return _page


def _close_browser() -> None:
    """Teardown: close page, browser, and Playwright in order."""
    global _playwright, _browser, _page
    if _page is not None:
        try:
            _page.close()
        except Exception:
            pass
        _page = None
    if _browser is not None:
        try:
            _browser.close()
        except Exception:
            pass
        _browser = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


# Automatically clean up when the process exits
atexit.register(_close_browser)


def _ensure_scheme(url: str) -> str:
    """Prepend https:// if the URL has no scheme."""
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


# ── Navigation tools ──────────────────────────────────────────────────────────


def browser_navigate(url: str) -> str:
    """Navigate to a URL. Returns the page title and final URL."""
    page = _get_page()
    url = _ensure_scheme(url)
    try:
        page.goto(url, wait_until="domcontentloaded")
        return f"Navigated to '{page.title()}' — {page.url}"
    except Exception as e:
        return f"Navigation failed: {e}"


def browser_go_back() -> str:
    """Go back to the previous page in browser history."""
    page = _get_page()
    try:
        response = page.go_back(wait_until="domcontentloaded")
        if response is None:
            return "No previous page in history."
        return f"Went back to '{page.title()}' — {page.url}"
    except Exception as e:
        return f"Go back failed: {e}"


def browser_reload() -> str:
    """Reload the current page."""
    page = _get_page()
    try:
        page.reload(wait_until="domcontentloaded")
        return f"Reloaded '{page.title()}' — {page.url}"
    except Exception as e:
        return f"Reload failed: {e}"


def browser_close() -> str:
    """Close the browser and reset the session. The browser will relaunch on next use."""
    _close_browser()
    return "Browser closed."


# ── Reading tools ─────────────────────────────────────────────────────────────


def browser_get_text(selector: str = "body") -> str:
    """Extract visible text from the current page, scoped to an optional CSS selector."""
    page = _get_page()
    escaped = selector.replace('"', '\\"')
    text = page.evaluate(
        f"""() => {{
            const el = document.querySelector("{escaped}");
            return el ? el.innerText.trim() : null;
        }}"""
    )
    if not text:
        return f"No text found for selector '{selector}'."
    return text


def browser_get_links() -> str:
    """Return all links on the current page with anchor text and URLs."""
    page = _get_page()
    links = page.evaluate("""() =>
        Array.from(document.querySelectorAll('a[href]')).map(a => ({
            text: (a.textContent.trim() || '(no text)').slice(0, 100),
            href: a.href
        }))
    """)
    if not links:
        return "No links found on this page."
    return "\n".join(f"{l['text']} \u2192 {l['href']}" for l in links)


# ── Interaction tools ──────────────────────────────────────────────────────────


def browser_scroll(amount: int = 500) -> str:
    """Scroll the page down by the given number of pixels."""
    page = _get_page()
    page.evaluate(f"window.scrollBy(0, {amount})")
    return f"Scrolled down {amount}px."
