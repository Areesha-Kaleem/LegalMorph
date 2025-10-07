from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from datetime import datetime
import os
import time

def scraper_easylaw(limit, keywords=None, delay_between_requests=2, timeout_seconds=15, output_dir=None, stop_flag=None, progress_callback=None):
    """
    Web scraper for EasyLaw case documents.
    Extracts case text based on keywords, avoids duplicates by journal_id, and saves each case as a .txt file.

    Parameters:
    - limit (int): Total number of unique cases to scrape across all keywords.
    - keywords (list): List of keywords to search for. If None, uses default keywords.
    - delay_between_requests (int): Delay between requests in seconds.
    - timeout_seconds (int): Timeout for web requests in seconds.
    - output_dir (str): Output directory for saved files. If None, uses default.
    - stop_flag (threading.Event): Thread-safe flag to check for stop signal.
    - progress_callback (function): Callback function to update progress (optional).

    Returns:
    - tuple: (case_count, issues_count, scraped_files, start_time, end_time, stop_reason)
    """
    
    # Initialize metadata tracking for current session
    start_time = datetime.now()
    scraped_files = []
    issues_count = 0
    stop_reason = "natural_completion"  # Default stop reason

    # Initialize Selenium Chrome WebDriver
    try:
        driver = webdriver.Chrome()
        print("✅ Chrome WebDriver initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Chrome WebDriver: {e}")
        print("💡 Make sure Chrome browser is installed and chromedriver is in PATH")
        end_time = datetime.now()
        return (0, issues_count, scraped_files, start_time, end_time, "error_initialization")
    
    try:
        driver.get("https://www.easylaw.ai/")
        print("🚀 Browser launched and navigated to EasyLaw.")
    except Exception as e:
        print(f"❌ Failed to navigate to EasyLaw: {e}")
        driver.quit()
        end_time = datetime.now()
        return (0, issues_count, scraped_files, start_time, end_time, "error_navigation")

    # Create output directory if it doesn't exist
    if output_dir is None:
        base_dir = "D:\\LawGPT_data_pipeline\\data\\raw\\easylaw"
    else:
        base_dir = output_dir
    os.makedirs(base_dir, exist_ok=True)

    # Keywords to search on EasyLaw
    if keywords is None:
        keywords = ["murder", "land dispute", "domestic violence", "corruption", "divorce", "education"]
    case_limit = limit
    case_count = 0  # Counter to track total saved cases

    for keyword in keywords:
        # Check stop flag at keyword boundary
        if stop_flag and stop_flag.is_set():
            print("🛑 Stop signal received. Stopping at keyword boundary...")
            stop_reason = "manual_stop"
            break
            
        if case_count >= case_limit:
            print(f"🎯 Case limit reached ({case_limit} cases). Stopping automatically.")
            stop_reason = "case_limit_reached"
            break  # Stop if we already reached the required number of cases

        print(f"\n🔍 Searching for keyword: {keyword}")
        
        # Update progress callback with current keyword
        if progress_callback:
            progress_callback(current_keyword=keyword, cases_for_keyword=0)
        
        driver.get("https://www.easylaw.ai/")

        # Step 1: Enter keyword and trigger search
        try:
            WebDriverWait(driver, timeout_seconds).until(EC.presence_of_element_located((By.ID, "comment2"))).send_keys(keyword)
            WebDriverWait(driver, timeout_seconds).until(EC.element_to_be_clickable((By.ID, "myBtn"))).click()
        except Exception as e:
            print(f"❌ Error during search input or button click: {e}")
            issues_count += 1
            continue

        time.sleep(delay_between_requests)  # Use configured delay

        # Step 2: Navigate result pages
        while True:
            try:
                buttons = WebDriverWait(driver, timeout_seconds).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "btn-link"))
                )
                print(f"📄 Found {len(buttons)} case buttons on current page.")
            except TimeoutException:
                print("⏰ Timeout! No case buttons found.")
                issues_count += 1
                break  # Proceed to next keyword

            # Step 3: Iterate through case buttons (links)
            for button in buttons:
                # Check stop flag at case boundary
                if stop_flag and stop_flag.is_set():
                    print("🛑 Stop signal received. Stopping at case boundary...")
                    stop_reason = "manual_stop"
                    break  # Break out of case loop, but don't return yet
                    
                if case_count >= case_limit:
                    print(f"🎯 Case limit reached ({case_limit} cases). Stopping automatically.")
                    stop_reason = "case_limit_reached"
                    break  # Break out of case loop, but don't return yet

                journal_id = button.get_attribute("value").strip()
                
                # Try to get case ID for better file naming
                try:
                    # Look for case ID in the button text or nearby elements
                    case_id = button.text.strip()
                    if not case_id or case_id == journal_id:
                        # If no readable case ID, use a formatted version of journal ID
                        case_id = f"case_{journal_id[:8]}"  # Use first 8 chars for readability
                except:
                    case_id = f"case_{journal_id[:8]}"  # Fallback
                
                # Create directories for both HTML and text files
                html_dir = os.path.join(base_dir, "html_easylaw")
                text_dir = os.path.join(base_dir, "text_easylaw")
                os.makedirs(html_dir, exist_ok=True)
                os.makedirs(text_dir, exist_ok=True)

                # Check if case already exists in both directories (deduplication based on case_id)
                html_file_path = os.path.join(html_dir, f"{case_id}.html")
                text_file_path = os.path.join(text_dir, f"{case_id}.txt")
                
                if os.path.exists(html_file_path) and os.path.exists(text_file_path):
                    print(f"⏭️ Skipping already scraped case: {case_id}")
                    continue

                print(f"📘 Opening case: {case_id}")

                # Open case in new tab
                button.send_keys(Keys.CONTROL + Keys.RETURN)
                time.sleep(delay_between_requests)
                driver.switch_to.window(driver.window_handles[1])  # Switch to new tab
                time.sleep(delay_between_requests)

                try:
                    # Extract case content from table
                    table = WebDriverWait(driver, timeout_seconds).until(
                        EC.presence_of_element_located((By.TAG_NAME, "table"))
                    )
                    
                    # Get raw HTML content
                    raw_html = table.get_attribute('outerHTML')
                    
                    # Get cleaned text content
                    text = table.text.strip()

                    # Create directories for both HTML and text files
                    html_dir = os.path.join(base_dir, "html_easylaw")
                    text_dir = os.path.join(base_dir, "text_easylaw")
                    os.makedirs(html_dir, exist_ok=True)
                    os.makedirs(text_dir, exist_ok=True)

                    # Safe file writing - never interrupt this operation
                    try:
                        # Save raw HTML file
                        html_file_path = os.path.join(html_dir, f"{case_id}.html")
                        with open(html_file_path, "w", encoding="utf-8") as f:
                            f.write(raw_html)
                        print(f"✅ Raw HTML saved: {html_file_path}")
                        
                        # Save cleaned text file
                        text_file_path = os.path.join(text_dir, f"{case_id}.txt")
                        with open(text_file_path, "w", encoding="utf-8") as f:
                            f.write(text)
                        print(f"✅ Cleaned text saved: {text_file_path}")
                        
                        case_count += 1
                        
                        # Track successful scrape for metadata
                        scraped_files.append(case_id)
                        
                        # Update progress callback with case count
                        if progress_callback:
                            progress_callback(
                                current_keyword=keyword,
                                cases_for_keyword=case_count,
                                total_cases=case_count,
                                progress=min(100, (case_count / limit) * 100)
                            )
                        
                        # Check if we've reached the case limit after saving
                        if case_count >= case_limit:
                            print(f"🎯 Case limit reached ({case_limit} cases). Stopping automatically.")
                            stop_reason = "case_limit_reached"
                            break  # Break out of the case loop, but don't return yet
                            
                    except Exception as e:
                        print(f"⚠️ Error saving case files: {e}")
                        issues_count += 1
                        # Continue with next case, don't stop entire process

                except Exception as e:
                    print(f"⚠️ Error scraping case: {e}")
                    issues_count += 1

                # Always close tab and return to main search page
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(delay_between_requests)

            # Check if we need to exit the page loop
            if case_count >= case_limit or (stop_flag and stop_flag.is_set()):
                break  # Exit page loop if limit reached or stop signal received

            # Step 4: Try to go to the next page of search results
            try:
                next_btn = driver.find_element(By.ID, "myTable_next")
                if "disabled" in next_btn.get_attribute("class"):
                    print("📭 No more pages.")
                    break
                else:
                    next_btn.click()
                    print("➡️ Moving to next page...")
                    time.sleep(delay_between_requests)
            except NoSuchElementException:
                print("❓ Next button not found. Moving to next keyword.")
                break

        # Check if we need to exit the keyword loop
        if case_count >= case_limit or (stop_flag and stop_flag.is_set()):
            break  # Exit keyword loop if limit reached or stop signal received

    # Gracefully shut down browser session
    try:
        driver.quit()
        print("✅ Browser session closed successfully")
    except Exception as e:
        print(f"⚠️ Error closing browser session: {e}")
    
    # Capture end time
    end_time = datetime.now()
    
    # Final completion message
    if case_count >= case_limit:
        print(f"\n🎯 Case limit reached ({case_limit} cases). Stopping automatically.")
    elif stop_flag and stop_flag.is_set():
        print(f"\n🛑 Manual stop requested. Stopped at {case_count} cases.")
    else:
        print(f"\n🎉 Scraping completed naturally. Total cases saved: {case_count}")
    
    print(f"📊 Total cases saved as HTML and text files: {case_count}")
    return (case_count, issues_count, scraped_files, start_time, end_time, stop_reason)
