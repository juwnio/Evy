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


def _locate(by: str, value: str, name: str = None):
    """Resolve a locator strategy string to a Playwright locator."""
    page = _get_page()
    if by == "text":
        return page.get_by_text(value, exact=True)
    if by == "role":
        return page.get_by_role(value, name=name)
    if by == "css":
        return page.locator(value)
    if by == "label":
        return page.get_by_label(value)
    if by == "placeholder":
        return page.get_by_placeholder(value)
    raise ValueError(f"Unknown locator strategy: '{by}'")


def browser_get_elements(type: str = "all") -> str:
    """Discover interactive elements on the current page: buttons, inputs, or selects."""
    page = _get_page()
    data = page.evaluate("""(filterType) => {
        const result = {};
        if (filterType === 'button' || filterType === 'all') {
            result.buttons = Array.from(document.querySelectorAll(
                'button, input[type="submit"], input[type="button"], [role="button"]'
            )).filter(el => el.offsetParent !== null).map(el => ({
                text: (el.textContent || el.value || '').trim().slice(0, 80) || '(no text)'
            }));
        }
        if (filterType === 'input' || filterType === 'all') {
            result.inputs = Array.from(document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea'
            )).filter(el => el.offsetParent !== null).map(el => {
                const label = (el.labels && el.labels[0])
                    ? el.labels[0].textContent.trim()
                    : el.getAttribute('aria-label') || '';
                return { label, placeholder: el.placeholder || '', type: el.type || 'text' };
            });
        }
        if (filterType === 'select' || filterType === 'all') {
            result.selects = Array.from(document.querySelectorAll('select'))
                .filter(el => el.offsetParent !== null).map(el => {
                    const label = (el.labels && el.labels[0])
                        ? el.labels[0].textContent.trim()
                        : el.getAttribute('aria-label') || '';
                    return {
                        label,
                        options: Array.from(el.options).map(o => o.text).slice(0, 20)
                    };
                });
        }
        return result;
    }""", type)

    lines = []
    for b in data.get("buttons") or []:
        lines.append(f'[Button] "{b["text"]}"')
    for inp in data.get("inputs") or []:
        parts = []
        if inp["label"]:
            parts.append(f'label="{inp["label"]}"')
        if inp["placeholder"]:
            parts.append(f'placeholder="{inp["placeholder"]}"')
        parts.append(f'type="{inp["type"]}"')
        lines.append(f'[Input]  {" ".join(parts)}')
    for sel in data.get("selects") or []:
        opts = ", ".join(sel["options"])
        lines.append(f'[Select] label="{sel["label"]}" options=[{opts}]')

    if not lines:
        return f"No {type} elements found on this page."
    return "\n".join(lines)


def browser_click(by: str, value: str, name: str = None) -> str:
    """Click an element located by strategy. Supports text, role, css, label, and placeholder."""
    try:
        locator = _locate(by, value, name)
        locator.click()
        return f"Clicked element via '{by}': '{value}'"
    except Exception as e:
        return f"Failed to click element via '{by}': '{value}' — {e}"


def browser_fill(by: str, value: str, text: str) -> str:
    """Fill a form field located by strategy. Supports label, placeholder, and css."""
    try:
        locator = _locate(by, value)
        locator.fill(text)
        return f"Filled field via '{by}': '{value}'"
    except Exception as e:
        return f"Failed to fill field via '{by}': '{value}' — {e}"


def browser_select(by: str, value: str, option_label: str = None, option_value: str = None) -> str:
    """Select a dropdown option by label or value. Supports label and css locators."""
    if not option_label and not option_value:
        return "Provide either option_label or option_value."
    try:
        locator = _locate(by, value)
        if option_label:
            locator.select_option(label=option_label)
            return f"Selected option '{option_label}' via '{by}': '{value}'"
        else:
            locator.select_option(value=option_value)
            return f"Selected option '{option_value}' via '{by}': '{value}'"
    except Exception as e:
        return f"Failed to select option via '{by}': '{value}' — {e}"
