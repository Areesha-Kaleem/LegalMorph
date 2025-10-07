from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from bs4 import BeautifulSoup
from datetime import datetime
import pymongo
import os
import re


TARGET_URL = (
    "https://www.moj.gov.sa/English/Ministry/Departments/Mohammah/Pages/legalSystem.aspx?utm_source=chatgpt.co"
)

# Output directories
BASE_OUTPUT_DIR = os.path.join("data", "ksa", "raw", "moj_laws_ksa")
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
    return safe[:200] or "moj_law"


def extract_title_and_text(page_html: str) -> tuple[str, str, str]:
    """
    Returns (title, container_html, cleaned_text).
    Tries to locate the main article area; falls back to <body> if not found.
    """
    soup = BeautifulSoup(page_html, "html.parser")

    # Try to detect a main heading/title
    title = None
    for tag_name in ["h1", "h2", "h3"]:
        el = soup.find(tag_name)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break
    if not title:
        # Fallback title for this page
        title = "Code of Law Practice"

    # Try to find a central content container; otherwise use body
    container = None
    candidates = [
        soup.find("main"),
        soup.find("div", id="content"),
        soup.find("div", class_="ms-rtestate-field"),
        soup.find("div", role="main"),
        soup.find("div", id=True, class_=True),
    ]
    for cand in candidates:
        if cand:
            container = cand
            break
    if container is None:
        container = soup.body or soup

    # Get container HTML
    container_html = str(container)

    # Clean text
    for tag in container.find_all(["script", "style", "noscript"]):
        tag.decompose()
    text = container.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    cleaned_text = "\n".join(lines)

    return title, container_html, cleaned_text


def save_files(base_name: str, html_content: str, text_content: str, html_output_dir: str = None, text_output_dir: str = None) -> tuple[str, str]:
    # Use provided directories or defaults
    if html_output_dir is None:
        html_output_dir = RAW_HTML_DIR
    if text_output_dir is None:
        text_output_dir = RAW_TEXT_DIR
    
    # Ensure directories exist
    os.makedirs(html_output_dir, exist_ok=True)
    os.makedirs(text_output_dir, exist_ok=True)
    
    html_path = os.path.join(html_output_dir, f"{base_name}.html")
    text_path = os.path.join(text_output_dir, f"{base_name}.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text_content)
    print(f"Saved: {html_path} | {text_path}")
    return html_path, text_path


def scrape_moj_laws_ksa(headless: bool = False, url: str = TARGET_URL, html_output_dir: str = None, text_output_dir: str = None, metadata_db_name: str = None, metadata_collection_name: str = None) -> tuple[str, str]:
    start_time = datetime.now()
    session_id = f"ksa_moj_laws_{start_time.strftime('%Y%m%dT%H%M%SZ')}"
    driver = setup_driver(headless=headless)
    try:
        try:
            driver.get(url)
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        # Wait for some presence (any heading) to ensure content is there
        try:
            WebDriverWait(driver, 45).until(
                EC.presence_of_element_located((By.XPATH, "//h1|//h2|//h3"))
            )
        except TimeoutException:
            pass

        page_html = driver.page_source
        title, container_html, cleaned_text = extract_title_and_text(page_html)
        base_name = sanitize_filename(title)
        html_path, text_path = save_files(base_name, container_html, cleaned_text, html_output_dir, text_output_dir)

        # Write session metadata (single document per run)
        try:
            end_time = datetime.now()
            doc = {
                "session_id": session_id,
                "source": "MOJ_Code_of_Law_Practice",
                "base_url": url,
                "start_timestamp": start_time.isoformat(),
                "end_timestamp": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
                "output_dirs": {
                    "html_dir": html_output_dir or RAW_HTML_DIR,
                    "text_dir": text_output_dir or RAW_TEXT_DIR,
                },
                "scraped_count": 1,
                "skipped_count": 0,
                "items": [title],
                "status": "completed",
                "error": None,
            }
            client = pymongo.MongoClient("mongodb://localhost:27017/")
            
            # Use provided database and collection names or defaults
            db_name = metadata_db_name or "LawGPT_Metadata_KSA"
            collection_name = metadata_collection_name or "moj_laws_scrapping"
            
            db = client[db_name]
            collection = db[collection_name]
            collection.insert_one(doc)
            print(f"Metadata saved to {db_name}.{collection_name}")
        except Exception as e:
            print(f"Metadata save failed: {e}")

        return html_path, text_path
    finally:
        try:
            driver.quit()
        except Exception:
            pass


# if __name__ == "__main__":
#     scrape_moj_laws_ksa(headless=False)


