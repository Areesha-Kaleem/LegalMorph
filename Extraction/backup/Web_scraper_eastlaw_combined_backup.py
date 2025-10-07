import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import threading

def scrape_eastlaw_judgments(limit=50, output_dir="data/raw/eastlaw", stop_flag=None, progress_callback=None, login_ready_event=None):
    """
    Scrape judgments from EastLaw
    
    Args:
        limit (int): Maximum number of cases to scrape
        output_dir (str): Directory to save scraped data
        stop_flag (threading.Event): Flag to stop scraping
        progress_callback (function): Callback to update progress
        login_ready_event (threading.Event): Event to signal when login is complete
    
    Returns:
        tuple: (cases_count, issues_count, scraped_files, start_time, end_time, stop_reason)
    """
    # Initialize variables
    cases_count = 0
    issues_count = 0
    scraped_files = []
    start_time = datetime.now()
    end_time = datetime.now()
    stop_reason = "completed"
    
    try:
        # Create Chrome options
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--start-maximized')
        
        # Initialize the driver
        driver = webdriver.Chrome(options=chrome_options)
        
        # Navigate to EastLaw
        driver.get("https://www.eastlaw.pk/")
        
        # Wait for manual login
        if login_ready_event:
            print("🔐 Waiting for manual login...")
            login_ready_event.wait()
            print("✅ Login confirmed, proceeding with scraping...")
        
        # Validate login
        try:
            # Wait for user-specific elements that indicate successful login
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "user-profile"))
            )
        except TimeoutException:
            print("❌ Login validation failed")
            driver.quit()
            return cases_count, issues_count, scraped_files, start_time, datetime.now(), "login_failed"
        
        # AGGRESSIVE STOP CHECK - Check before starting main loop
        if stop_flag and stop_flag.is_set():
            print("🛑 STOP SIGNAL RECEIVED - STOPPING BEFORE MAIN LOOP!")
            stop_reason = "manual_stop"
            driver.quit()
            return cases_count, issues_count, scraped_files, start_time, datetime.now(), stop_reason
        
        # Navigate to search page
        search_url = "https://www.eastlaw.pk/Search/Index"
        driver.get(search_url)
        
        # Wait for search results
        try:
            case_links = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td a[href*='/Cases/Detail/']"))
            )
        except TimeoutException:
            print("❌ No search results found")
            driver.quit()
            return cases_count, issues_count, scraped_files, start_time, datetime.now(), "no_results"
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Process each case
        for case_link in case_links:
            # Check stop flag
            if stop_flag and stop_flag.is_set():
                print("🛑 Stop flag detected - stopping gracefully")
                stop_reason = "manual_stop"
                break
            
            # Check case limit
            if cases_count >= limit:
                print(f"🎯 Reached case limit ({limit})")
                stop_reason = "case_limit_reached"
                break
            
            try:
                # Get case URL
                case_url = case_link.get_attribute('href')
                
                # Extract case data
                case_count, case_data = extract_case_data(driver, case_url, stop_flag)
                
                if case_data:
                    # Generate filename
                    filename = f"case_{cases_count + 1}.json"
                    filepath = os.path.join(output_dir, filename)
                    
                    # Save case data
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(case_data, f, ensure_ascii=False, indent=4)
                    
                    # Update counts and lists
                    cases_count += case_count
                    scraped_files.append(filename)
                    
                    # Update progress
                    if progress_callback:
                        progress = (cases_count / limit) * 100
                        progress_callback(
                            current_keyword="",
                            cases_for_keyword=cases_count,
                            total_cases=cases_count,
                            progress=progress
                        )
                    
                    print(f"✅ Saved case {cases_count} to {filename}")
                    
                else:
                    issues_count += 1
                    print(f"⚠️ Failed to extract case data from {case_url}")
                
            except Exception as e:
                issues_count += 1
                print(f"❌ Error processing case: {str(e)}")
                continue
            
            # Small delay between requests
            time.sleep(2)
        
    except Exception as e:
        print(f"❌ Error during scraping: {str(e)}")
        stop_reason = "error"
        issues_count += 1
    
    finally:
        # Close browser
        try:
            if stop_reason in ["error", "manual_stop", "login_failed"]:
                driver.quit()
            else:
                # Just close current tab
                if len(driver.window_handles) > 1:
                    driver.close()
                else:
                    driver.quit()
        except:
            pass
        
        end_time = datetime.now()
    
    return cases_count, issues_count, scraped_files, start_time, end_time, stop_reason

def extract_case_data(driver, case_url, stop_flag=None):
    """Extract data from a single case page"""
    cases_count = 0
    case_data = None
    
    try:
        # STOP CHECK before opening new window
        if stop_flag and stop_flag.is_set():
            print("🛑 STOP SIGNAL RECEIVED - STOPPING BEFORE OPENING CASE WINDOW!")
            return cases_count, None
        
        # Open case in new window
        driver.execute_script(f"window.open('{case_url}');")
        driver.switch_to.window(driver.window_handles[-1])
        
        # Wait for case content
        case_content = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "case-content"))
        )
        
        # Extract case information
        case_data = {
            'url': case_url,
            'title': driver.title,
            'content': case_content.text,
            'scraped_at': datetime.now().isoformat()
        }
        
        cases_count = 1
        
        # Close case window and switch back
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        
    except Exception as e:
        print(f"❌ Error extracting case data: {str(e)}")
        # Ensure we're back on the main window
        try:
            if len(driver.window_handles) > 1:
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
        except:
            pass
    
    return cases_count, case_data

def scrape_eastlaw_statutes(limit=50, output_dir="data/raw/eastlaw", stop_flag=None, progress_callback=None, login_ready_event=None):
    """
    Scrape statutes from EastLaw
    
    Args:
        limit (int): Maximum number of statutes to scrape
        output_dir (str): Directory to save scraped data
        stop_flag (threading.Event): Flag to stop scraping
        progress_callback (function): Callback to update progress
        login_ready_event (threading.Event): Event to signal when login is complete
    
    Returns:
        tuple: (statutes_count, issues_count, scraped_files, start_time, end_time, stop_reason)
    """
    # Initialize variables
    statutes_count = 0
    issues_count = 0
    scraped_files = []
    start_time = datetime.now()
    end_time = datetime.now()
    stop_reason = "completed"
    
    try:
        # Create Chrome options
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--start-maximized')
        
        # Initialize the driver
        driver = webdriver.Chrome(options=chrome_options)
        
        # Navigate to EastLaw
        driver.get("https://www.eastlaw.pk/")
        
        # Wait for manual login
        if login_ready_event:
            print("🔐 Waiting for manual login...")
            login_ready_event.wait()
            print("✅ Login confirmed, proceeding with scraping...")
        
        # Validate login
        try:
            # Wait for user-specific elements that indicate successful login
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "user-profile"))
            )
        except TimeoutException:
            print("❌ Login validation failed")
            driver.quit()
            return statutes_count, issues_count, scraped_files, start_time, datetime.now(), "login_failed"
        
        # Navigate to statutes page
        statutes_url = "https://www.eastlaw.pk/Statutes/Index"
        driver.get(statutes_url)
        
        # Wait for statute links
        try:
            statute_links = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td a[href*='/Statutes/Detail/']"))
            )
        except TimeoutException:
            print("❌ No statutes found")
            driver.quit()
            return statutes_count, issues_count, scraped_files, start_time, datetime.now(), "no_results"
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Process each statute
        for statute_link in statute_links:
            # Check stop flag
            if stop_flag and stop_flag.is_set():
                print("🛑 Stop flag detected - stopping gracefully")
                stop_reason = "manual_stop"
                break
            
            # Check statute limit
            if statutes_count >= limit:
                print(f"🎯 Reached statute limit ({limit})")
                stop_reason = "statute_limit_reached"
                break
            
            try:
                # Get statute URL
                statute_url = statute_link.get_attribute('href')
                
                # Open statute in new window
                driver.execute_script(f"window.open('{statute_url}');")
                driver.switch_to.window(driver.window_handles[-1])
                
                # Wait for statute content
                statute_content = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "statute-content"))
                )
                
                # Extract statute information
                statute_data = {
                    'url': statute_url,
                    'title': driver.title,
                    'content': statute_content.text,
                    'scraped_at': datetime.now().isoformat()
                }
                
                # Generate filename
                filename = f"statute_{statutes_count + 1}.json"
                filepath = os.path.join(output_dir, filename)
                
                # Save statute data
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(statute_data, f, ensure_ascii=False, indent=4)
                
                # Update counts and lists
                statutes_count += 1
                scraped_files.append(filename)
                
                # Update progress
                if progress_callback:
                    progress = (statutes_count / limit) * 100
                    progress_callback(
                        current_keyword="",
                        cases_for_keyword=statutes_count,
                        total_cases=statutes_count,
                        progress=progress
                    )
                
                print(f"✅ Saved statute {statutes_count} to {filename}")
                
                # Close statute window and switch back
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                
            except Exception as e:
                issues_count += 1
                print(f"❌ Error processing statute: {str(e)}")
                # Ensure we're back on the main window
                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                except:
                    pass
                continue
            
            # Small delay between requests
            time.sleep(2)
        
    except Exception as e:
        print(f"❌ Error during scraping: {str(e)}")
        stop_reason = "error"
        issues_count += 1
    
    finally:
        # Close browser
        try:
            if stop_reason in ["error", "manual_stop", "login_failed"]:
                driver.quit()
            else:
                # Just close current tab
                if len(driver.window_handles) > 1:
                    driver.close()
                else:
                    driver.quit()
        except:
            pass
        
        end_time = datetime.now()
    
    return statutes_count, issues_count, scraped_files, start_time, end_time, stop_reason
