import streamlit as st
import threading
import time
import os
from datetime import datetime
import queue
import sys
from io import StringIO
from pymongo import MongoClient

# Add the project root to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from Extraction.ksa.moj_cases_ksa import scrape_moj_cases_ksa

class StreamlitLogger:
    """Custom logger to capture output for Streamlit"""
    def __init__(self):
        self.log_queue = queue.Queue()
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.string_io = StringIO()
        
    def start_capture(self):
        """Start capturing stdout and stderr"""
        sys.stdout = self.string_io
        sys.stderr = self.string_io
        
    def stop_capture(self):
        """Stop capturing and restore original stdout/stderr"""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
    def get_logs(self):
        """Get captured logs"""
        logs = self.string_io.getvalue()
        self.string_io.truncate(0)
        self.string_io.seek(0)
        return logs

def get_last_metadata(db_name, collection_name):
    """Get the most recent metadata from MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        
        # Get the most recent document
        last_metadata = collection.find_one(
            sort=[("start_timestamp", -1)]
        )
        
        if last_metadata:
            # Remove MongoDB internal fields
            last_metadata.pop("_id", None)
            return last_metadata
        else:
            return None
    except Exception as e:
        print(f"❌ Error retrieving metadata from MongoDB: {e}")
        return None

def initialize_session_state():
    """Initialize session state variables"""
    defaults = {
        'scraping_status': 'idle',
        'scraping_thread': None,
        'thread_started': False,
        'logger': None,
        'logs': '',
        'last_metadata': None,
        'session_start_time': datetime.now(),
        'stop_flag': False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    
    # Load last metadata from MongoDB if not already loaded
    if 'last_metadata' not in st.session_state or st.session_state.last_metadata is None:
        # Use default values for initial load
        default_db_name = st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA')
        default_collection_name = st.session_state.get('metadata_collection_name', 'moj_cases_scrapping')
        last_metadata = get_last_metadata(default_db_name, default_collection_name)
        if last_metadata:
            st.session_state.last_metadata = last_metadata

def main():
    st.set_page_config(
        page_title="MOJ Cases Scraper",
        page_icon="⚖️",
        layout="wide"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Header - Centered
    st.markdown("<h1 style='text-align: center;'>Legal Data Pipeline</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>KSA Laws Scraper</h2>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>For MOJ Cases</h3>", unsafe_allow_html=True)
    
    # Check if scraping is running to disable inputs
    is_scraping = st.session_state.scraping_status == "running"
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Output Directories
        st.subheader("📁 Output Directories")
        # Get absolute paths
        default_html_dir = os.path.abspath(os.path.join("data", "ksa", "raw", "moj_cases_ksa", "raw_html"))
        default_text_dir = os.path.abspath(os.path.join("data", "ksa", "raw", "moj_cases_ksa", "raw_text"))
        
        html_output_dir = st.text_input(
            "HTML Output Directory",
            value=default_html_dir,
            help="Directory where HTML files will be saved",
            disabled=is_scraping
        )
        text_output_dir = st.text_input(
            "Text Output Directory", 
            value=default_text_dir,
            help="Directory where text files will be saved",
            disabled=is_scraping
        )
        
        # Scraping Settings
        st.subheader("🔧 Scraping Settings")
        list_url = st.text_input(
            "List URL",
            value="https://laws.moj.gov.sa/ar/JudicialDecisionsList/0?pageNumber=1&pageSize=12&viewType=grid&sortingBy=2",
            help="Starting URL for the judicial decisions list",
            disabled=is_scraping
        )
        max_cases = st.number_input(
            "Max Cases to Scrape",
            min_value=1,
            max_value=1000,
            value=50,
            help="Maximum number of cases to scrape",
            disabled=is_scraping
        )
        headless = st.checkbox(
            "Headless Mode",
            value=True,
            help="Run browser in headless mode (no GUI)",
            disabled=is_scraping
        )
        
        # MongoDB Configuration
        st.subheader("🗄️ MongoDB Metadata Configuration")
        metadata_db_name = st.text_input(
            "Metadata Database Name",
            value="LawGPT_Metadata_KSA",
            help="MongoDB database name for storing metadata",
            disabled=is_scraping
        )
        metadata_collection_name = st.text_input(
            "Metadata Collection Name",
            value="moj_cases_scrapping",
            help="MongoDB collection name for storing metadata",
            disabled=is_scraping
        )
        
        # Update session state with configuration
        if not is_scraping:
            st.session_state.metadata_db_name = metadata_db_name
            st.session_state.metadata_collection_name = metadata_collection_name
        
        st.markdown("---")
        
        # Last Session Metadata
        st.markdown("### Last Session Metrics")
        
        # Display key metrics - show metadata if available
        if 'last_metadata' in st.session_state and st.session_state.last_metadata:
            metadata = st.session_state.last_metadata
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Cases Scraped", metadata.get('scraped_count', 0))
                st.metric("Duration", f"{metadata.get('duration_seconds', 0):.1f}s")
            with col2:
                st.metric("Status", metadata.get('status', 'unknown'))
                st.metric("Session ID", metadata.get('session_id', 'N/A')[:10] + "...")
            
            # View full metadata button
            if st.button("View Full Metadata", use_container_width=True):
                st.session_state.show_full_metadata = True
            
            # Show full metadata in expandable section
            if st.session_state.get('show_full_metadata', False):
                with st.expander("Full Metadata Details", expanded=True):
                    st.json(metadata)
        else:
            st.info("No metadata available. Run a scraping session to see metrics.")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Control buttons
        button_col1, button_col2 = st.columns(2)
        
        with button_col1:
            if st.button("🚀 Start Scraping", type="primary", disabled=st.session_state.scraping_status == "running"):
                start_scraping(
                    list_url, max_cases, headless, html_output_dir, text_output_dir,
                    metadata_db_name, metadata_collection_name
                )
        
        with button_col2:
            if st.button("🗑️ Clear Log"):
                clear_log()
    
    with col2:
        # Session management
        if st.button("🔄 Reset Session"):
            reset_session()
    
    # Log output
    st.header("Log Output")
    
    # Create a placeholder for logs
    log_placeholder = st.empty()
    
    # Display logs
    if 'logs' in st.session_state:
        log_placeholder.code(st.session_state.logs, language="text")
    
    # Auto-refresh logs
    if 'scraping_status' in st.session_state and st.session_state.scraping_status == "running":
        # Update logs from logger if available
        if 'logger' in st.session_state and st.session_state.logger is not None:
            try:
                logs = st.session_state.logger.get_logs()
                if logs:
                    st.session_state.logs += logs
            except:
                # Logger might be None or in invalid state after stop
                pass
        
        # Check if scraping thread has finished
        if ('scraping_thread' in st.session_state and 
            st.session_state.scraping_thread is not None and 
            not st.session_state.scraping_thread.is_alive()):
            if st.session_state.scraping_status == "running":
                st.session_state.scraping_status = "completed"
                st.rerun()
        
        # Auto-refresh every 1 second during scraping for faster response
        time.sleep(1)
        st.rerun()
    elif 'scraping_status' in st.session_state and st.session_state.scraping_status in ["completed", "error"]:
        # Update logs one final time when scraping is done
        if 'logger' in st.session_state and st.session_state.logger is not None:
            try:
                logs = st.session_state.logger.get_logs()
                if logs:
                    st.session_state.logs += logs
            except:
                # Logger might be None or in invalid state after stop
                pass

def start_scraping(list_url, max_cases, headless, html_output_dir, text_output_dir, metadata_db_name, metadata_collection_name):
    """Start the scraping process"""
    
    # Initialize session state
    st.session_state.scraping_status = "running"
    st.session_state.logs = ""
    st.session_state.start_time = time.time()
    
    # Create logger
    logger = StreamlitLogger()
    logger.start_capture()
    st.session_state.logger = logger
    
    try:
        # Log initial information
        print("🚀 Starting MOJ Cases Scraper...")
        print(f"📊 Configuration: Max cases={max_cases}, Headless={headless}")
        print(f"📁 HTML output: {html_output_dir}")
        print(f"📁 Text output: {text_output_dir}")
        
        # Run scraper in a separate thread
        def run_scraper():
            try:
                # Call the scraper with all configurable parameters
                scrape_moj_cases_ksa(
                    list_url=list_url,
                    max_cases=max_cases,
                    headless=headless,
                    html_output_dir=html_output_dir,
                    text_output_dir=text_output_dir,
                    metadata_db_name=metadata_db_name,
                    metadata_collection_name=metadata_collection_name,
                    logger=logger,
                )
                
                st.session_state.scraping_status = "completed"
                print("🎉 Scraping process completed!")
                
            except Exception as e:
                st.session_state.scraping_status = "error"
                print(f"💥 Scraping error: {str(e)}")
                import traceback
                print(f"💥 Traceback: {traceback.format_exc()}")
            finally:
                # Stop logger capture
                logger.stop_capture()
        
        # Start the scraping thread
        st.session_state.scraping_thread = threading.Thread(target=run_scraper)
        st.session_state.scraping_thread.daemon = True
        st.session_state.scraping_thread.start()
        st.session_state.thread_started = True
        
        # Don't block the UI thread
        st.rerun()
        
    except Exception as e:
        st.session_state.scraping_status = "error"
        st.error(f"Failed to start scraping: {str(e)}")

def clear_log():
    """Clear the log display and metadata"""
    if 'logs' in st.session_state:
        st.session_state.logs = ""
    # Also clear metadata display
    if 'last_metadata' in st.session_state:
        del st.session_state.last_metadata
    if 'show_full_metadata' in st.session_state:
        del st.session_state.show_full_metadata
    st.rerun()

def reset_session():
    """Reset all session state variables"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    initialize_session_state()
    st.rerun()

if __name__ == "__main__":
    main()