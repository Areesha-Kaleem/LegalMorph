# ✅ Statute scraper with OCR, dynamic filename, pagination, and limit
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
import pytesseract
from PIL import Image
from io import BytesIO
from pymongo import MongoClient
import time
import traceback
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ✅ Tesseract path for OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ✅ Clean filename utility
def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

# ✅ Extract data for a single statute
def extract_statute_data(driver, title, index):
    # ✅ Connect to MongoDB (adjust URI and DB name as needed)
    client = MongoClient("mongodb://localhost:27017/")
    db = client["Raw_statutes"]
    collection = db["statutes_raw_json"]
    print(f"🔍 Extracting data for statute: {title}")
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "react-pdf__Page"))
        )
        pages = driver.find_elements(By.CLASS_NAME, "react-pdf__Page")
        print(f"📄 Found {len(pages)} page(s)")

        all_text = ""
        for i, page in enumerate(pages):
            canvas = page.find_element(By.CLASS_NAME, "react-pdf__Page__canvas")
            # Scroll and shift down 100px for safety
            driver.execute_script("""
                arguments[0].scrollIntoView(true);
                window.scrollBy(0, 100);
            """, canvas)

            time.sleep(1)
            png_data = canvas.screenshot_as_png
            image = Image.open(BytesIO(png_data))
            text = pytesseract.image_to_string(image)
            all_text += f"\n=== Page {i+1} ===\n{text.strip()}\n"

        # ✅ Insert into MongoDB
        document = {
            "title": title,
            "index": index,
            "content": all_text.strip(),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        collection.insert_one(document)
        print(f"✅ Inserted into MongoDB: {title}")

        # Try closing the modal
        try:
            close_icon = driver.find_element(By.CSS_SELECTOR, 'svg[data-testid="HighlightOffIcon"]')
            close_icon.click()
        except Exception as e:
            print(f"⚠️ Error clicking close icon: {e}")

        time.sleep(1)

    except Exception as e:
        print(f"❌ Error extracting statute: {e}")
        traceback.print_exc()


# ✅ Main scraping function with pagination and limit
def scrape_statutes(statute_limit=100):
    domain = "eastlaw.pk"
    options = Options()
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)

    login_url = f"https://{domain}/"
    driver.get(login_url)
    print("🔐 Please log in manually in the Chrome window.")
    input("✅ After logging in completely, press ENTER to continue...")
    time.sleep(5)

    scraped_count = 0
    try:
        # Navigate to Statutes
        statutes_xpath = "//p[contains(text(), 'Statutes') or contains(text(), 'statutes')]"
        statutes_element = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, statutes_xpath))
        )
        driver.execute_script("arguments[0].click();", statutes_element)
        time.sleep(5)
        print("📚 Statutes section loaded")

        while scraped_count < statute_limit:
            statute_rows = WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.XPATH, "//table//tr[td]"))
            )

            for index, row in enumerate(statute_rows):
                if scraped_count >= statute_limit:
                    break
                try:
                    driver.execute_script("arguments[0].scrollIntoView();", row)
                    ActionChains(driver).move_to_element(row).perform()
                    time.sleep(1)

                    title = row.find_element(By.XPATH, "./td[2]").text
                    view_doc_button = row.find_element(By.XPATH,
                        ".//button[contains(text(), 'View Document') or contains(@class, 'view-document')]")
                    driver.execute_script("arguments[0].click();", view_doc_button)

                    extract_statute_data(driver, title, index)
                    scraped_count += 1
                except Exception as e:
                    print(f"⚠️ Skipped statute due to error: {e}")
                    traceback.print_exc()
                    continue

            # Check if we need to go to next page
            if scraped_count < statute_limit:
                try:
                    next_button = driver.find_element(By.XPATH, "//button[@aria-label='Go to next page']")
                    if "Mui-disabled" in next_button.get_attribute("class"):
                        print("🚫 No more pages available.")
                        break
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)
                    print("💌Moved to next slide")
                except Exception as e:
                    print(f"❌ Error clicking next page: {e}")
                    break

    except Exception as e:
        print(f"❌ Statutes scraping failed: {e}")
        traceback.print_exc()

    print(f"🎯 Statute scraping complete. Total statutes scraped: {scraped_count}")
    driver.quit()


