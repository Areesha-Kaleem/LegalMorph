from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
import time
import re
from datetime import datetime
import pymongo


BASE_URL = "https://www.saudilegal.com/saudi-law-overview/real-estate"

# Output directories
BASE_OUTPUT_DIR = os.path.join("data", "ksa", "raw", "saudilegal")
RAW_HTML_DIR = os.path.join(BASE_OUTPUT_DIR, "raw_html")
RAW_TEXT_DIR = os.path.join(BASE_OUTPUT_DIR, "raw_text")


def ensure_dirs() -> None:
    os.makedirs(RAW_HTML_DIR, exist_ok=True)
    os.makedirs(RAW_TEXT_DIR, exist_ok=True)


def setup_driver(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(120)
    return driver


def sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/*?:"<>|\r\n]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe[:200] or "saudilegal_page"


def extract_main_section(html: str) -> tuple[str, str]:
    """
    Return (container_html, cleaned_text) for the main content section starting at
    the div with id "1068521083" which contains the Real Estate header and body.
    """
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", {"id": "1068521083"})
    if not container:
        # Fallback: try the known class
        container = soup.find("div", class_="u_1068521083 dmRespCol small-12 large-8 medium-8")
    if not container:
        raise ValueError("Main content container not found (id=1068521083)")

    container_html = str(container)

    # Clean text: strip scripts/styles and normalize whitespace
    for tag in container.find_all(["script", "style", "noscript"]):
        tag.decompose()
    text = container.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    cleaned = "\n".join(lines)
    return container_html, cleaned


def save_files(base_name: str, html_content: str, text_content: str) -> None:
    ensure_dirs()
    html_path = os.path.join(RAW_HTML_DIR, f"{base_name}.html")
    text_path = os.path.join(RAW_TEXT_DIR, f"{base_name}.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text_content)
    print(f"Saved: {html_path} | {text_path}")


def save_files_with_dirs(base_name: str, html_content: str, text_content: str, html_dir: str, text_dir: str) -> None:
    """Save files to specified directories"""
    html_path = os.path.join(html_dir, f"{base_name}.html")
    text_path = os.path.join(text_dir, f"{base_name}.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text_content)
    print(f"Saved: {html_path} | {text_path}")


def wait_main_loaded(driver: webdriver.Chrome, timeout: int = 30) -> None:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, "1068521083"))
    )


def get_nav_links(driver: webdriver.Chrome) -> list[tuple[str, str, str]]:
    """
    Return list of (title_text, href, slug) from the right-side navigation.
    Only items under /saudi-law-overview/ are considered.
    """
    links: list[tuple[str, str, str]] = []
    try:
        nav_container = driver.find_element(By.ID, "1196778096")
    except NoSuchElementException:
        return links

    anchors = nav_container.find_elements(By.XPATH, ".//a[contains(@href, '/saudi-law-overview/')]")
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            text = a.text.strip() or a.get_attribute("data-target-page-alias") or ""
            if not href:
                continue
            slug = href.rstrip("/").split("/")[-1]
            links.append((text or slug, href, slug))
        except Exception:
            continue
    # Deduplicate by href while preserving order
    seen = set()
    unique: list[tuple[str, str, str]] = []
    for item in links:
        if item[1] in seen:
            continue
        seen.add(item[1])
        unique.append(item)
    return unique


def scrape_saudilegal(headless: bool = False, base_url: str = None, html_output_dir: str = None, text_output_dir: str = None, exclusions: list = None, metadata_db_name: str = None, metadata_collection_name: str = None) -> None:
    # Use provided parameters or defaults
    target_url = base_url or BASE_URL
    html_dir = html_output_dir or RAW_HTML_DIR
    text_dir = text_output_dir or RAW_TEXT_DIR
    excluded_pages = set(exclusions) if exclusions else {"doing-business-in-saudi-arabia", "dispute-resolution"}
    
    # Create directories if they don't exist
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    
    start_time = datetime.now()  # Use local time instead of UTC
    session_id = f"ksa_saudilegal_{start_time.strftime('%Y%m%dT%H%M%S')}"
    driver = setup_driver(headless=headless)
    scraped_titles: list[str] = []
    skipped_count = 0
    try:
        # 1) Open target page and save
        print(f"Opening: {target_url}")
        try:
            driver.get(target_url)
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
        wait_main_loaded(driver, timeout=45)
        time.sleep(1.0)
        html = driver.page_source
        container_html, cleaned_text = extract_main_section(html)
        
        # Save with configurable directories
        base_name = "real-estate" if "real-estate" in target_url else "main-page"
        save_files_with_dirs(base_name, container_html, cleaned_text, html_dir, text_dir)
        scraped_titles.append("Real Estate")

        # 2) Collect nav links and iterate
        links = get_nav_links(driver)
        print(f"Found {len(links)} nav links")

        # Start from the first list item; we'll navigate one by one
        for title, href, slug in links:
            if slug in excluded_pages:
                print(f"Skip (excluded): {slug}")
                skipped_count += 1
                continue
            # Avoid re-saving the already saved real-estate page
            if slug == "real-estate":
                continue

            base_name = sanitize_filename(slug or title)
            html_path = os.path.join(html_dir, f"{base_name}.html")
            text_path = os.path.join(text_dir, f"{base_name}.txt")
            if os.path.exists(html_path) and os.path.exists(text_path):
                print(f"Skip (exists): {base_name}")
                skipped_count += 1
                continue

            full_url = urljoin(target_url, href)
            print(f"Navigate: {full_url}")

            try:
                driver.get(full_url)
            except TimeoutException:
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass

            # Wait for main section again and small delay
            try:
                wait_main_loaded(driver, timeout=45)
            except TimeoutException:
                print("Main container wait timed out; proceeding to parse anyway")
            time.sleep(0.8)

            page_html = driver.page_source
            try:
                cont_html, txt = extract_main_section(page_html)
            except Exception as e:
                print(f"Extraction failed for {base_name}: {e}")
                skipped_count += 1
                continue
            save_files_with_dirs(base_name, cont_html, txt, html_dir, text_dir)
            scraped_titles.append(title or slug)

    finally:
        end_time = datetime.now()  # Use local time instead of UTC
        # Write session metadata (single document)
        try:
            doc = {
                "session_id": session_id,
                "source": "SaudiLegal_Overview",
                "base_url": target_url,
                "start_timestamp": start_time.isoformat(),
                "end_timestamp": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
                "scrape_mode": "all",
                "exclusions": list(excluded_pages),
                "navigation_total": len(links) if 'links' in locals() else 0,
                "output_dirs": {
                    "html_dir": html_dir,
                    "text_dir": text_dir,
                },
                "scraped_count": len(scraped_titles),
                "skipped_count": skipped_count,
                "items": scraped_titles,
                "status": "completed",
                "error": None,
            }
            client = pymongo.MongoClient("mongodb://localhost:27017/")
            
            # Use provided database and collection names or defaults
            db_name = metadata_db_name or "LawGPT_Metadata_KSA"
            collection_name = metadata_collection_name or "saudilegal_scrapping"
            
            db = client[db_name]
            collection = db[collection_name]
            collection.insert_one(doc)
            print(f"Metadata saved to {db_name}.{collection_name}")
        except Exception as e:
            print(f"Metadata save failed: {e}")
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    scrape_saudilegal(headless=False)


