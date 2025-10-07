from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import pytesseract
from PIL import Image
from io import BytesIO
import time
import traceback
import re
import os
from datetime import datetime
from bs4 import BeautifulSoup
from langdetect import detect

# Tesseract path for OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def validate_login(driver, domain):
    """Validate if user is actually logged in"""
    try:
        # Wait a moment for page to load after login
        time.sleep(3)
        
        print("🔍 Validating login status...")
        
        # Check if "Login | Register" button is still visible (indicates not logged in)
        try:
            login_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Login | Register')]")
            if login_button.is_displayed():
                print("❌ 'Login | Register' button is still visible - user is not logged in")
                print("🔐 Please log in manually in the Chrome window and try again.")
                return False
        except:
            # Button not found, which means user might be logged in
            pass
        
        # If Login | Register button is not found, assume user is logged in
        print("✅ Login validation successful - Login | Register button not found")
        return True
        
    except Exception as e:
        print(f"❌ Login validation error: {e}")
        print("❌ Please log in manually in the Chrome window and try again.")
        return False

def extract_clean_text_from_html(html_content):
    """Extract clean text from HTML content"""
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()

    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()

    try:
        detected_lang = detect(text)
        if detected_lang != 'en':
            raise Exception(f"Non-English content detected: {detected_lang}")
    except Exception as e:
        print(f"⚠️ Language detection warning: {e}")
        # Continue with the text even if language detection fails

    return text

def extract_case_data(driver, title, cases_count, output_dir):
    """Extract case data for judgments"""
    # Sanitize title to make it a valid filename
    safe_title = re.sub(r'[\\/*?:"<>|\r\n]', "_", title).strip()
    
    # Create directories
    cases_dir = os.path.join(output_dir, "cases")
    html_dir = os.path.join(cases_dir, "html_cases")
    text_dir = os.path.join(cases_dir, "text_cases")
    
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    
    # Check if files already exist
    html_filename = f"{safe_title}.html"
    html_path = os.path.join(html_dir, html_filename)
    text_filename = f"{safe_title}.txt"
    text_path = os.path.join(text_dir, text_filename)
    
    # Check for existing files
    if os.path.exists(html_path) and os.path.exists(text_path):
        print(f"⏭️ Skipping already scraped case: {title}")
        return cases_count, None  # Return current cases_count (no increment for skipped case)
    
    WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
    driver.switch_to.window(driver.window_handles[1])

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.XPATH, "//p[contains(@class, 'text-2xl') and contains(@class, 'font-bold')]")
        )
    )

    html = driver.page_source
    text = extract_clean_text_from_html(html)

    try:
        # Save HTML
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ Saved HTML: {html_path}")
        
        # Save text
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✅ Saved text: {text_path}")
        
    except Exception as e:
        print(f"⚠️ Failed to save files for '{title}': {e}")

    driver.close()
    driver.switch_to.window(driver.window_handles[0])
    time.sleep(2)
    return cases_count + 1, safe_title  # Increment count for successfully processed case

def extract_statute_data(driver, title, scraped_count, output_dir):
    """Extract statute data using OCR and save to directories"""
    # Sanitize title to make it a valid filename
    safe_title = re.sub(r'[\\/*?:"<>|\r\n]', "_", title).strip()
    
    # Create directories
    statutes_dir = os.path.join(output_dir, "statutes")
    text_dir = os.path.join(statutes_dir, "text_statutes")
    
    os.makedirs(text_dir, exist_ok=True)
    
    # Check if files already exist
    text_filename = f"{safe_title}.txt"
    text_path = os.path.join(text_dir, text_filename)
    
    # Check for existing files
    if os.path.exists(text_path):
        print(f"⏭️ Skipping already scraped statute: {title}")
        return None, scraped_count  # Return current scraped_count (no increment for skipped statute)
    
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
            all_text += f"\n=== Page {i + 1} ===\n{text.strip()}\n"

        try:
            # Save text
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(all_text.strip())
            print(f"✅ Saved text: {text_path}")

        except Exception as e:
            print(f"⚠️ Failed to save files for '{title}': {e}")

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
        return None, scraped_count  # Return current count on error (no increment)
    
    # If we reach here, statute was successfully processed
    return safe_title, scraped_count + 1  # Increment count for successfully processed statute

def scrape_eastlaw_judgments(limit, output_dir, stop_flag=None, progress_callback=None, login_ready_event=None):
    """
    Scrape judgments from EastLaw
    
    Parameters:
    - limit (int): Number of cases to scrape
    - output_dir (str): Base output directory
    - stop_flag (threading.Event): Stop signal flag
    - progress_callback (function): Progress update callback
    - login_ready_event (threading.Event): Event to signal when manual login is ready
    
    Returns:
    - tuple: (case_count, issues_count, scraped_files, start_time, end_time, stop_reason)
    """
    start_time = datetime.now()
    scraped_files = []
    issues_count = 0
    stop_reason = "natural_completion"
    
    domain = "eastlaw.pk"
    options = Options()
    options.add_experimental_option("detach", True)
    
    try:
        driver = webdriver.Chrome(options=options)
        print("✅ Chrome WebDriver initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Chrome WebDriver: {e}")
        end_time = datetime.now()
        return (0, issues_count, scraped_files, start_time, end_time, "error_initialization")

    login_url = f"https://{domain}/"
    try:
        driver.get(login_url)
        print("🔐 Please log in manually in the Chrome window.")
        print("⏳ Waiting for manual login...")
        
        # Wait for the login ready event from UI
        if login_ready_event:
            login_ready_event.wait()  # Wait for UI signal
        else:
            time.sleep(10)  # Fallback wait
            
        print("✅ Login process completed")
        
        # Validate login
        if not validate_login(driver, domain):
            driver.quit()
            end_time = datetime.now()
            return (0, issues_count, scraped_files, start_time, end_time, "login_failed")
            
    except Exception as e:
        print(f"❌ Failed to navigate to EastLaw: {e}")
        driver.quit()
        end_time = datetime.now()
        return (0, issues_count, scraped_files, start_time, end_time, "error_navigation")

    print("⏳ Waiting for sidebar to load and clicking on items...")
    sidebar_keywords = ["Judgments"]
    visited_sections = set()
    total_cases_scraped = 0
    cases_count = 0
    
    for keyword in sidebar_keywords:
        # Check stop flag
        if stop_flag and stop_flag.is_set():
            print("🛑 Stop signal received. Stopping at keyword boundary...")
            stop_reason = "manual_stop"
            break
            
        if total_cases_scraped >= limit:
            print(f"🎯 Case limit reached ({limit} cases). Stopping automatically.")
            stop_reason = "case_limit_reached"
            break

        if keyword in visited_sections:
            continue

        xpath_variants = [
            f"//p[contains(text(), '{keyword}')]",
            f"//*[contains(text(), '{keyword}')]",
            f"//*[@aria-label='{keyword}']"
        ]
        sidebar_clicked = False
        for xpath in xpath_variants:
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                try:
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(3)
                    print(f"✅ Clicked on: {keyword}")
                    sidebar_clicked = True
                    break
                except:
                    continue
            if sidebar_clicked:
                break

        if not sidebar_clicked:
            print(f"❌ Could not find or click '{keyword}' in sidebar.")
            issues_count += 1
            continue

        visited_sections.add(keyword)
        if keyword == "Judgments" and total_cases_scraped < limit:
            try:
                print("⏳ Collecting case list...")
                cases = WebDriverWait(driver, 25).until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, "//div[contains(@aria-label, 'vs')]/div[contains(@class, 'action')]")
                    )
                )
                print(f"📄 Found {len(cases)} cases")

                while total_cases_scraped < limit:
                    # Check stop flag at case boundary
                    if stop_flag and stop_flag.is_set():
                        print("🛑 Stop signal received. Stopping at case boundary...")
                        stop_reason = "manual_stop"
                        break
                        
                    if total_cases_scraped >= limit:
                        print(f"🎯 Case limit reached ({limit} cases). Stopping automatically.")
                        stop_reason = "case_limit_reached"
                        break

                    if len(cases) < limit:
                        print(f"⚠️ Only {len(cases)} cases found. Adjusting case_limit to {len(cases)}.")
                        limit = len(cases)

                    i = 0
                    while total_cases_scraped < limit and i < len(cases):
                        try:
                            print(f"\n⏳ Processing case {i + 1}...")
                            
                            # Refresh list if needed (in case of DOM changes)
                            cases = driver.find_elements(By.XPATH,
                                                         "//div[contains(@aria-label, 'vs')]/div[contains(@class, 'action')]")

                            icon = cases[i]
                            title = icon.find_element(By.XPATH, "./parent::div").get_attribute("aria-label")
                            print(f"📘 Processing case: {title}")
                            
                            # Update progress callback
                            if progress_callback:
                                progress_callback(
                                    current_keyword=keyword,
                                    cases_for_keyword=total_cases_scraped,
                                    total_cases=total_cases_scraped,
                                    progress=min(100, (total_cases_scraped / limit) * 100)
                                )
                            
                            # Check stop flag before processing case
                            if stop_flag and stop_flag.is_set():
                                print("🛑 Stop signal received. Stopping during case processing...")
                                print(f"🔍 Debug: stop_flag.is_set() = {stop_flag.is_set()}")
                                stop_reason = "manual_stop"
                                break
                            
                            driver.execute_script("arguments[0].scrollIntoView();", icon)
                            driver.execute_script("arguments[0].click();", icon)
                            cases_count, safe_title = extract_case_data(driver, title, cases_count, output_dir)
                            
                            # Check stop flag after processing case
                            if stop_flag and stop_flag.is_set():
                                print("🛑 Stop signal received. Stopping after case processing...")
                                stop_reason = "manual_stop"
                                break
                            
                            # Only count and add to scraped files if case was actually processed
                            if safe_title is not None:
                                total_cases_scraped += 1
                                scraped_files.append(safe_title)
                            
                            # Update progress callback after successful scrape
                            if progress_callback:
                                progress_callback(
                                    current_keyword=keyword,
                                    cases_for_keyword=total_cases_scraped,
                                    total_cases=total_cases_scraped,
                                    progress=min(100, (total_cases_scraped / limit) * 100)
                                )
                            
                        except Exception as e:
                            print(f"⚠️ Skipped case due to error: {e}")
                            issues_count += 1
                            traceback.print_exc()
                            if len(driver.window_handles) > 1:
                                driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                        
                        # Always increment i to move to next case
                        i += 1

                    if total_cases_scraped < limit:
                        try:
                            next_button = driver.find_element(By.XPATH, "//button[@aria-label='Go to next page']")
                            if "Mui-disabled" in next_button.get_attribute("class"):
                                print("🚫 No more pages available.")
                                break
                            driver.execute_script("arguments[0].click();", next_button)
                            time.sleep(3)
                            print("💌 Moved to next slide")
                        except Exception as e:
                            print(f"❌ Error clicking next page: {e}")
                            break

                # Check if we need to exit the case loop
                if total_cases_scraped >= limit:
                    stop_reason = "case_limit_reached"
                    break
                elif stop_flag and stop_flag.is_set():
                    stop_reason = "manual_stop"
                    break

            except Exception as e:
                print(f"❌ Error collecting cases: {e}")
                issues_count += 1

    # Gracefully shut down browser session
    try:
        driver.quit()
        print("✅ Browser session closed successfully")
    except Exception as e:
        print(f"⚠️ Error closing browser session: {e}")
    
    # Capture end time
    end_time = datetime.now()
    
    # Final completion message and stop reason determination
    if stop_reason == "case_limit_reached":
        print(f"\n🎯 Case limit reached ({limit} cases). Stopping automatically.")
    elif stop_reason == "manual_stop":
        print(f"\n🛑 Manual stop requested. Stopped at {total_cases_scraped} cases.")
    else:
        print(f"\n🎉 Scraping completed naturally. Total cases saved: {total_cases_scraped}")
        stop_reason = "natural_completion"
    
    print(f"📊 Total cases saved to directories: {total_cases_scraped}")
    return (total_cases_scraped, issues_count, scraped_files, start_time, end_time, stop_reason)

def scrape_eastlaw_statutes(limit, output_dir, stop_flag=None, progress_callback=None, login_ready_event=None):
    """
    Scrape statutes from EastLaw
    
    Parameters:
    - limit (int): Number of statutes to scrape
    - output_dir (str): Base output directory
    - stop_flag (threading.Event): Stop signal flag
    - progress_callback (function): Progress update callback
    - login_ready_event (threading.Event): Event to signal when manual login is ready
    
    Returns:
    - tuple: (statute_count, issues_count, scraped_files, start_time, end_time, stop_reason)
    """
    start_time = datetime.now()
    scraped_files = []
    issues_count = 0
    stop_reason = "natural_completion"
    
    domain = "eastlaw.pk"
    options = Options()
    options.add_experimental_option("detach", True)
    
    try:
        driver = webdriver.Chrome(options=options)
        print("✅ Chrome WebDriver initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Chrome WebDriver: {e}")
        end_time = datetime.now()
        return (0, issues_count, scraped_files, start_time, end_time, "error_initialization")

    login_url = f"https://{domain}/"
    try:
        driver.get(login_url)
        print("🔐 Please log in manually in the Chrome window.")
        print("⏳ Waiting for manual login...")
        
        # Wait for the login ready event from UI
        if login_ready_event:
            login_ready_event.wait()  # Wait for UI signal
        else:
            time.sleep(10)  # Fallback wait
            
        print("✅ Login process completed")
        
        # Validate login
        if not validate_login(driver, domain):
            driver.quit()
            end_time = datetime.now()
            return (0, issues_count, scraped_files, start_time, end_time, "login_failed")
            
    except Exception as e:
        print(f"❌ Failed to navigate to EastLaw: {e}")
        driver.quit()
        end_time = datetime.now()
        return (0, issues_count, scraped_files, start_time, end_time, "error_navigation")

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

        while scraped_count < limit:
            # Check stop flag
            if stop_flag and stop_flag.is_set():
                print("🛑 Stop signal received. Stopping at statute boundary...")
                stop_reason = "manual_stop"
                break
                
            if scraped_count >= limit:
                print(f"🎯 Statute limit reached ({limit} statutes). Stopping automatically.")
                stop_reason = "case_limit_reached"
                break

            try:
                # Find statute rows using your exact logic
                statute_rows = WebDriverWait(driver, 15).until(
                    EC.presence_of_all_elements_located((By.XPATH, "//table//tr[td]"))
                )
                
                print(f"📄 Found {len(statute_rows)} statutes on current page")
                
                index = 0
                while scraped_count < limit and index < len(statute_rows):
                    # Check stop flag at statute boundary
                    if stop_flag and stop_flag.is_set():
                        print("🛑 Stop signal received. Stopping at statute boundary...")
                        stop_reason = "manual_stop"
                        break
                        
                    if scraped_count >= limit:
                        print(f"🎯 Statute limit reached ({limit} statutes). Stopping automatically.")
                        stop_reason = "case_limit_reached"
                        break

                    try:
                        row = statute_rows[index]
                        driver.execute_script("arguments[0].scrollIntoView();", row)
                        ActionChains(driver).move_to_element(row).perform()
                        time.sleep(1)

                        title = row.find_element(By.XPATH, "./td[2]").text
                        print(f"📘 Processing statute: {title}")
                        
                        # Update progress callback
                        if progress_callback:
                            progress_callback(
                                current_keyword="Statutes",
                                cases_for_keyword=scraped_count,
                                total_cases=scraped_count,
                                progress=min(100, (scraped_count / limit) * 100)
                            )
                        
                        # Check stop flag before processing statute
                        if stop_flag and stop_flag.is_set():
                            print("🛑 Stop signal received. Stopping during statute processing...")
                            print(f"🔍 Debug: stop_flag.is_set() = {stop_flag.is_set()}")
                            stop_reason = "manual_stop"
                            break
                        
                        view_doc_button = row.find_element(By.XPATH,
                                                           ".//button[contains(text(), 'View Document') or contains(@class, 'view-document')]")
                        driver.execute_script("arguments[0].click();", view_doc_button)
                        
                        safe_title, scraped_count = extract_statute_data(driver, title, scraped_count, output_dir)
                        
                        # Check stop flag after processing statute
                        if stop_flag and stop_flag.is_set():
                            print("🛑 Stop signal received. Stopping after statute processing...")
                            stop_reason = "manual_stop"
                            break
                        
                        # Only add to scraped files if statute was actually processed
                        if safe_title is not None:
                            scraped_files.append(safe_title)
                        
                        # Update progress callback after successful scrape
                        if progress_callback:
                            progress_callback(
                                current_keyword="Statutes",
                                cases_for_keyword=scraped_count,
                                total_cases=scraped_count,
                                progress=min(100, (scraped_count / limit) * 100)
                            )
                        
                        # Check if we've reached the limit after processing this statute
                        if scraped_count >= limit:
                            print(f"🎯 Statute limit reached ({limit} statutes). Stopping automatically.")
                            stop_reason = "case_limit_reached"
                            break
                        
                    except Exception as e:
                        print(f"⚠️ Skipped statute due to error: {e}")
                        issues_count += 1
                        traceback.print_exc()
                    
                    # Always increment index to move to next statute
                    index += 1

                # Check if we need to exit the statute loop
                if scraped_count >= limit:
                    stop_reason = "case_limit_reached"
                    break
                elif stop_flag and stop_flag.is_set():
                    stop_reason = "manual_stop"
                    break

                # Try to go to next page using your exact logic
                if scraped_count < limit:
                    try:
                        next_button = driver.find_element(By.XPATH, "//button[@aria-label='Go to next page']")
                        if "Mui-disabled" in next_button.get_attribute("class"):
                            print("🚫 No more pages available.")
                            break
                        driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(3)
                        print("💌 Moved to next slide")
                    except Exception as e:
                        print(f"❌ Error clicking next page: {e}")
                        break

            except Exception as e:
                print(f"❌ Error collecting statutes: {e}")
                issues_count += 1
                break

    except Exception as e:
        print(f"❌ Error in statute scraping: {e}")
        issues_count += 1

    # Gracefully shut down browser session
    try:
        driver.quit()
        print("✅ Browser session closed successfully")
    except Exception as e:
        print(f"⚠️ Error closing browser session: {e}")
    
    # Capture end time
    end_time = datetime.now()
    
    # Final completion message and stop reason determination
    if stop_reason == "case_limit_reached":
        print(f"\n🎯 Statute limit reached ({limit} statutes). Stopping automatically.")
    elif stop_reason == "manual_stop":
        print(f"\n🛑 Manual stop requested. Stopped at {scraped_count} statutes.")
    else:
        print(f"\n🎉 Scraping completed naturally. Total statutes saved: {scraped_count}")
        stop_reason = "natural_completion"
    
    print(f"📊 Total statutes saved to directories: {scraped_count}")
    return (scraped_count, issues_count, scraped_files, start_time, end_time, stop_reason) 