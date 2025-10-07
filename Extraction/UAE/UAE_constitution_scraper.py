from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import time
import os
import pymongo
from datetime import datetime

def setup_driver(headless=True):
    """Setup Chrome WebDriver with anti-detection options."""
    options = Options()
    
    if headless:
        options.add_argument("--headless")
    
    # Anti-detection options
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"❌ Failed to initialize WebDriver: {e}")
        return None

def save_metadata_to_db(metadata):
    """Save scraping metadata to MongoDB."""
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client["LawGPT_Metadata_UAE"]
        collection = db["uae_constitution_scraping"]
        
        # Convert datetime objects to string for MongoDB storage
        metadata_copy = metadata.copy()
        if 'start_timestamp' in metadata_copy:
            metadata_copy['start_timestamp'] = metadata_copy['start_timestamp'].isoformat()
        if 'end_timestamp' in metadata_copy:
            metadata_copy['end_timestamp'] = metadata_copy['end_timestamp'].isoformat()
        
        # Insert metadata
        result = collection.insert_one(metadata_copy)
        print(f"✅ Metadata saved to database with ID: {result.inserted_id}")
        
    except Exception as e:
        print(f"❌ Failed to save metadata to database: {e}")

def scrape_uae_constitution(url="https://uaecabinet.ae/en/the-constitution", 
                           output_dir="data/uae/raw/uae_constitution",
                           html_filename="The_Constitution_of_UAE.html",
                           txt_filename="The_Constitution_of_UAE.txt",
                           headless=True,
                           wait_time=5):
    """
    Scrape UAE Constitution and save to specified directory.
    
    Args:
        url (str): Source URL to scrape
        output_dir (str): Output directory path
        html_filename (str): HTML filename
        txt_filename (str): Text filename
        headless (bool): Run browser in headless mode
        wait_time (int): Time to wait for page load
    """
    
    # Initialize metadata
    start_time = datetime.now()
    metadata = {
        'start_timestamp': start_time,
        'url': url,
        'output_dir': output_dir,
        'html_filename': html_filename,
        'txt_filename': txt_filename,
        'headless': headless,
        'wait_time': wait_time,
        'status': 'running'
    }
    
    print(f"🚀 Starting UAE Constitution Scraper at {start_time}")
    print(f"📋 Configuration:")
    print(f"   URL: {url}")
    print(f"   Output Directory: {output_dir}")
    print(f"   HTML File: {html_filename}")
    print(f"   Text File: {txt_filename}")
    print(f"   Headless Mode: {headless}")
    print(f"   Wait Time: {wait_time}s")
    
    # Create directory structure with separate folders for HTML and text
    print(f"📁 Creating directory structure: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Create separate subdirectories for HTML and text files
    html_dir = os.path.join(output_dir, "raw_html")
    text_dir = os.path.join(output_dir, "raw_text")
    
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    
    print(f"📁 Created HTML directory: {html_dir}")
    print(f"📁 Created text directory: {text_dir}")
    
    # File paths
    html_file = os.path.join(html_dir, html_filename)
    txt_file = os.path.join(text_dir, txt_filename)
    
    driver = None
    
    try:
        print(f"🌐 Loading UAE Constitution: {url}")
        
        # Setup driver
        print(f"🔧 Setting up Chrome WebDriver (headless={headless})...")
        driver = setup_driver(headless=headless)
        if not driver:
            metadata['stopping_reason'] = 'Failed to initialize WebDriver'
            metadata['status'] = 'failed'
            return False
        
        # Navigate to URL
        print(f"🌐 Navigating to URL: {url}")
        driver.get(url)
        
        # Wait for page to load
        print(f"⏳ Waiting {wait_time} seconds for page to load...")
        time.sleep(wait_time)
        
        # Wait for body element
        print("🔍 Checking for page body element...")
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            print("✅ Page body element found")
        except TimeoutException:
            print("⚠️  Timeout waiting for page to load, but continuing...")
        
        # Get the page source
        print("📄 Extracting page source...")
        html_content = driver.page_source
        
        # Save raw HTML
        print(f"💾 Saving HTML to: {html_file}")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ HTML saved successfully")
        print(f"📄 HTML content length: {len(html_content):,} characters")
        
        # Extract and clean text
        print("🧹 Extracting and cleaning text content...")
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        print("🗑️  Removing script and style elements...")
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        print("📝 Extracting text content...")
        text_content = soup.get_text()
        
        # Clean up the text
        print("✨ Cleaning up text formatting...")
        lines = (line.strip() for line in text_content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text_content = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Save cleaned text
        print(f"💾 Saving text to: {txt_file}")
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        print(f"✅ Text saved successfully")
        print(f"📝 Text content length: {len(text_content):,} characters")
        
        # Update metadata for success
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        metadata.update({
            'end_timestamp': end_time,
            'duration_seconds': duration,
            'html_file_path': html_file,
            'txt_file_path': txt_file,
            'html_content_length': len(html_content),
            'text_content_length': len(text_content),
            'stopping_reason': 'Successfully completed',
            'status': 'completed'
        })
        
        print(f"⏱️  Scraping completed in {duration:.2f} seconds")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
        # Update metadata for failure
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        metadata.update({
            'end_timestamp': end_time,
            'duration_seconds': duration,
            'stopping_reason': f'Error: {str(e)}',
            'status': 'failed'
        })
        
        return False
        
    finally:
        if driver:
            driver.quit()
            print("🔒 WebDriver closed")
        
        # Save metadata to database
        print("💾 Saving metadata to database...")
        save_metadata_to_db(metadata)

if __name__ == "__main__":
    print("🚀 Starting UAE Constitution Scraper...")
    success = scrape_uae_constitution()
    
    if success:
        print("✅ UAE Constitution scraping completed successfully!")
    else:
        print("❌ UAE Constitution scraping failed!")
