from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from bs4 import BeautifulSoup
from datetime import datetime
import pymongo
import time
import os
import re
import random


"""ADJD judgments scraper that extracts HTML and Arabic text directly (no PDF/OCR)."""


def sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|\r\n]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:200]


def ensure_output_directories(base_output_dir: str) -> tuple[str, str]:
    html_dir = os.path.join(base_output_dir, "raw_html")
    text_dir = os.path.join(base_output_dir, "raw_text")
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    return html_dir, text_dir


def setup_driver(headless: bool, user_agent: str | None = None) -> webdriver.Chrome | None:
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
    options.add_experimental_option('useAutomationExtension', False)
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    else:
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(180)
        try:
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception:
            pass
        return driver
    except Exception as e:
        print(f"❌ Failed to initialize Chrome WebDriver: {e}")
        return None


def save_session_metadata(doc: dict) -> None:
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client["LawGPT_Metadata_UAE"]
        collection = db["adjd_cases_scraper"]
        normalized = dict(doc)
        for k, v in list(normalized.items()):
            if isinstance(v, datetime):
                normalized[k] = v.isoformat()
        collection.insert_one(normalized)
    except Exception as e:
        print(f"⚠️ Failed to save session metadata: {e}")


## PDF/OCR helpers removed: We read HTML directly from the judgment view.


def click_with_scroll_and_js(driver: webdriver.Chrome, element) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.5)
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def select_court_level(driver: webdriver.Chrome, court_level: str) -> bool:
    level_map = {
        "First Instance": "BtnFIC",
        "Appeal": "BtnAPP",
        "Cassation": "BtnCAS",
    }
    target_id = level_map.get(court_level.strip())
    if not target_id:
        print(f"⚠️ Unsupported court_level: {court_level}")
        return False
    try:
        button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, target_id))
        )
    except TimeoutException:
        print("⚠️ Court level buttons did not appear")
        return False
    return click_with_scroll_and_js(driver, button)


def select_case_type(driver: webdriver.Chrome, case_type: str) -> bool:
    try:
        container = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "MainCaseTypes"))
        )
    except TimeoutException:
        print("⚠️ Case type container not found")
        return False

    label_xpath = f".//label[contains(@class,'theme-checkbox-container')][.//span[normalize-space()={repr(case_type)}]]//input"
    try:
        input_box = container.find_element(By.XPATH, label_xpath)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", input_box)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", input_box)
        return True
    except Exception:
        print(f"⚠️ Could not select case type: {case_type}")
        return False


def click_show_judgments(driver: webdriver.Chrome) -> bool:
    try:
        button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'min-search-btn')]"))
        )
        return click_with_scroll_and_js(driver, button)
    except TimeoutException:
        print("⚠️ Show judgments button not found")
        return False


def wait_for_table_rows(driver: webdriver.Chrome, timeout: int = 60) -> None:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, "//table[@id='tblMyJudgments']//tbody/tr"))
    )


def table_next_is_available(driver: webdriver.Chrome) -> bool:
    try:
        next_a = driver.find_element(By.ID, "tblMyJudgments_next")
        classes = next_a.get_attribute("class") or ""
        return "disabled" not in classes.lower()
    except NoSuchElementException:
        return False


def click_table_next(driver: webdriver.Chrome) -> bool:
    try:
        next_a = driver.find_element(By.ID, "tblMyJudgments_next")
        return click_with_scroll_and_js(driver, next_a)
    except NoSuchElementException:
        return False


def extract_row_fields(row_el) -> dict:
    tds = row_el.find_elements(By.TAG_NAME, "td")
    result: dict = {
        "case_number": tds[0].text.strip() if len(tds) > 0 else "",
        "court": tds[1].text.strip() if len(tds) > 1 else "",
        "case_type": tds[2].text.strip() if len(tds) > 2 else "",
        "sub_type": tds[3].text.strip() if len(tds) > 3 else "",
        "judgment_date": tds[4].text.strip() if len(tds) > 4 else "",
    }
    return result


def scrape_adjd_cases(
    court_level: str,
    case_type: str,
    limit: int | None,
    base_url: str = "https://www.adjd.gov.ae/sites/eservices/EN/pages/judgments.aspx",
    base_output_dir: str = os.path.join("data", "uae", "raw", "adjd"),
    headless: bool = False,
    per_item_delay_seconds: tuple[float, float] = (3.0, 6.0),
    per_page_delay_seconds: tuple[float, float] = (8.0, 12.0),
    user_agent: str | None = None,
) -> tuple[int, int]:
    start_time = datetime.now()
    session_id = f"adjd_cases_{start_time.strftime('%Y%m%dT%H%M%SZ')}"

    html_dir, text_dir = ensure_output_directories(base_output_dir)
    driver = setup_driver(headless=headless, user_agent=user_agent)
    if not driver:
        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "ADJD",
            "source_url": base_url,
            "court_level": court_level,
            "case_type": case_type,
            "scrape_mode": "limit",
            "limit": limit,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {"html_dir": html_dir, "text_dir": text_dir},
            "scraped_count": 0,
            "skipped_count": 0,
            "pages_processed": 0,
            "filenames": [],
            "status": "failed",
            "error": "webdriver_init_failed",
        })
        return 0, 0

    visited_keys: set[str] = set()
    scraped_count = 0
    skipped_count = 0
    pages_processed = 0
    session_filenames: list[str] = []
    # We no longer track PDF/OCR stats since we extract HTML directly

    try:
        try:
            driver.get(base_url)
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        try:
            agree_btn = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.ID, "btnApproveTC"))
            )
            click_with_scroll_and_js(driver, agree_btn)
            time.sleep(random.uniform(1.0, 2.0))
        except TimeoutException:
            pass

        if not select_court_level(driver, court_level):
            print("⚠️ Could not select court level")
            return 0, 0
        time.sleep(random.uniform(2.0, 4.0))

        if not select_case_type(driver, case_type):
            print("⚠️ Could not select case type")
            return 0, 0
        time.sleep(random.uniform(2.0, 4.0))

        if not click_show_judgments(driver):
            print("⚠️ Could not click Show judgments")
            return 0, 0
        time.sleep(random.uniform(3.0, 6.0))

        while True:
            wait_for_table_rows(driver, timeout=90)
            rows = driver.find_elements(By.XPATH, "//table[@id='tblMyJudgments']//tbody/tr")
            for row in rows:
                fields = extract_row_fields(row)
                key = f"{fields['case_number']}__{fields['court']}__{fields['judgment_date']}"
                if key in visited_keys:
                    continue
                visited_keys.add(key)

                base_name = sanitize_filename(key)
                html_path = os.path.join(html_dir, f"{base_name}.html")
                text_path = os.path.join(text_dir, f"{base_name}.txt")

                if os.path.exists(html_path) and os.path.exists(text_path):
                    skipped_count += 1
                    continue

                if isinstance(limit, int) and scraped_count >= limit:
                    raise StopIteration

                try:
                    eye = row.find_element(By.XPATH, ".//a[contains(@class,'view-record')]")
                except NoSuchElementException:
                    continue

                click_with_scroll_and_js(driver, eye)

                # Wait for detail view: presence of back button indicates view loaded
                try:
                    WebDriverWait(driver, 45).until(
                        EC.presence_of_element_located((By.XPATH, "//button[contains(@class,'back-button')]"))
                    )
                except TimeoutException:
                    print("⚠️ Detail view did not load; skipping")
                    continue

                time.sleep(1.0)

                # Read specific HTML fragment that contains judgment data
                fragment_html = ""
                try:
                    try:
                        jud = driver.find_element(By.ID, "judContent")
                    except NoSuchElementException:
                        jud = driver.find_element(By.ID, "mainbody")
                    fragment_html = jud.get_attribute("innerHTML") or ""
                except Exception:
                    # Fallback to full page if fragment not available
                    try:
                        fragment_html = driver.page_source
                    except Exception:
                        fragment_html = ""

                # Clean text; keep Arabic letters and digits, remove English letters
                soup = BeautifulSoup(fragment_html, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                raw_text = soup.get_text(separator="\n")
                # Remove ASCII English letters; keep Arabic (\u0600-\u06FF, \u0750-\u077F, \u08A0-\u08FF) and digits (0-9, Arabic-Indic \u0660-\u0669)
                raw_text = re.sub(r"[A-Za-z]", "", raw_text)
                # Normalize whitespace and empty lines
                text_lines = [ln.strip() for ln in raw_text.splitlines()]
                text_content = "\n".join([ln for ln in text_lines if ln])

                # Save files
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(fragment_html)
                    with open(text_path, "w", encoding="utf-8") as f:
                        f.write(text_content)
                    scraped_count += 1
                    session_filenames.append(base_name)
                    print(f"✅ Saved: {html_path} | {text_path}")
                except Exception as e:
                    print(f"❌ Failed to save files: {e}")

                try:
                    back_btn = driver.find_element(By.XPATH, "//button[contains(@class,'back-button')]")
                    click_with_scroll_and_js(driver, back_btn)
                except NoSuchElementException:
                    try:
                        driver.back()
                    except Exception:
                        pass

                time.sleep(random.uniform(*per_item_delay_seconds))

            pages_processed += 1
            if isinstance(limit, int) and scraped_count >= limit:
                break

            if not table_next_is_available(driver):
                break

            click_table_next(driver)
            time.sleep(random.uniform(*per_page_delay_seconds))

        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "ADJD",
            "source_url": base_url,
            "court_level": court_level,
            "case_type": case_type,
            "scrape_mode": "limit",
            "limit": limit,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {"html_dir": html_dir, "text_dir": text_dir},
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "pages_processed": pages_processed,
            "filenames": session_filenames,
            "status": "completed",
            "error": None,
        })
        print(f"\n🎯 Done. Scraped: {scraped_count}, Skipped: {skipped_count}, Pages: {pages_processed}")
        return scraped_count, skipped_count

    except StopIteration:
        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "ADJD",
            "source_url": base_url,
            "court_level": court_level,
            "case_type": case_type,
            "scrape_mode": "limit",
            "limit": limit,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {"html_dir": html_dir, "text_dir": text_dir},
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "pages_processed": pages_processed,
            "filenames": session_filenames,
            "status": "completed",
            "error": None,
        })
        print(f"\n🎯 Done (limit reached). Scraped: {scraped_count}, Skipped: {skipped_count}, Pages: {pages_processed}")
        return scraped_count, skipped_count

    except Exception as e:
        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "ADJD",
            "source_url": base_url,
            "court_level": court_level,
            "case_type": case_type,
            "scrape_mode": "limit",
            "limit": limit,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {"html_dir": html_dir, "text_dir": text_dir},
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "pages_processed": pages_processed,
            "filenames": session_filenames,
            "status": "failed",
            "error": str(e),
        })
        print(f"🚨 Unexpected error: {e}")
        return scraped_count, skipped_count
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    scrape_adjd_cases(
        court_level="First Instance",
        case_type="Civil",
        limit=25,
        base_url="https://www.adjd.gov.ae/sites/eservices/EN/pages/judgments.aspx",
        base_output_dir=os.path.join("data", "uae", "raw", "adjd"),
        headless=False,
        per_item_delay_seconds=(3.0, 6.0),
        per_page_delay_seconds=(8.0, 12.0),
    )


