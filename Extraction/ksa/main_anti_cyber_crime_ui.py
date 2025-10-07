import streamlit as st
import threading
import time
import os
from datetime import datetime
import queue
import sys
from io import StringIO
from pymongo import MongoClient

# Import the scraper function
from anti_cyber_crime_scraper import scrape_anti_cyber_crime_law

# MongoDB Configuration - Now configurable through UI

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

def save_metadata(metadata_dict, db_name, collection_name):
    """Save metadata to MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        
        # Add timestamp for document ordering
        metadata_dict["created_at"] = datetime.now()
        
        # Insert metadata
        result = collection.insert_one(metadata_dict)
        print(f"✅ Metadata saved to MongoDB: {result.inserted_id}")
        return True
    except Exception as e:
        print(f"❌ Error saving metadata to MongoDB: {e}")
        return False

def get_last_metadata(db_name, collection_name):
    """Get the most recent metadata from MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        
        # Get the most recent document
        last_metadata = collection.find_one(
            sort=[("created_at", -1)]
        )
        
        if last_metadata:
            # Remove MongoDB internal fields
            last_metadata.pop("_id", None)
            last_metadata.pop("created_at", None)
            return last_metadata
        else:
            return None
    except Exception as e:
        print(f"❌ Error retrieving metadata from MongoDB: {e}")
        return None

def refresh_metadata(db_name, collection_name):
    """Refresh metadata from MongoDB and update session state"""
    try:
        last_metadata = get_last_metadata(db_name, collection_name)
        if last_metadata:
            st.session_state.last_metadata = last_metadata
            print(f"🔍 Debug: Refreshed metadata for Anti-Cyber Crime Law")
            return True
        else:
            # Clear metadata if none found
            if 'last_metadata' in st.session_state:
                del st.session_state.last_metadata
            print("🔍 Debug: No metadata found in MongoDB")
            return False
    except Exception as e:
        print(f"❌ Error refreshing metadata: {e}")
        return False

def initialize_session_state():
    """Initialize all session state variables with defaults"""
    defaults = {
        'scraping_status': 'idle',
        'thread_started': False,
        'scraping_thread': None,
        'logs': "",
        'logger': None,
        'stop_flag': threading.Event()
    }
    
    # Initialize defaults if not present
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    
    # Load last metadata from MongoDB if not already loaded
    if 'last_metadata' not in st.session_state:
        # Use default values for initial load
        default_db_name = st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA')
        default_collection_name = st.session_state.get('metadata_collection_name', 'anti_cyber_crime_scraping')
        last_metadata = get_last_metadata(default_db_name, default_collection_name)
        if last_metadata:
            st.session_state.last_metadata = last_metadata

def main():
    st.set_page_config(
        page_title="KSA Anti-Cyber Crime Law Scraper",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Check if thread finished but status wasn't updated
    if ('scraping_thread' in st.session_state and 
        st.session_state.scraping_thread is not None and 
        not st.session_state.scraping_thread.is_alive()):
        if 'scraping_status' in st.session_state and st.session_state.scraping_status == "running":
            st.session_state.scraping_status = "completed"
            # Refresh metadata when scraping completes
            refresh_metadata(st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA'), 
                           st.session_state.get('metadata_collection_name', 'anti_cyber_crime_scraping'))
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .status-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">Legal Data Pipeline</h1>', unsafe_allow_html=True)
    st.markdown('<h2 style="text-align: center; color: #666; margin-bottom: 1rem;">KSA Laws Scraper</h2>', unsafe_allow_html=True)
    st.markdown('<h3 style="text-align: center; color: #888; margin-bottom: 2rem;">For Anti-Cyber Crimes</h3>', unsafe_allow_html=True)
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        
        # Check if scraping is running to disable all controls
        is_scraping = st.session_state.get('scraping_status') == "running"
        
        # Output directory configuration
        st.subheader("Output Directories")
        html_output_dir = st.text_input(
            "HTML Output Directory:",
            value=st.session_state.get('html_output_dir', "D:\\LawGPT_data_pipeline\\data\\ksa\\raw\\anti_cyber_crime\\raw_html"),
            disabled=is_scraping,
            help="Directory for saving HTML files" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        text_output_dir = st.text_input(
            "Text Output Directory:",
            value=st.session_state.get('text_output_dir', "D:\\LawGPT_data_pipeline\\data\\ksa\\raw\\anti_cyber_crime\\raw_text"),
            disabled=is_scraping,
            help="Directory for saving text files" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Target URL
        st.subheader("Scraping Settings")
        target_url = st.text_input(
            "Target URL:",
            value=st.session_state.get('target_url', "https://laws.boe.gov.sa/BoeLaws/Laws/LawDetails/25df73d6-0f49-4dc5-b010-a9a700f2ec1d/2"),
            disabled=is_scraping,
            help="URL of the Anti-Cyber Crime Law page" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Headless mode
        headless_mode = st.checkbox(
            "Headless Mode",
            value=st.session_state.get('headless_mode', False),
            disabled=is_scraping,
            help="Run browser in headless mode (no visible window)" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # MongoDB Metadata Configuration
        st.subheader("MongoDB Metadata Configuration")
        metadata_db_name = st.text_input(
            "Metadata Database Name:",
            value=st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA'),
            disabled=is_scraping,
            help="MongoDB database name for storing metadata" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        metadata_collection_name = st.text_input(
            "Metadata Collection Name:",
            value=st.session_state.get('metadata_collection_name', 'anti_cyber_crime_scraping'),
            disabled=is_scraping,
            help="MongoDB collection name for storing metadata" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Update session state with configuration
        if not is_scraping:
            st.session_state.html_output_dir = html_output_dir
            st.session_state.text_output_dir = text_output_dir
            st.session_state.target_url = target_url
            st.session_state.headless_mode = headless_mode
            st.session_state.metadata_db_name = metadata_db_name
            st.session_state.metadata_collection_name = metadata_collection_name
        
        st.markdown("---")
        
        # Last Session Metadata
        st.markdown("### Last Session Metrics")
        
        # Display key metrics - show metadata if available
        if 'last_metadata' in st.session_state:
            metadata = st.session_state.last_metadata
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Items Scraped", metadata.get('scraped_count', 0))
                st.metric("Duration", f"{metadata.get('duration_seconds', 0):.1f}s")
            with col2:
                st.metric("Status", metadata.get('status', 'unknown'))
                st.metric("Session ID", metadata.get('session_id', 'N/A')[:10] + "...")
            
            # View full metadata button
            if st.button("View Full Metadata", use_container_width=True):
                # Refresh metadata before showing
                refresh_metadata(metadata_db_name, metadata_collection_name)
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
        st.header("Scraping Control")
        
        # Control buttons
        col_start, col_clear = st.columns(2)
        
        with col_start:
            # Disable start while scraping
            start_disabled = st.session_state.get('scraping_status') == "running"
            if st.button("Start Scraping", type="primary", use_container_width=True, disabled=start_disabled):
                if not html_output_dir.strip() or not text_output_dir.strip():
                    st.error("Please specify both HTML and Text output directories.")
                else:
                    start_scraping(target_url, headless_mode, html_output_dir, text_output_dir, metadata_db_name, metadata_collection_name)
        
        with col_clear:
            if st.button("Clear Log", use_container_width=True):
                clear_log()
        
        # Progress and status
        if 'scraping_status' in st.session_state:
            status = st.session_state.scraping_status
            
            status_messages = {
                "running": {
                    "message": "Scraping Anti-Cyber Crime Law in progress...",
                    "class": "info-box"
                },
                "completed": {
                    "message": "Scraping completed successfully! Check the sidebar for detailed metrics.",
                    "class": "success-box"
                },
                "error": {
                    "message": "Error occurred during scraping. Check logs for details.",
                    "class": "error-box"
                }
            }
            
            # Get status message and class
            status_info = status_messages.get(status, {
                "message": f"Unknown status: {status}",
                "class": "warning-box"
            })
            
            # Display status message
            st.markdown(
                f'<div class="status-box {status_info["class"]}">{status_info["message"]}</div>',
                unsafe_allow_html=True
            )
    
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

def start_scraping(target_url, headless_mode, html_output_dir, text_output_dir, metadata_db_name, metadata_collection_name):
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
        print(f"Starting Anti-Cyber Crime Law scraper...")
        print(f"Target URL: {target_url}")
        print(f"Headless Mode: {headless_mode}")
        print(f"HTML Output Directory: {html_output_dir}")
        print(f"Text Output Directory: {text_output_dir}")
        
        # Run scraper in a separate thread
        def run_scraper():
            try:
                # Call the original scraper function
                html_path, text_path = scrape_anti_cyber_crime_law(
                    url=target_url,
                    headless=headless_mode,
                    html_output_dir=html_output_dir,
                    text_output_dir=text_output_dir
                )
                
                st.session_state.scraping_status = "completed"
                print(f"Scraping completed successfully!")
                print(f"HTML saved to: {html_path}")
                print(f"Text saved to: {text_path}")
                
            except Exception as e:
                st.session_state.scraping_status = "error"
                print(f"Error during scraping: {str(e)}")
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

if __name__ == "__main__":
    main()
