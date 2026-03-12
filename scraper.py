from time import sleep
import datetime
from pathlib import Path
import traceback
import sys

import pandas as pd
from io import StringIO

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ================= CONFIG =================
URL = "https://www.nepalstock.com/floor-sheet"
OUTPUT_DIR = Path("data")
HEADLESS = True
# =========================================


# ---------------- DRIVER ----------------
def start_driver():

    options = webdriver.ChromeOptions()

    options.add_argument("--window-size=1400,900")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")

    if HEADLESS:
        options.add_argument("--headless=new")

    # Required for Linux cloud runners
    options.binary_location = "/usr/bin/chromium-browser"

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    return driver


def wait_page_ready(driver, timeout=15):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


# --------- GET NEPSE TRADE DATE ----------
def get_nepse_trade_date(driver):

    el = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((
            By.XPATH,
            "/html/body/app-root/div/main/div/app-floor-sheet/div/div[1]/div"
        ))
    )

    raw = el.text.strip()

    if raw.lower().startswith("as of"):
        raw = raw.replace("As of", "").strip()

    trade_dt = datetime.datetime.strptime(
        raw,
        "%b %d, %Y, %I:%M:%S %p"
    )

    return trade_dt.strftime("%Y%m%d")


# -------- SET PAGE SIZE = 500 ------------
def set_items_per_page(driver):

    select = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.table__perpage select")
        )
    )

    js = """
    var el = arguments[0];
    var opt = Array.from(el.options).find(o => o.value === '500');
    if (opt) {
        el.value = '500';
        el.dispatchEvent(new Event('change', {bubbles:true}));
    }
    """

    driver.execute_script(js, select)

    sleep(1)

    search_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button.box__filter--search")
        )
    )

    search_btn.click()

    sleep(2)


# -------------- SCRAPE TABLE --------------
def scrape_table(driver):

    table_html = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((By.XPATH, "//table"))
    ).get_attribute("outerHTML")

    tables = pd.read_html(StringIO(table_html))

    return tables[0]


# -------------- NEXT PAGE ----------------
def click_next(driver):

    nxt = driver.find_element(
        By.XPATH, "//li[contains(@class,'pagination-next')]"
    )

    if "disabled" in nxt.get_attribute("class").lower():
        return False

    btn = nxt.find_element(By.TAG_NAME, "a")

    driver.execute_script("arguments[0].click();", btn)

    sleep(2)

    return True


# ---------------- MAIN ----------------
def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    driver = start_driver()

    try:

        print("Opening NEPSE floorsheet page...")

        driver.get(URL)

        wait_page_ready(driver)

        sleep(2)

        trade_date = get_nepse_trade_date(driver)

        output_file = OUTPUT_DIR / f"floorsheet_{trade_date}.csv"

        # Prevent duplicate downloads
        if output_file.exists():
            print(f"File already exists for {trade_date}. Skipping.")
            driver.quit()
            return

        print(f"Trading Date: {trade_date}")

        print("Setting rows per page to 500...")
        set_items_per_page(driver)

        all_pages = []
        page = 1

        while True:

            print(f"Scraping page {page}")

            df = scrape_table(driver)

            if df.empty:
                break

            all_pages.append(df)

            if not click_next(driver):
                break

            page += 1

        if not all_pages:
            print("No data scraped.")
            sys.exit(1)

        final_df = pd.concat(all_pages, ignore_index=True)

        final_df.to_csv(output_file, index=False)

        print(f"SAVED {len(final_df)} rows → {output_file}")

    except Exception as e:

        print("[FATAL ERROR]", e)

        traceback.print_exc()

    finally:

        driver.quit()


if __name__ == "__main__":
    main()