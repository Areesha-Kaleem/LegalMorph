from __future__ import annotations

import os
import re
import time
import random
from urllib.parse import urljoin
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from bs4 import BeautifulSoup
import pymongo


LIST_URL = "https://laws.moj.gov.sa/ar/JudicialDecisionsList/0?pageNumber=1&pageSize=12&viewType=grid&sortingBy=2"

# Default output directories (will be overridden by configurable parameters)
DEFAULT_BASE_OUTPUT_DIR = os.path.join("data", "ksa", "raw", "moj_cases_ksa")
DEFAULT_RAW_HTML_DIR = os.path.join(DEFAULT_BASE_OUTPUT_DIR, "raw_html")
DEFAULT_RAW_TEXT_DIR = os.path.join(DEFAULT_BASE_OUTPUT_DIR, "raw_text")


def ensure_output_dirs(html_output_dir: str = None, text_output_dir: str = None, logger=None) -> None:
    """Ensure output directories exist, using configurable paths or defaults."""
    try:
        if html_output_dir:
            # Convert to absolute path
            html_output_dir = os.path.abspath(html_output_dir)
            os.makedirs(html_output_dir, exist_ok=True)
            log_message(f"📁 Created/verified HTML directory: {html_output_dir}", logger)
        else:
            os.makedirs(DEFAULT_RAW_HTML_DIR, exist_ok=True)
            log_message(f"📁 Created/verified default HTML directory: {DEFAULT_RAW_HTML_DIR}", logger)
        
        if text_output_dir:
            # Convert to absolute path
            text_output_dir = os.path.abspath(text_output_dir)
            os.makedirs(text_output_dir, exist_ok=True)
            log_message(f"📁 Created/verified Text directory: {text_output_dir}", logger)
        else:
            os.makedirs(DEFAULT_RAW_TEXT_DIR, exist_ok=True)
            log_message(f"📁 Created/verified default Text directory: {DEFAULT_RAW_TEXT_DIR}", logger)
    except Exception as e:
        log_message(f"❌ Error creating directories: {str(e)}", logger)
        raise


def setup_driver(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-US")
    options.add_argument("--accept-lang=en-US,en")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-features=OptimizationHints,MediaRouter")
    # Suppress browser logs and warnings
    options.add_argument("--log-level=3")  # Only show fatal errors
    options.add_argument("--disable-logging")
    options.add_argument("--disable-gpu-logging")
    options.add_argument("--silent")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Optional: disable images for faster loading

    # Encourage Chrome to auto-translate Arabic pages to English on the list page
    prefs = {
        "translate": {"enabled": True},
        "translate_whitelists": {"ar": "en"},
        "intl.accept_languages": "en,en-US"
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    return driver


def random_sleep(min_s: float = 0.8, max_s: float = 1.6) -> None:
    time.sleep(random.uniform(min_s, max_s))


def sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|\r\n]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:200] or "moj_case"


def extract_arabic_text(html: str) -> str:
    """
    Extract complete readable text from HTML (Arabic + any other text),
    removing script/style/noscript and collapsing whitespace lines.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    # Drop common chrome/translate/nav wrappers to reduce noise
    for tag in soup.find_all(["header", "footer", "nav"]):
        try:
            tag.decompose()
        except Exception:
            pass
    for tag in soup.find_all(True, attrs={"role": "navigation"}):
        try:
            tag.decompose()
        except Exception:
            pass
    raw_text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in raw_text.splitlines()]
    # Remove Google Translate boilerplate if present
    drop_patterns = [
        "Original text",
        "Rate this translation",
        "Your feedback will be used to help improve Google Translate",
    ]
    cleaned = []
    for ln in lines:
        if not ln:
            continue
        lower = ln.lower()
        if any(pat.lower() in lower for pat in drop_patterns):
            continue
        cleaned.append(ln)
    lines = cleaned
    return "\n".join(lines)


def wait_for_list_cards(driver: webdriver.Chrome, timeout: int = 45) -> List[webdriver.remote.webelement.WebElement]:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.legislation-card-body"))
    )
    return driver.find_elements(By.CSS_SELECTOR, "div.legislation-card-body")


def parse_card_fields(card_el) -> Dict[str, Optional[str]]:
    result = {"judgment_number": None, "court": None, "city": None, "date_hijri": None, "details_url": None}
    try:
        header_el = card_el.find_element(By.XPATH, ".//div[contains(@class,'h4')]")
        header_text = header_el.text.strip()
        m = re.search(r"(\d{6,})", header_text)
        if m:
            result["judgment_number"] = m.group(1)
    except Exception:
        pass

    # Court
    try:
        court_label = card_el.find_element(By.XPATH, ".//div[contains(@class,'label') and normalize-space(.)='المحكمة']")
        court_value = court_label.find_element(By.XPATH, "../div[contains(@class,'deatils')]")
        result["court"] = court_value.text.strip()
    except Exception:
        pass

    # City
    try:
        city_label = card_el.find_element(By.XPATH, ".//div[contains(@class,'label') and normalize-space(.)='المدينة']")
        city_value = city_label.find_element(By.XPATH, "../div[contains(@class,'deatils')]")
        result["city"] = city_value.text.strip()
    except Exception:
        pass

    # Date (Hijri)
    try:
        date_label = card_el.find_element(By.XPATH, ".//div[contains(@class,'label') and normalize-space(.)='التاريخ']")
        span = date_label.find_element(By.XPATH, "../div[contains(@class,'deatils')]//span")
        result["date_hijri"] = span.text.strip()
    except Exception:
        pass

    # Details link (relative)
    try:
        link_el = card_el.find_element(By.XPATH, ".//a[contains(@class,'details-link')]")
        result["details_url"] = link_el.get_attribute("href") or link_el.get_attribute("data-href")
    except Exception:
        pass

    return result


def get_case_id(fields: Dict[str, Optional[str]]) -> str:
    if fields.get("judgment_number"):
        return fields["judgment_number"]  # type: ignore
    url = fields.get("details_url") or ""
    slug = url.rstrip("/").split("/")[-1]
    return slug or f"moj_case_{int(time.time())}"


def open_details_in_new_tab(driver: webdriver.Chrome, absolute_url: str, timeout: int = 45) -> str:
    current_handles = set(driver.window_handles)
    # Try to open in new tab
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", absolute_url)
    except Exception:
        pass
    # Poll for new handle (avoids tight WebDriver calls)
    new_handle = None
    start = time.time()
    while time.time() - start < 15:
        try:
            handles = driver.window_handles
            extra = list(set(handles) - current_handles)
            if extra:
                new_handle = extra[0]
                break
        except Exception:
            pass
        time.sleep(0.3)

    if new_handle is None:
        # Fallback: navigate same tab
        orig_handle = driver.current_window_handle
        driver.get(absolute_url)
        try:
            # Wait for the actual case content to load
            case_content_xpath = "//div[contains(@class, 'text-rulling') and contains(@class, 'selectable-text')]"
            WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, case_content_xpath)))
            
            # Simple wait to ensure content is fully loaded
            random_sleep(1.0, 2.0)
        except TimeoutException:
            print(f"⚠️ Timeout waiting for case content in fallback mode")
        html = driver.page_source
        # Navigate back to list
        try:
            driver.back()
            wait_for_list_cards(driver, timeout=45)
        except Exception:
            pass
        return html

    driver.switch_to.window(new_handle)
    try:
        # Wait for the actual case content to load - this is the key fix!
        # Look for the div containing the case text content
        case_content_xpath = "//div[contains(@class, 'text-rulling') and contains(@class, 'selectable-text')]"
        
        # Wait for this content container to appear
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, case_content_xpath)))
        
        # Simple wait to ensure content is fully loaded
        random_sleep(1.0, 2.0)
        
        # Get the HTML once content class is found
        html = driver.page_source
            
    except TimeoutException:
        print(f"⚠️ Timeout waiting for case content container")
        # Continue anyway and capture what we have
    html = driver.page_source
    try:
        driver.close()
    except Exception:
        pass
    # switch back to list tab
    remaining = list(current_handles)
    driver.switch_to.window(remaining[0])
    return html


def click_next_page(driver: webdriver.Chrome, timeout: int = 20) -> bool:
    try:
        # Support both Arabic ("التالي") and translated English ("the next").
        # Prefer aria-label when present.
        xpath = (
            "//li[contains(@class,'page-item')]//button[contains(@class,'page-link') and ("
            "@aria-label='Go to next page' or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'the next') or contains(normalize-space(.), 'التالي')"
            ")]"
        )
        next_btn = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].click();", next_btn)
        random_sleep()
        # wait for cards refresh
        wait_for_list_cards(driver, timeout=45)
        return True
    except TimeoutException:
        return False


def save_case_files(case_id: str, html: str, text: str, html_output_dir: str = None, text_output_dir: str = None, logger=None) -> Tuple[str, str]:
    """Save case files to specified directories or defaults."""
    try:
        # Use configurable directories or defaults
        html_dir = html_output_dir or DEFAULT_RAW_HTML_DIR
        text_dir = text_output_dir or DEFAULT_RAW_TEXT_DIR
        
        # Convert to absolute paths
        html_dir = os.path.abspath(html_dir)
        text_dir = os.path.abspath(text_dir)
        
        # Ensure directories exist
        os.makedirs(html_dir, exist_ok=True)
        os.makedirs(text_dir, exist_ok=True)
        
        # Verify directories exist
        if not os.path.exists(html_dir):
            log_message(f"❌ HTML directory does not exist: {html_dir}", logger)
            return "", ""
        if not os.path.exists(text_dir):
            log_message(f"❌ Text directory does not exist: {text_dir}", logger)
            return "", ""
        
        base = sanitize_filename(case_id)
        html_path = os.path.join(html_dir, f"{base}.html")
        text_path = os.path.join(text_dir, f"{base}.txt")
        
        # Save HTML file
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        # Save text file
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
        
        # Verify files were created and have content
        html_exists = os.path.exists(html_path)
        text_exists = os.path.exists(text_path)
        html_size = os.path.getsize(html_path) if html_exists else 0
        text_size = os.path.getsize(text_path) if text_exists else 0
        
        if html_exists and text_exists and html_size > 0 and text_size > 0:
            log_message(f"💾 Successfully saved case {case_id}: html={os.path.basename(html_path)} text={os.path.basename(text_path)}", logger)
            return os.path.basename(html_path), os.path.basename(text_path)
        else:
            log_message(f"❌ Failed to save case {case_id}: Files not created or empty", logger)
            return "", ""
            
    except Exception as e:
        log_message(f"❌ Error saving case {case_id}: {str(e)}", logger)
        import traceback
        log_message(f"❌ Traceback: {traceback.format_exc()}", logger)
        return "", ""


def already_scraped(case_id: str, text_output_dir: str = None) -> bool:
    """Check if case already exists in specified directory or default."""
    text_dir = text_output_dir or DEFAULT_RAW_TEXT_DIR
    base = sanitize_filename(case_id)
    text_path = os.path.join(text_dir, f"{base}.txt")
    return os.path.exists(text_path)


def insert_session_metadata(
    session_id: str,
    start_time: datetime,
    items: List[Dict[str, str]],
    start_url: str,
    page_size: int,
    max_cases_requested: int,
    scraped_count: int,
    skipped_count: int,
    status: str,
    error: Optional[str],
    metadata_db_name: str = "LawGPT_Metadata_KSA",
    metadata_collection_name: str = "moj_cases_scrapping",
    html_output_dir: str = None,
    text_output_dir: str = None,
) -> None:
    """Insert session metadata with configurable database and collection names."""
    try:
        end_time = datetime.now()  # Use local time instead of UTC
        doc = {
            "session_id": session_id,
            "source": "KSA_MOJ_JudicialDecisions",
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "start_url": start_url,
            "page_size": page_size,
            "max_cases_requested": max_cases_requested,
            "scraped_count": scraped_count,
            "skipped_count": skipped_count,
            "status": status,
            "error": error,
            "items": items,
            "html_output_dir": html_output_dir or DEFAULT_RAW_HTML_DIR,
            "text_output_dir": text_output_dir or DEFAULT_RAW_TEXT_DIR,
            "db_name": metadata_db_name,
            "collection_name": metadata_collection_name,
        }
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client[metadata_db_name]
        collection = db[metadata_collection_name]
        collection.insert_one(doc)
        print(f"Metadata saved to {metadata_db_name}.{metadata_collection_name}")
    except Exception as e:
        print(f"Metadata save failed: {e}")


def log_message(message: str, logger=None) -> None:
    """Log a message using the provided logger or print to console."""
    if logger and hasattr(logger, 'log'):
        logger.log(message)
    else:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        import sys
        sys.stdout.flush()


def scrape_moj_cases_ksa(
    list_url: str = LIST_URL,
    max_cases: int = 200,
    headless: bool = False,
    retries_per_case: int = 2,
    retries_per_page: int = 2,
    html_output_dir: str = None,
    text_output_dir: str = None,
    metadata_db_name: str = "LawGPT_Metadata_KSA",
    metadata_collection_name: str = "moj_cases_scrapping",
    logger=None,
) -> None:
    """Main scraping function with configurable parameters."""
    log_message(f"🚀 Starting MOJ Cases Scraper", logger)
    log_message(f"📊 Max cases to scrape: {max_cases}", logger)
    log_message(f"🌐 List URL: {list_url}", logger)
    log_message(f"📁 HTML output: {html_output_dir or DEFAULT_RAW_HTML_DIR}", logger)
    log_message(f"📁 Text output: {text_output_dir or DEFAULT_RAW_TEXT_DIR}", logger)
    
    ensure_output_dirs(html_output_dir, text_output_dir, logger)
    driver = setup_driver(headless=headless)
    start_time = datetime.now()  # Use local time instead of UTC
    session_id = f"ksa_moj_cases_{start_time.strftime('%Y%m%dT%H%M%S')}"

    visited_this_session: Set[str] = set()
    items_meta: List[Dict[str, str]] = []
    scraped_count = 0
    skipped_count = 0

    try:
        try:
            driver.get(list_url)
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        # Allow some time for translation UI to auto-translate
        random_sleep(1.2, 2.0)

        page_size = 12
        while scraped_count < max_cases:
            # Wait for cards
            cards = wait_for_list_cards(driver, timeout=60)

            for card in cards:
                if scraped_count >= max_cases:
                    break

                fields = parse_card_fields(card)
                abs_url = fields.get("details_url") or ""
                abs_url = urljoin(list_url, abs_url)
                fields["details_url"] = abs_url
                case_id = get_case_id(fields)

                if case_id in visited_this_session:
                    continue
                visited_this_session.add(case_id)



                if already_scraped(case_id, text_output_dir):
                    skipped_count += 1
                    log_message(f"⏭️ Skip (exists): {case_id}", logger)
                    continue

                success = False
                for attempt in range(retries_per_case + 1):
                    try:
                        log_message(f"🔍 Scraping: {case_id} (attempt {attempt+1})", logger)
                        html = open_details_in_new_tab(driver, abs_url)
                        text = extract_arabic_text(html)
                        
                        # Check if we got valid content
                        if not html or not text or len(text.strip()) < 10:
                            log_message(f"⚠️ No valid content extracted for {case_id}", logger)
                            continue
                        
                        html_filename, text_filename = save_case_files(case_id, html, text, html_output_dir, text_output_dir, logger)
                        
                        # Only count as successful if files were actually saved
                        if html_filename and text_filename:
                            items_meta.append({
                                "case_id": case_id,
                                "details_url": abs_url,
                                "judgment_number": fields.get("judgment_number") or "",
                                "court": fields.get("court") or "",
                                "city": fields.get("city") or "",
                                "date_hijri": fields.get("date_hijri") or "",
                                "language": "ar",
                                "html_filename": html_filename,
                                "text_filename": text_filename,
                            })
                            scraped_count += 1
                            success = True
                            log_message(f"✅ Successfully scraped and saved: {case_id}", logger)
                            random_sleep()
                            break
                        else:
                            log_message(f"❌ Failed to save files for {case_id}", logger)
                            continue
                    except WebDriverException as e:
                        log_message(f"⚠️ Error scraping {case_id}: {str(e)}", logger)
                        if attempt >= retries_per_case:
                            skipped_count += 1
                            log_message(f"❌ Failed to scrape {case_id} after {retries_per_case + 1} attempts", logger)
                        random_sleep(1.0, 2.0)

            if scraped_count >= max_cases:
                break

            # Next page
            log_message(f"📄 Moving to next page...", logger)
            advanced = False
            for _ in range(retries_per_page + 1):
                if click_next_page(driver):
                    advanced = True
                    log_message(f"➡️ Successfully moved to next page", logger)
                    break
                random_sleep(1.0, 2.0)
            if not advanced:
                log_message(f"🏁 No more pages available", logger)
                break

        log_message(f"🎉 Scraping completed! Scraped: {scraped_count}, Skipped: {skipped_count}", logger)

        insert_session_metadata(
            session_id=session_id,
            start_time=start_time,
            items=items_meta,
            start_url=list_url,
            page_size=page_size,
            max_cases_requested=max_cases,
            scraped_count=scraped_count,
            skipped_count=skipped_count,
            status="completed",
            error=None,
            metadata_db_name=metadata_db_name,
            metadata_collection_name=metadata_collection_name,
            html_output_dir=html_output_dir,
            text_output_dir=text_output_dir,
        )
    except Exception as e:
        log_message(f"💥 Scraping failed with error: {str(e)}", logger)
        raise
    finally:
        try:
            driver.quit()
            log_message(f"🔚 Browser closed", logger)
        except Exception:
            pass


if __name__ == "__main__":
    print("🚀 KSA MOJ Cases Scraper")
    print("=" * 40)
    
    try:
        # Get user input for scraping limit
        user_input = input("Enter number of cases to scrape (or press Enter for default 50): ").strip()
        
        if user_input:
            max_cases = int(user_input)
            if max_cases <= 0:
                print("❌ Invalid number. Using default: 50 cases")
                max_cases = 50
        else:
            max_cases = 50
            print("📊 Using default limit: 50 cases")
        
        print(f"🎯 Starting scraper with limit: {max_cases} cases")
        print("=" * 40)
        
        # Start scraping with user-defined limit
        scrape_moj_cases_ksa(max_cases=max_cases)
        
    except ValueError:
        print("❌ Invalid input. Using default: 50 cases")
        scrape_moj_cases_ksa(max_cases=50)
    except KeyboardInterrupt:
        print("\n⏹️ Scraping stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("🔄 Falling back to default: 50 cases")
        scrape_moj_cases_ksa(max_cases=50)


