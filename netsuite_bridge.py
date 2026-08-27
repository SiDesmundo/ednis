"""Drives NetSuite's global search inside an already-running, already-logged-in
Chrome instance (started via launch_chrome_debug.bat) using the Chrome DevTools
Protocol. This never launches its own browser and never touches credentials.
"""

from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from chrome_utils import find_active_page, open_background_tab

CDP_URL = "http://localhost:9222"

SEARCH_INPUT_SELECTORS = [
    "#nsSearchField",
    "input[title='Search']",
    "input[placeholder*='Search' i]",
    # Last resort: brittle absolute path from this account's actual DOM,
    # in case the selectors above don't match this NetSuite instance/theme.
    "xpath=/html/body/div[1]/div[2]/div/div[1]/div[2]/input",
]


def _find_netsuite_page(context):
    return find_active_page(context, "netsuite.com")


def _connect():
    try:
        p = sync_playwright().start()
        browser = p.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        raise RuntimeError(
            "Can't reach Chrome on port 9222. Run launch_chrome_debug.bat "
            "first and make sure a NetSuite tab is open in that window."
        ) from e
    return p, browser


def _get_netsuite_page(browser):
    context = browser.contexts[0]
    page = _find_netsuite_page(context)
    if page is None:
        raise RuntimeError(
            "No NetSuite tab found in the automation Chrome window. "
            "Open your NetSuite dashboard there first."
        )
    return context, page


def _type_into_search(page, query: str, log):
    # Deliberately no bring_to_front(): CDP can type into a background tab
    # fine, and we don't want to yank focus away from whatever the user is
    # currently looking at.
    log(f"Found NetSuite tab: {page.url}")

    search_box = None
    for sel in SEARCH_INPUT_SELECTORS:
        loc = page.locator(sel)
        if loc.count() > 0:
            search_box = loc.first
            break

    if search_box is None:
        raise RuntimeError(
            "Could not find the NetSuite global search box (selectors need "
            "adjusting)."
        )

    search_box.click()
    search_box.fill("")
    search_box.type(query, delay=40)
    log(f"Typed '{query}', waiting for results...")
    page.wait_for_timeout(1000)


def _open_result_types(context, page, query: str, result_types, log) -> int:
    """Finds every global-search result whose label matches one of
    `result_types` (e.g. 'Sales Order', 'Return Authorization') and opens
    each in its own new tab. Returns how many were opened."""
    pattern = "|".join(result_types)
    results = page.locator(f"text=/^({pattern}):/")
    try:
        results.first.wait_for(timeout=8000)
    except Exception as e:
        raise RuntimeError(
            f"No {' / '.join(result_types)} result showed up for '{query}'. "
            "Double-check the order number."
        ) from e

    count = results.count()
    log(f"Found {count} matching result(s), opening in new tabs...")

    hrefs = []
    for i in range(count):
        anchor = results.nth(i).locator("xpath=ancestor-or-self::a[1]")
        href = anchor.get_attribute("href")
        if href:
            hrefs.append(urljoin(page.url, href))

    page.keyboard.press("Escape")

    for href in hrefs:
        open_background_tab(context, href)
        log(f"Opened {href}")

    return len(hrefs)


def open_sales_orders(query: str, log=print) -> int:
    """Search NetSuite for `query` and open every matching Sales Order result
    in its own new tab. Returns how many were opened."""
    p, browser = _connect()
    try:
        context, page = _get_netsuite_page(browser)
        _type_into_search(page, query, log)
        return _open_result_types(context, page, query, ["Sales Order"], log)
    finally:
        # Do NOT call browser.close() here: this browser is the user's real,
        # already-running Chrome window, not one Playwright launched itself.
        p.stop()


def open_sales_orders_with_ra(query: str, log=print):
    """Search NetSuite for `query`, open every matching Sales Order in a new
    tab, and also open any linked Return Authorization. Always opens Sales
    Orders even if no RA is tied to them. Returns (sales_order_count,
    return_authorization_count)."""
    p, browser = _connect()
    try:
        context, page = _get_netsuite_page(browser)
        _type_into_search(page, query, log)

        so_results = page.locator("text=/^Sales Order:/")
        ra_results = page.locator("text=/^Return Authorization:/")

        try:
            page.locator(
                "text=/^(Sales Order|Return Authorization):/"
            ).first.wait_for(timeout=8000)
        except Exception as e:
            raise RuntimeError(
                f"No Sales Order or Return Authorization result showed up for "
                f"'{query}'. Double-check the order number."
            ) from e

        so_count = so_results.count()
        ra_count = ra_results.count()
        log(f"Found {so_count} sales order(s), {ra_count} return authorization(s). Opening...")

        hrefs = []
        for locator, n in ((so_results, so_count), (ra_results, ra_count)):
            for i in range(n):
                anchor = locator.nth(i).locator("xpath=ancestor-or-self::a[1]")
                href = anchor.get_attribute("href")
                if href:
                    hrefs.append(urljoin(page.url, href))

        page.keyboard.press("Escape")

        for href in hrefs:
            open_background_tab(context, href)
            log(f"Opened {href}")

        return so_count, ra_count
    finally:
        p.stop()


def open_return_auths(query: str, log=print) -> int:
    """Search NetSuite for `query` and open every matching Return Authorization
    in its own new tab, WITHOUT opening the Sales Order. Returns how many were
    opened (0 if no RA is tied to the order)."""
    p, browser = _connect()
    try:
        context, page = _get_netsuite_page(browser)
        _type_into_search(page, query, log)

        ra_results = page.locator("text=/^Return Authorization:/")

        # Wait for the search to resolve to *something* for this order, so we
        # can tell "no RA tied" apart from "bad order number".
        try:
            page.locator(
                "text=/^(Sales Order|Return Authorization):/"
            ).first.wait_for(timeout=8000)
        except Exception as e:
            raise RuntimeError(
                f"No Sales Order or Return Authorization result showed up for "
                f"'{query}'. Double-check the order number."
            ) from e

        count = ra_results.count()
        if count == 0:
            log(f"No Return Authorization tied to {query}.")
            return 0

        log(f"Found {count} return authorization(s), opening in new tabs...")

        hrefs = []
        for i in range(count):
            anchor = ra_results.nth(i).locator("xpath=ancestor-or-self::a[1]")
            href = anchor.get_attribute("href")
            if href:
                hrefs.append(urljoin(page.url, href))

        page.keyboard.press("Escape")

        for href in hrefs:
            open_background_tab(context, href)
            log(f"Opened {href}")

        return len(hrefs)
    finally:
        p.stop()


def open_ecom_record(number: str, log=print) -> None:
    """Search NetSuite for the raw ecom record number, open it in a new tab,
    then open the link under its PARENT field in another new tab -- same
    new-tab-per-record behavior as the Sales Order buttons."""
    p, browser = _connect()
    try:
        context, page = _get_netsuite_page(browser)
        _type_into_search(page, number, log)

        result = page.locator("text=/^Ecom Record:/").first
        try:
            result.wait_for(timeout=8000)
        except Exception as e:
            raise RuntimeError(
                f"No 'Ecom Record' result showed up for '{number}'."
            ) from e

        anchor = result.locator("xpath=ancestor-or-self::a[1]")
        href = anchor.get_attribute("href")
        if not href:
            raise RuntimeError("Found the Ecom Record result but couldn't get its link.")
        ecom_url = urljoin(page.url, href)

        page.keyboard.press("Escape")

        log("Opening the Ecom Record in a new tab...")
        ecom_page = open_background_tab(context, ecom_url)
        ecom_page.wait_for_load_state("domcontentloaded")
        log(f"Opened {ecom_url}")

        log("Looking for the PARENT link...")
        parent_href = None
        try:
            label = ecom_page.get_by_text("PARENT", exact=False).first
            parent_href = label.locator("xpath=following::a[1]").get_attribute(
                "href", timeout=3000
            )
        except Exception:
            parent_href = None

        if not parent_href:
            raise RuntimeError(
                "Opened the Ecom Record, but couldn't find a PARENT link "
            )

        parent_url = urljoin(ecom_page.url, parent_href)
        open_background_tab(context, parent_url)
        log("Opened the PARENT record in a new tab.")
    finally:
        p.stop()
