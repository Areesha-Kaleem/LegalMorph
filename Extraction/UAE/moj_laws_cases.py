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


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe filename from a law title."""
    safe = re.sub(r'[\\/*?:"<>|\r\n]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:200]


def setup_driver(headless: bool = True) -> webdriver.Chrome | None:
    """Create and configure a Chrome WebDriver instance."""
    chrome_options = Options()
    # Proceed after DOMContentLoaded to avoid renderer timeouts on heavy pages
    chrome_options.page_load_strategy = "eager"
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(120)
        try:
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception:
            pass
        return driver
    except Exception as e:
        print(f"❌ Failed to initialize Chrome WebDriver: {e}")
        return None


def save_metadata_to_db(run_metadata: dict | None = None, per_law_metadata: dict | None = None, collection_name: str | None = None) -> None:
    """Insert run-level or per-law/case metadata into MongoDB.

    Database: LawGPT_Metadata_UAE
    Collection: moj_laws_scraping (default) or moj_cases_scraping
    """
    try:
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client["LawGPT_Metadata_UAE"]
        collection = db[collection_name] if collection_name else db["moj_laws_scraping"]

        def normalize(doc: dict) -> dict:
            normalized = dict(doc)
            for k, v in list(normalized.items()):
                if isinstance(v, datetime):
                    normalized[k] = v.isoformat()
            return normalized

        if run_metadata is not None:
            collection.insert_one(normalize(run_metadata))
        if per_law_metadata is not None:
            collection.insert_one(normalize(per_law_metadata))
    except Exception as e:
        print(f"⚠️ Failed to save metadata: {e}")


def ensure_output_directories(base_output_dir: str) -> tuple[str, str]:
    """Create and return (html_dir, text_dir) under base_output_dir."""
    html_dir = os.path.join(base_output_dir, "raw_html")
    text_dir = os.path.join(base_output_dir, "raw_text")
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    return html_dir, text_dir


def wait_for_tree_loaded(driver: webdriver.Chrome, timeout: int = 20) -> None:
    """Wait until the left TreeView container is present."""
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, "ctl00_ctl00_MainContent_NestedTree_TreeView1"))
    )


def expand_all_categories(driver: webdriver.Chrome, max_passes: int = 3) -> None:
    """Expand top-level categories in the ASP.NET TreeView to reveal law links.

    Strategy: click anchors whose href contains 'TreeView_PopulateNode' at the category level.
    We perform a few passes to catch nodes that appear after earlier expansions.
    """
    for _ in range(max_passes):
        try:
            tree = driver.find_element(By.ID, "ctl00_ctl00_MainContent_NestedTree_TreeView1")
        except NoSuchElementException:
            return

        expand_links = tree.find_elements(
            By.XPATH,
            ".//a[contains(@href, 'TreeView_PopulateNode') and contains(@id, 'TreeView1t')]"
        )

        clicked_any = False
        for link in expand_links:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                driver.execute_script("arguments[0].click();", link)
                time.sleep(0.4)
                clicked_any = True
            except StaleElementReferenceException:
                clicked_any = True
                continue
            except Exception:
                continue

        if not clicked_any:
            break


def collect_law_entries(driver: webdriver.Chrome) -> list[dict]:
    """Return a list of law dicts with keys: id, title.

    We select anchors that target the 'naf' frame and link to a .html document
    without an article fragment (#Anchor...).
    """
    try:
        tree = driver.find_element(By.ID, "ctl00_ctl00_MainContent_NestedTree_TreeView1")
    except NoSuchElementException:
        return []

    anchors = tree.find_elements(
        By.XPATH,
        ".//a[@target='naf' and contains(@href, '.html') and not(contains(@href, '#'))]"
    )
    entries: list[dict] = []
    seen_titles: set[str] = set()
    for a in anchors:
        try:
            title = a.text.strip()
            node_id = a.get_attribute("id") or ""
            if not title or not node_id:
                continue
            if title in seen_titles:
                continue
            entries.append({"id": node_id, "title": title})
            seen_titles.add(title)
        except StaleElementReferenceException:
            continue
    return entries


def switch_to_content_frame(driver: webdriver.Chrome, timeout: int = 15) -> bool:
    """Switch into the main content frame/iframe named 'naf'. Return True if successful."""
    driver.switch_to.default_content()
    try:
        WebDriverWait(driver, timeout).until(
            EC.frame_to_be_available_and_switch_to_it((By.NAME, "naf"))
        )
        # Ensure body is present
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return True
    except TimeoutException:
        try:
            # Try by id as a fallback
            driver.switch_to.default_content()
            WebDriverWait(driver, timeout).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "naf"))
            )
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            return True
        except Exception:
            driver.switch_to.default_content()
            return False


def extract_clean_text(html_content: str) -> str:
    """Clean HTML to readable text."""
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Normalize whitespace lines
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def scrape_moj_laws(
    base_url: str = "https://elaws.moj.gov.ae/English.aspx?val=UAE-KaitEL1",
    base_output_dir: str = os.path.join("data", "uae", "raw", "moj_laws"),
    headless: bool = True,
    scrape_all: bool = True,
    limit: int | None = None,
    data_type: str = "laws",
) -> tuple[int, int]:
    """Scrape UAE MOJ laws or cases and store HTML + text for each page.

    Args:
        data_type: "laws" or "cases" to determine what to scrape
    Returns: (num_scraped, num_skipped)
    """
    # Configure based on data type
    if data_type.lower() == "cases":
        base_url = "https://elaws.moj.gov.ae/Temiiz.aspx?val=UAE-UC-En"
        base_output_dir = os.path.join("data", "uae", "raw", "moj_cases")
        source_name = "MOJ_Cases"
        collection_name = "moj_cases_scraping"
    else:  # laws (default)
        base_url = "https://elaws.moj.gov.ae/English.aspx?val=UAE-KaitEL1"
        base_output_dir = os.path.join("data", "uae", "raw", "moj_laws")
        source_name = "UAE_MOJ_eLaws"
        collection_name = "moj_laws_scraping"

    start_time = datetime.now()

    html_dir, text_dir = ensure_output_directories(base_output_dir)
    driver = setup_driver(headless=headless)
    if not driver:
        end_time = datetime.now()
        session_doc = {
            "session_id": f"moj_{data_type}_{start_time.strftime('%Y%m%dT%H%M%SZ')}",
            "source": source_name,
            "source_url": base_url,
            "scrape_mode": "all" if scrape_all else "limit",
            "limit": limit if not scrape_all else None,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {
                "html_dir": html_dir,
                "text_dir": text_dir,
            },
            "scraped_count": 0,
            "skipped_count": 0,
            "filenames": [],
            "status": "failed",
            "error": "webdriver_init_failed",
        }
        save_metadata_to_db(run_metadata=session_doc, collection_name=collection_name)
        return 0, 0

    scraped_count = 0
    skipped_count = 0
    session_filenames: list[str] = []

    try:
        print(f"🌐 Opening {base_url}")
        try:
            driver.get(base_url)
        except TimeoutException:
            print("⏱️ Page load timed out. Stopping further loading and proceeding...")
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
        wait_for_tree_loaded(driver)

        print("📂 Expanding categories...")
        expand_all_categories(driver, max_passes=3)
        time.sleep(1)

        # Collect law/case links after expansion
        entries = collect_law_entries(driver)
        print(f"🔎 Found {len(entries)} {data_type} entries to consider")

        for idx, entry in enumerate(entries, start=1):
            title = entry["title"]
            node_id = entry["id"]
            filename = sanitize_filename(title)
            html_path = os.path.join(html_dir, f"{filename}.html")
            text_path = os.path.join(text_dir, f"{filename}.txt")

            # Dedup: require both existing to skip
            if os.path.exists(html_path) and os.path.exists(text_path):
                print(f"⏭️  [{idx}/{len(entries)}] Skipping existing: {title}")
                skipped_count += 1
                continue

            # Respect limit when not scraping all
            if not scrape_all and limit is not None and scraped_count >= limit:
                print("🛑 Reached user-specified limit. Stopping.")
                break

            print(f"➡️  [{idx}/{len(entries)}] Opening {data_type[:-1]}: {title}")

            # Re-locate the node by id due to ASP.NET postbacks
            try:
                wait_for_tree_loaded(driver)
                anchor = driver.find_element(By.ID, node_id)
            except NoSuchElementException:
                # Tree might require further expansion; try expand again and find by text
                expand_all_categories(driver, max_passes=2)
                try:
                    anchor = driver.find_element(By.XPATH, f"//div[@id='ctl00_ctl00_MainContent_NestedTree_TreeView1']//a[@target='naf' and normalize-space(text())={repr(title)}]")
                except NoSuchElementException:
                    print(f"⚠️ Could not re-locate anchor for: {title}")
                    continue

            # Click the law/case link
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", anchor)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", anchor)
            except Exception as e:
                print(f"⚠️ Click failed for '{title}': {e}")
                continue

            # Switch to content frame and wait for load
            if not switch_to_content_frame(driver, timeout=20):
                print("⚠️ Could not switch to content frame 'naf'. Skipping.")
                driver.switch_to.default_content()
                continue

            # Wait a bit for the content to stabilize
            time.sleep(1.0)

            # Capture only the frame's HTML (main content)
            try:
                content_html = driver.page_source
            except Exception as e:
                print(f"⚠️ Failed to get page source for '{title}': {e}")
                driver.switch_to.default_content()
                continue

            content_text = extract_clean_text(content_html)

            # Save files
            try:
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(content_html)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(content_text)
                print(f"✅ Saved HTML: {html_path}")
                print(f"✅ Saved Text: {text_path}")
            except Exception as e:
                print(f"❌ Failed to save files for '{title}': {e}")
                driver.switch_to.default_content()
                continue

            scraped_count += 1
            session_filenames.append(title)

            # Return to default content for the next iteration
            driver.switch_to.default_content()
            time.sleep(0.5)

        end_time = datetime.now()
        session_doc = {
            "session_id": f"moj_{data_type}_{start_time.strftime('%Y%m%dT%H%M%SZ')}",
            "source": source_name,
            "source_url": base_url,
            "scrape_mode": "all" if scrape_all else "limit",
            "limit": limit if not scrape_all else None,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {
                "html_dir": html_dir,
                "text_dir": text_dir,
            },
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "filenames": session_filenames,
            "status": "completed",
            "error": None,
        }
        save_metadata_to_db(run_metadata=session_doc, collection_name=collection_name)

        print(f"\n🎯 Done. Scraped: {scraped_count}, Skipped: {skipped_count}")
        return scraped_count, skipped_count

    except Exception as e:
        end_time = datetime.now()
        session_doc = {
            "session_id": f"moj_{data_type}_{start_time.strftime('%Y%m%dT%H%M%SZ')}",
            "source": source_name,
            "source_url": base_url,
            "scrape_mode": "all" if scrape_all else "limit",
            "limit": limit if not scrape_all else None,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {
                "html_dir": html_dir,
                "text_dir": text_dir,
            },
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "filenames": session_filenames,
            "status": "failed",
            "error": str(e),
        }
        save_metadata_to_db(run_metadata=session_doc, collection_name=collection_name)
        print(f"🚨 Unexpected error: {e}")
        return scraped_count, skipped_count
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    # Default run: headless True, scrape all
    scrape_moj_laws(
        base_url="https://elaws.moj.gov.ae/Temiiz.aspx?val=UAE-UC-En",
        base_output_dir=os.path.join("data", "uae", "raw", "moj_cases"),
        headless=True,
        scrape_all=True,
        limit=None,
        data_type="cases",
    )


