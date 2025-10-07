from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin
import pymongo
import time
import os
import re
import random


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe filename from a case title."""
    safe = re.sub(r'[\\/*?:"<>|\r\n]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:200]


def setup_driver(headless: bool = True, user_agent: str | None = None) -> webdriver.Chrome | None:
    """Create and configure a Chrome WebDriver instance."""
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


def ensure_output_directories(base_output_dir: str) -> tuple[str, str]:
    """Create and return (html_dir, text_dir) under base_output_dir."""
    html_dir = os.path.join(base_output_dir, "raw_html")
    text_dir = os.path.join(base_output_dir, "raw_text")
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    return html_dir, text_dir


def extract_clean_text(html_content: str) -> str:
    """Clean HTML to readable text."""
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def save_session_metadata(doc: dict) -> None:
    """Persist session-level metadata to MongoDB."""
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client["LawGPT_Metadata_UAE"]
        collection = db["difc_cases_scraper"]
        normalized = dict(doc)
        for k, v in list(normalized.items()):
            if isinstance(v, datetime):
                normalized[k] = v.isoformat()
        collection.insert_one(normalized)
    except Exception as e:
        print(f"⚠️ Failed to save session metadata: {e}")


def wait_for_listing(driver: webdriver.Chrome, timeout: int = 30) -> None:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'media--items')]"))
    )


def find_result_anchors(driver: webdriver.Chrome) -> list[tuple[str, str]]:
    """Return list of (title, href) for visible case title anchors on the listing page."""
    try:
        container = driver.find_element(By.XPATH, "//div[contains(@class,'media--items')]")
    except NoSuchElementException:
        return []

    anchors = container.find_elements(
        By.XPATH,
        ".//div[contains(@class,'each_result') and contains(@class,'content_set')]//h4/a"
    )
    results: list[tuple[str, str]] = []
    for a in anchors:
        try:
            title = a.text.strip()
            href = a.get_attribute("href") or ""
            if not title or not href:
                continue
            results.append((title, href))
        except StaleElementReferenceException:
            continue
    return results


def find_next_page_url(driver: webdriver.Chrome) -> str | None:
    """Return absolute URL for the next page, or None if not present."""
    try:
        a = driver.find_element(By.XPATH, "//li[contains(@class,'next')]/a[@rel='next']")
        href = a.get_attribute("href")
        if not href:
            # Some sites use relative href on listing
            href = a.get_attribute("data-href")
        if href:
            return urljoin("https://www.difccourts.ae", href)
    except NoSuchElementException:
        return None
    return None


def scrape_difc_cases(
    base_url: str = "https://www.difccourts.ae/rules-decisions/judgments-orders",
    base_output_dir: str = os.path.join("data", "uae", "raw", "difc"),
    headless: bool = True,
    limit: int | None = None,
    per_item_delay_seconds: tuple[float, float] = (1.0, 2.0),
    per_page_delay_seconds: tuple[float, float] = (2.0, 4.0),
    user_agent: str | None = None,
) -> tuple[int, int]:
    """Scrape DIFC Courts cases list and save HTML + text for each case page.

    Returns: (num_scraped, num_skipped)
    """
    start_time = datetime.now()
    session_id = f"difc_cases_{start_time.strftime('%Y%m%dT%H%M%SZ')}"

    html_dir, text_dir = ensure_output_directories(base_output_dir)
    driver = setup_driver(headless=headless, user_agent=user_agent)
    if not driver:
        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "DIFC_Courts",
            "source_url": base_url,
            "scrape_mode": "limit" if isinstance(limit, int) else "all",
            "limit": limit if isinstance(limit, int) else None,
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

    visited_links: set[str] = set()
    scraped_count = 0
    skipped_count = 0
    pages_processed = 0
    filenames: list[str] = []

    try:
        print(f"🌐 Opening {base_url}")
        try:
            driver.get(base_url)
        except TimeoutException:
            print("⏱️ Initial page load timed out; stopping load and continuing...")
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        while True:
            wait_for_listing(driver, timeout=45)
            time.sleep(0.5)
            anchors = find_result_anchors(driver)
            print(f"📄 Found {len(anchors)} cases on this page")

            for idx, (title, href) in enumerate(anchors, start=1):
                if href in visited_links:
                    continue
                visited_links.add(href)

                # Dedup by filesystem
                filename = sanitize_filename(title)
                html_path = os.path.join(html_dir, f"{filename}.html")
                text_path = os.path.join(text_dir, f"{filename}.txt")
                if os.path.exists(html_path) and os.path.exists(text_path):
                    skipped_count += 1
                    continue

                # Respect global limit
                if isinstance(limit, int) and scraped_count >= limit:
                    print("🛑 Reached user-specified limit. Stopping.")
                    raise StopIteration

                print(f"➡️  [{scraped_count + 1}] {title}")

                # Try to scroll link into view for human-like behavior
                try:
                    link_el = driver.find_element(By.XPATH, f"//h4/a[@href={repr(href)}]")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_el)
                    time.sleep(random.uniform(*per_item_delay_seconds))
                except Exception:
                    pass

                # Open in new tab and switch
                current_handles = set(driver.window_handles)
                try:
                    driver.execute_script("window.open(arguments[0], '_blank');", href)
                except Exception as e:
                    print(f"⚠️ Failed to open new tab for {href}: {e}")
                    continue

                WebDriverWait(driver, 15).until(lambda d: len(set(d.window_handles) - current_handles) > 0)
                new_handle = list(set(driver.window_handles) - current_handles)[0]
                driver.switch_to.window(new_handle)

                # Wait for body and small delay
                try:
                    WebDriverWait(driver, 45).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                except TimeoutException:
                    print("⚠️ Detail page body timed out")
                time.sleep(1.0)

                # Capture page
                try:
                    page_html = driver.page_source
                except Exception as e:
                    print(f"⚠️ Failed to read page_source: {e}")
                    try:
                        driver.close()
                    finally:
                        driver.switch_to.window(list(current_handles)[0])
                    continue

                page_text = extract_clean_text(page_html)

                # Save files
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(page_html)
                    with open(text_path, "w", encoding="utf-8") as f:
                        f.write(page_text)
                    scraped_count += 1
                    filenames.append(title)
                    print(f"✅ Saved: {html_path} | {text_path}")
                except Exception as e:
                    print(f"❌ Failed saving files: {e}")

                # Close detail tab and return
                try:
                    driver.close()
                except Exception:
                    pass
                driver.switch_to.window(list(current_handles)[0])

                # Human-like delay between items
                time.sleep(random.uniform(*per_item_delay_seconds))

            # After processing current page, move to next if available
            pages_processed += 1
            if isinstance(limit, int) and scraped_count >= limit:
                print("🛑 Reached user-specified limit on page end. Stopping.")
                break

            next_url = find_next_page_url(driver)
            if not next_url:
                print("🚫 No next page link found. Finished.")
                break

            print(f"➡️  Navigating to next page: {next_url}")
            try:
                driver.get(next_url)
            except TimeoutException:
                print("⏱️ Next page load timed out; stopping load and continuing...")
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass
            wait_for_listing(driver, timeout=45)
            time.sleep(random.uniform(*per_page_delay_seconds))

        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "DIFC_Courts",
            "source_url": base_url,
            "scrape_mode": "limit" if isinstance(limit, int) else "all",
            "limit": limit if isinstance(limit, int) else None,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {"html_dir": html_dir, "text_dir": text_dir},
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "pages_processed": pages_processed,
            "filenames": filenames,
            "status": "completed",
            "error": None,
        })
        print(f"\n🎯 Done. Scraped: {scraped_count}, Skipped: {skipped_count}, Pages: {pages_processed}")
        return scraped_count, skipped_count

    except StopIteration:
        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "DIFC_Courts",
            "source_url": base_url,
            "scrape_mode": "limit" if isinstance(limit, int) else "all",
            "limit": limit if isinstance(limit, int) else None,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {"html_dir": html_dir, "text_dir": text_dir},
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "pages_processed": pages_processed,
            "filenames": filenames,
            "status": "completed",
            "error": None,
        })
        print(f"\n🎯 Done (limit reached). Scraped: {scraped_count}, Skipped: {skipped_count}, Pages: {pages_processed}")
        return scraped_count, skipped_count

    except Exception as e:
        end_time = datetime.now()
        save_session_metadata({
            "session_id": session_id,
            "source": "DIFC_Courts",
            "source_url": base_url,
            "scrape_mode": "limit" if isinstance(limit, int) else "all",
            "limit": limit if isinstance(limit, int) else None,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {"html_dir": html_dir, "text_dir": text_dir},
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "pages_processed": pages_processed,
            "filenames": filenames,
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
    scrape_difc_cases(
        base_url="https://www.difccourts.ae/rules-decisions/judgments-orders",
        base_output_dir=os.path.join("data", "uae", "raw", "difc"),
        headless=False,
        limit=15,
        per_item_delay_seconds=(1.0, 2.0),
        per_page_delay_seconds=(2.0, 4.0),
    )


