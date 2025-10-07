from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

import requests
import os
from typing import Optional

import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import pymongo
from datetime import datetime


TARGET_URL = "https://fac.gov.sa/en/legislations-posts/personal-status-system/"

# Output directories
RAW_DOWNLOAD_DIR = os.path.join("data", "ksa", "raw", "personal_status_law", "raw_download")
ARABIC_TEXT_DIR = os.path.join("data", "ksa", "raw", "personal_status_law", "arabic_text")


def ensure_dirs() -> None:
    os.makedirs(RAW_DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(ARABIC_TEXT_DIR, exist_ok=True)


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


def find_pdf_info(driver: webdriver.Chrome) -> tuple[str, str]:
    """
    Returns (pdf_url, filename).
    Looks for <a class="single-download-post-pdf" ... data-url=... data-filename=...>
    """
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a.single-download-post-pdf"))
    )
    link = driver.find_element(By.CSS_SELECTOR, "a.single-download-post-pdf")

    pdf_url = link.get_attribute("data-url") or link.get_attribute("href")
    filename = link.get_attribute("data-filename") or os.path.basename(pdf_url)

    if not pdf_url:
        raise NoSuchElementException("PDF URL not found on page")
    if not filename:
        filename = "download.pdf"
    return pdf_url, filename


def download_pdf(pdf_url: str, filename: str, download_dir: str = None) -> str:
    if download_dir is None:
        download_dir = RAW_DOWNLOAD_DIR
    os.makedirs(download_dir, exist_ok=True)
    pdf_path = os.path.join(download_dir, filename)
    with requests.get(pdf_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return pdf_path


def ocr_pdf_to_arabic_text(pdf_path: str, tesseract_path: Optional[str] = None) -> str:
    """
    Render PDF pages to images with PyMuPDF, pass to Tesseract with lang='ara',
    return concatenated Arabic text.
    If TESSERACT_PATH env var is set or tesseract_path is provided, use it.
    """
    # Force the installed Tesseract path as requested
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    # Ensure Arabic traineddata is discoverable
    os.environ.setdefault("TESSDATA_PREFIX", r"C:\Program Files\Tesseract-OCR\tessdata")

    print(f"Opening PDF: {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
        print(f"PDF opened successfully, {len(doc)} pages found")
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return ""
    
    texts = []
    try:
        for page_index in range(len(doc)):
            try:
                print(f"Processing page {page_index + 1}/{len(doc)}")
                page = doc.load_page(page_index)
                # Render at 300 DPI approx (zoom factor ~ 300/72)
                zoom = 300 / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                # OCR in Arabic
                txt = pytesseract.image_to_string(img, lang="ara")
                if txt.strip():
                    texts.append(txt.strip())
                    print(f"Page {page_index + 1}: Extracted {len(txt.strip())} characters")
                else:
                    print(f"Page {page_index + 1}: No text extracted")
            except Exception as e:
                print(f"Error processing page {page_index + 1}: {e}")
                continue
    finally:
        doc.close()

    result = "\n\n".join([t for t in texts if t])
    print(f"Total extracted text: {len(result)} characters")
    return result


def save_arabic_text(base_name: str, text: str, text_dir: str = None) -> str:
    if text_dir is None:
        text_dir = ARABIC_TEXT_DIR
    os.makedirs(text_dir, exist_ok=True)
    base_no_ext = os.path.splitext(base_name)[0]
    out_path = os.path.join(text_dir, f"{base_no_ext}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path


def scrape_personal_status_pdf(headless: bool = False, override_url: Optional[str] = None, tesseract_path: Optional[str] = None, download_dir: str = None, text_dir: str = None, metadata_db_name: str = None, metadata_collection_name: str = None) -> tuple[str, str]:
    """
    Opens the FAC Personal Status Law page, extracts the PDF URL, downloads it,
    performs Arabic OCR, and saves the text.

    Returns (pdf_path, arabic_text_path)
    """
    url = override_url or TARGET_URL
    start_time = datetime.now()
    session_id = f"ksa_personal_status_{start_time.strftime('%Y%m%dT%H%M%SZ')}"
    driver = setup_driver(headless=headless)
    try:
        try:
            driver.get(url)
        except TimeoutException:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        pdf_url, filename = find_pdf_info(driver)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    pdf_path = download_pdf(pdf_url, filename, download_dir)
    arabic_text = ocr_pdf_to_arabic_text(pdf_path, tesseract_path=tesseract_path)
    text_path = save_arabic_text(filename, arabic_text, text_dir)

    print(f"Downloaded PDF -> {pdf_path}")
    print(f"Saved Arabic text -> {text_path}")

    # Write session metadata (single document)
    try:
        end_time = datetime.now()
        doc = {
            "session_id": session_id,
            "source": "FAC_Personal_Status",
            "base_url": url,
            "start_timestamp": start_time.isoformat(),
            "end_timestamp": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "output_dirs": {
                "download_dir": download_dir or RAW_DOWNLOAD_DIR,
                "text_dir": text_dir or ARABIC_TEXT_DIR,
            },
            "pdf_url": pdf_url,
            "pdf_filename": filename,
            "scraped_count": 1,
            "skipped_count": 0,
            "items": [filename],
            "status": "completed",
            "error": None,
        }
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        
        # Use provided database and collection names or defaults
        db_name = metadata_db_name or "LawGPT_Metadata_KSA"
        collection_name = metadata_collection_name or "personal_status_law_scraping"
        
        db = client[db_name]
        collection = db[collection_name]
        collection.insert_one(doc)
        print(f"Metadata saved to {db_name}.{collection_name}")
    except Exception as e:
        print(f"Metadata save failed: {e}")
    return pdf_path, text_path


# if __name__ == "__main__":
#     # Optionally set Tesseract path via env: set TESSERACT_PATH=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
#     scrape_personal_status_pdf(headless=False)


