from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup, NavigableString, Tag
import os
from datetime import datetime
import pymongo


TARGET_URL = "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/25df73d6-0f49-4dc5-b010-a9a700f2ec1d/2"

# Output directories
BASE_OUTPUT_DIR = os.path.join("data", "ksa", "raw", "anti_cyber_crime")
RAW_HTML_DIR = os.path.join(BASE_OUTPUT_DIR, "raw_html")
RAW_TEXT_DIR = os.path.join(BASE_OUTPUT_DIR, "raw_text")


def ensure_output_directories() -> None:
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


def extract_div_lawtext_html_and_clean_text(page_html: str) -> tuple[str, str, str]:
    """
    Returns (law_title, law_div_html, cleaned_text_starting_from_title).
    Cleaned text begins at the first h3.center with text "Anti-Cyber Crime Law" inside div#divLawText.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    container = soup.find("div", {"id": "divLawText"})
    if container is None:
        raise ValueError("div#divLawText not found")

    # Save full HTML of the container for raw_html output
    container_html = str(container)

    # Find the first <h3 class="center">Anti-Cyber Crime Law</h3>
    title_h3 = None
    for h3 in container.find_all("h3", class_="center"):
        if h3.get_text(strip=True).lower() == "anti-cyber crime law":
            title_h3 = h3
            break

    if title_h3 is None:
        # Fallback: try to use the system title h1 if present
        law_title_el = container.find(["h3", "h1"], string=True)
        law_title = law_title_el.get_text(strip=True) if law_title_el else "anti_cyber_crime_law"
        cleaned_text = clean_text(container)
        return law_title, container_html, cleaned_text

    law_title = title_h3.get_text(strip=True)

    # Build a new fragment starting from title_h3 through the end of container
    content_nodes = []

    # Include the title node itself
    content_nodes.append(title_h3)

    # Collect all following siblings of the title within the same container
    for sib in title_h3.next_siblings:
        # stop if sibling is outside container (it shouldn't be) – keep all until end
        if isinstance(sib, (NavigableString, Tag)):
            content_nodes.append(sib)

    fragment_soup = BeautifulSoup("", "html.parser")
    wrapper = fragment_soup.new_tag("div")
    for node in content_nodes:
        wrapper.append(BeautifulSoup(str(node), "html.parser"))

    cleaned_text = clean_text(wrapper)
    return law_title, container_html, cleaned_text


def clean_text(node: Tag) -> str:
    for tag in node.find_all(["script", "style", "noscript"]):
        tag.decompose()
    text = node.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def sanitize_filename(name: str) -> str:
    import re
    safe = re.sub(r'[\\/*?:"<>|\r\n]', "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return (safe or "anti_cyber_crime_law")[:200]


def scrape_anti_cyber_crime_law(url: str = TARGET_URL, headless: bool = False, html_output_dir: str = None, text_output_dir: str = None) -> tuple[str, str]:
    """
    Scrape the Anti-Cyber Crime Law page, saving:
      - full HTML of div#divLawText to html_output_dir
      - cleaned text (starting at the specified title h3) to text_output_dir
    Returns (html_path, text_path)
    """
    # Use provided directories or defaults
    if html_output_dir is None:
        html_output_dir = RAW_HTML_DIR
    if text_output_dir is None:
        text_output_dir = RAW_TEXT_DIR
    
    # Ensure directories exist
    os.makedirs(html_output_dir, exist_ok=True)
    os.makedirs(text_output_dir, exist_ok=True)
    start_time = datetime.now()
    session_id = f"ksa_boe_anti_cyber_{start_time.strftime('%Y%m%dT%H%M%SZ')}"
    driver = setup_driver(headless=headless)
    try:
        try:
            driver.get(url)
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        # Wait for the container to be present
        try:
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.ID, "divLawText"))
            )
        except TimeoutException:
            # Proceed; we will try parsing whatever loaded
            pass

        page_html = driver.page_source
        law_title, container_html, cleaned_text = extract_div_lawtext_html_and_clean_text(page_html)

        filename = sanitize_filename(law_title)
        html_path = os.path.join(html_output_dir, f"{filename}.html")
        text_path = os.path.join(text_output_dir, f"{filename}.txt")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(container_html)
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)

        print(f"Saved HTML -> {html_path}")
        print(f"Saved Text -> {text_path}")
        # Write session metadata (single document)
        try:
            end_time = datetime.now()
            doc = {
                "session_id": session_id,
                "source": "BOE_Anti_Cyber_Crime",
                "base_url": url,
                "start_timestamp": start_time.isoformat(),
                "end_timestamp": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
                "output_dirs": {
                    "html_dir": html_output_dir,
                    "text_dir": text_output_dir,
                },
                "scraped_count": 1,
                "skipped_count": 0,
                "items": [law_title],
                "status": "completed",
                "error": None,
            }
            client = pymongo.MongoClient("mongodb://localhost:27017/")
            db = client["LawGPT_Metadata_KSA"]
            collection = db["anti_cyber_crime_scraping"]
            collection.insert_one(doc)
            print("Metadata saved to LawGPT_Metadata_KSA.anti_cyber_crime_scraping")
        except Exception as e:
            print(f"Metadata save failed: {e}")

        return html_path, text_path
    finally:
        try:
            driver.quit()
        except Exception:
            pass


# if __name__ == "__main__":
#     scrape_anti_cyber_crime_law(headless=False)


