import streamlit as st
import threading
import time
import os
from datetime import datetime
import queue
import sys
from io import StringIO
from pymongo import MongoClient

from personal_status_law_scraper import scrape_personal_status_pdf
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from translator.translate_with_gpt import translate_file


class StreamlitLogger:
    """Custom logger to capture output for Streamlit"""
    def __init__(self):
        self.log_queue = queue.Queue()
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.string_io = StringIO()
        self.log_buffer = []
        
    def start_capture(self):
        """Start capturing stdout and stderr"""
        sys.stdout = self.string_io
        sys.stderr = self.string_io
        
    def stop_capture(self):
        """Stop capturing and restore original stdout/stderr"""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
    def get_logs(self):
        """Get captured logs without clearing the buffer"""
        return self.string_io.getvalue()
        
    def get_logs_and_clear(self):
        """Get captured logs and clear the buffer"""
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
        collection.insert_one(metadata_dict)
        return True
    except Exception as e:
        print(f"Error saving metadata: {e}")
        return False


def get_last_metadata(db_name, collection_name):
    """Get the last metadata from MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        last_doc = collection.find_one(sort=[("start_timestamp", -1)])
        return last_doc
    except Exception as e:
        print(f"Error retrieving metadata: {e}")
        return None


def refresh_metadata(db_name, collection_name):
    """Refresh metadata in session state"""
    last_metadata = get_last_metadata(db_name, collection_name)
    if last_metadata:
        st.session_state.last_metadata = last_metadata
    else:
        st.session_state.last_metadata = None


def initialize_session_state():
    """Initialize all session state variables with defaults"""
    defaults = {
        'scraping_status': 'idle',
        'thread_started': False,
        'scraping_thread': None,
        'logs': "",
        'logger': None,
        'stop_flag': threading.Event(),
        'session_start_time': time.time()
    }
    
    # Initialize defaults if not present
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    
    # Check for session timeout (30 minutes of inactivity)
    current_time = time.time()
    session_duration = current_time - st.session_state.get('session_start_time', current_time)
    
    # If session is older than 30 minutes and not currently scraping, reset it
    if session_duration > 1800 and st.session_state.get('scraping_status') != 'running':
        reset_session()
        return
    
    # Load last metadata from MongoDB if not already loaded
    if 'last_metadata' not in st.session_state:
        # Use default values for initial load
        default_db_name = st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA')
        default_collection_name = st.session_state.get('metadata_collection_name', 'personal_status_law_scraping')
        last_metadata = get_last_metadata(default_db_name, default_collection_name)
        if last_metadata:
            st.session_state.last_metadata = last_metadata


def main():
    st.set_page_config(
        page_title="Personal Status Law Scraper",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    initialize_session_state()
    
    # Check if thread finished but status wasn't updated
    if ('scraping_thread' in st.session_state and 
        st.session_state.scraping_thread is not None and 
        not st.session_state.scraping_thread.is_alive()):
        if st.session_state.scraping_status == "running":
            st.session_state.scraping_status = "completed"
            # Refresh metadata when scraping completes
            refresh_metadata(st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA'), 
                           st.session_state.get('metadata_collection_name', 'personal_status_law_scraping'))
            # Update logs one final time when scraping is done
            try:
                if hasattr(st.session_state, 'logger') and st.session_state.logger is not None:
                    logs = st.session_state.logger.get_logs()
                    if logs:
                        st.session_state.logs = logs
            except (KeyError, AttributeError) as e:
                print(f"Error getting logs: {e}")
            
            # Clean up thread references
            st.session_state.scraping_thread = None
            st.session_state.thread_started = False
            
            st.rerun()
    
    # CSS styling
    st.markdown("""
    <style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
        padding: 1rem 0;
        border-bottom: 3px solid #1f77b4;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin: 0.5rem 0;
    }
    .status-running {
        color: #ff6b6b;
        font-weight: bold;
    }
    .status-completed {
        color: #51cf66;
        font-weight: bold;
    }
    .status-idle {
        color: #868e96;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">Legal Data Pipeline</h1>', unsafe_allow_html=True)
    st.markdown('<h2 style="text-align: center; color: #666; margin-bottom: 1rem;">KSA Laws Scraper</h2>', unsafe_allow_html=True)
    st.markdown('<h3 style="text-align: center; color: #888; margin-bottom: 2rem;">For Personal Status Law</h3>', unsafe_allow_html=True)
    
    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")
        is_scraping = st.session_state.get('scraping_status') == "running"
        
        # Show current status
        if is_scraping:
            st.info("🔄 Scraping in progress...")
        elif st.session_state.get('scraping_status') == "completed":
            st.success("✅ Scraping completed")
        elif st.session_state.get('scraping_status') == "error":
            st.error("❌ Scraping failed")
        
        # Output directory configuration
        st.subheader("Output Directories")
        download_dir = st.text_input(
            "PDF Download Directory:",
            value=st.session_state.get('download_dir', "D:\\LawGPT_data_pipeline\\data\\ksa\\raw\\personal_status_law\\raw_download"),
            help="Directory for downloading PDF files"
        )
        
        arabic_text_dir = st.text_input(
            "Arabic Text Directory:",
            value=st.session_state.get('arabic_text_dir', "D:\\LawGPT_data_pipeline\\data\\ksa\\raw\\personal_status_law\\arabic_text"),
            help="Directory for saving extracted Arabic text"
        )
        
        translated_text_dir = st.text_input(
            "Translated Text Directory:",
            value=st.session_state.get('translated_text_dir', "D:\\LawGPT_data_pipeline\\data\\ksa\\raw\\personal_status_law\\translated_text"),
            help="Directory for saving translated English text"
        )
        
        # Scraping settings
        st.subheader("Scraping Settings")
        target_url = st.text_input(
            "Target URL:",
            value=st.session_state.get('target_url', "https://fac.gov.sa/en/legislations-posts/personal-status-system/"),
            help="URL of the personal status law page"
        )
        
        headless_mode = st.checkbox(
            "Headless Mode",
            value=st.session_state.get('headless_mode', False),
            help="Run browser in headless mode"
        )
        
        tesseract_path = st.text_input(
            "Tesseract Path (Optional):",
            value=st.session_state.get('tesseract_path', r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            help="Path to Tesseract executable (optional)"
        )
        
        # Translation settings
        st.subheader("Translation Settings")
        enable_translation = st.checkbox(
            "Enable Translation",
            value=st.session_state.get('enable_translation', True),
            help="Automatically translate Arabic text to English after extraction"
        )
        
        max_input_tokens = st.number_input(
            "Max Input Tokens:",
            min_value=1000,
            max_value=100000,
            value=st.session_state.get('max_input_tokens', 60000),
            help="Maximum tokens per translation request"
        )
        
        # MongoDB metadata configuration
        st.subheader("MongoDB Metadata Configuration")
        metadata_db_name = st.text_input(
            "Metadata Database Name:",
            value=st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA'),
            help="MongoDB database name for metadata"
        )
        
        metadata_collection_name = st.text_input(
            "Metadata Collection Name:",
            value=st.session_state.get('metadata_collection_name', 'personal_status_law_scraping'),
            help="MongoDB collection name for metadata"
        )
        
        # Update session state with configuration
        st.session_state.download_dir = download_dir
        st.session_state.arabic_text_dir = arabic_text_dir
        st.session_state.translated_text_dir = translated_text_dir
        st.session_state.target_url = target_url
        st.session_state.headless_mode = headless_mode
        st.session_state.tesseract_path = tesseract_path
        st.session_state.enable_translation = enable_translation
        st.session_state.max_input_tokens = max_input_tokens
        st.session_state.metadata_db_name = metadata_db_name
        st.session_state.metadata_collection_name = metadata_collection_name
        
        # Last Session Metrics
        if st.session_state.last_metadata:
            st.subheader("Last Session Metrics")
            metadata = st.session_state.last_metadata
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Duration", f"{metadata.get('duration_seconds', 0):.1f}s")
                st.metric("Status", metadata.get('status', 'Unknown'))
            
            with col2:
                st.metric("Scraped", metadata.get('scraped_count', 0))
                st.metric("Skipped", metadata.get('skipped_count', 0))
            
            if st.button("View Full Metadata", key="view_metadata"):
                st.json(metadata)
        
        # Refresh metadata button
        if st.button("Refresh Metadata", key="refresh_metadata"):
            refresh_metadata(metadata_db_name, metadata_collection_name)
            st.rerun()
    
    # Main content area - matching MOJ layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Scraping Control")
        
        # Status display (only show when running or completed)
        status = st.session_state.get('scraping_status', 'idle')
        if status == "running":
            st.markdown('<div style="text-align: center; padding: 1rem; background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 0.5rem; margin: 1rem 0;"><p class="status-running">🔄 Scraping in progress...</p></div>', unsafe_allow_html=True)
        elif status == "completed":
            st.markdown('<div style="text-align: center; padding: 1rem; background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 0.5rem; margin: 1rem 0;"><p class="status-completed">✅ Scraping completed</p></div>', unsafe_allow_html=True)
        
        # Buttons side by side
        col_start, col_clear = st.columns(2)
        
        with col_start:
            start_disabled = is_scraping or not download_dir.strip() or not arabic_text_dir.strip()
            if st.button("Start Scraping", type="primary", use_container_width=True, disabled=start_disabled):
                if not download_dir.strip() or not arabic_text_dir.strip():
                    st.error("Please specify both download and text directories.")
                else:
                    start_scraping(
                        target_url, headless_mode, tesseract_path,
                        download_dir, arabic_text_dir, translated_text_dir,
                        enable_translation, max_input_tokens,
                        metadata_db_name, metadata_collection_name
                    )
        
        with col_clear:
            if st.button("Clear Log", use_container_width=True):
                clear_log()
        
        # Reset Session button below the main buttons
        st.markdown('<div style="margin-top: 1rem;">', unsafe_allow_html=True)
        if st.button("🔄 Reset Session", use_container_width=True, help="Reset all settings and start fresh"):
            reset_session()
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.empty()  # Right spacer for symmetry
    
    # Log Output section
    st.subheader("Log Output")
    
    # Auto-refresh logs when scraping is running
    if st.session_state.get('scraping_status') == "running":
        try:
            if hasattr(st.session_state, 'logger') and st.session_state.logger is not None:
                logs = st.session_state.logger.get_logs()
                if logs:
                    st.session_state.logs = logs
        except (KeyError, AttributeError):
            pass  # Silently handle errors during log capture
    
    # Display logs
    if st.session_state.logs:
        st.text_area("Logs", value=st.session_state.logs, height=400, disabled=False, key="log_display")
    else:
        st.info("No logs available. Start scraping to see output.")
    
    # Auto-refresh when scraping is running
    if st.session_state.get('scraping_status') == "running":
        time.sleep(2)  # Wait 2 seconds before refreshing
        st.rerun()


def start_scraping(target_url, headless_mode, tesseract_path, download_dir, arabic_text_dir, translated_text_dir, enable_translation, max_input_tokens, metadata_db_name, metadata_collection_name):
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
        print(f"Starting Personal Status Law scraper...")
        print(f"Target URL: {target_url}")
        print(f"Headless Mode: {headless_mode}")
        print(f"Download Directory: {download_dir}")
        print(f"Arabic Text Directory: {arabic_text_dir}")
        print(f"Translation Enabled: {enable_translation}")
        
        # Run scraper in a separate thread
        def run_scraper():
            try:
                print("=" * 50)
                print("STEP 1: Starting PDF download and text extraction...")
                print("=" * 50)
                
                # Call the original scraper function
                pdf_path, arabic_text_path = scrape_personal_status_pdf(
                    headless=headless_mode,
                    override_url=target_url,
                    tesseract_path=tesseract_path if tesseract_path.strip() else None,
                    download_dir=download_dir,
                    text_dir=arabic_text_dir,
                    metadata_db_name=metadata_db_name,
                    metadata_collection_name=metadata_collection_name
                )
                
                print("=" * 50)
                print("STEP 1 COMPLETED: PDF download and text extraction")
                print(f"PDF saved to: {pdf_path}")
                print(f"Arabic text saved to: {arabic_text_path}")
                print("=" * 50)
                
                # Translation step
                if enable_translation:
                    print("=" * 50)
                    print("STEP 2: Starting translation process...")
                    print("=" * 50)
                    
                    try:
                        # Check if the Arabic text file exists and has content
                        if not os.path.exists(arabic_text_path):
                            print(f"Error: Arabic text file not found: {arabic_text_path}")
                            raise FileNotFoundError(f"Arabic text file not found: {arabic_text_path}")
                        
                        # Check if the file has content
                        with open(arabic_text_path, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                        
                        if not content:
                            print(f"Warning: Arabic text file is empty: {arabic_text_path}")
                            print("Skipping translation due to empty content")
                        else:
                            print(f"Arabic text file contains {len(content)} characters")
                            print("Starting translation of Arabic text to English...")
                            
                            # Create translated text directory if it doesn't exist
                            os.makedirs(translated_text_dir, exist_ok=True)
                            
                            # Translate the Arabic text file
                            input_file, translated_file = translate_file(
                                arabic_text_path,
                                translated_text_dir,
                                max_input_tokens
                            )
                            
                            print("=" * 50)
                            print("STEP 2 COMPLETED: Translation process")
                            print(f"Translated text saved to: {translated_file}")
                            print("=" * 50)
                        
                    except Exception as e:
                        print(f"Translation failed: {e}")
                        print("Continuing without translation...")
                else:
                    print("Translation is disabled, skipping translation step.")
                
                print("=" * 50)
                print("ALL STEPS COMPLETED SUCCESSFULLY!")
                print("=" * 50)
                
                # Update status only after everything is done
                st.session_state.scraping_status = "completed"
                
            except Exception as e:
                print(f"Scraping failed: {e}")
                st.session_state.scraping_status = "error"
            finally:
                # Stop logging and update final logs
                try:
                    if hasattr(st.session_state, 'logger') and st.session_state.logger:
                        st.session_state.logger.stop_capture()
                        st.session_state.logs = st.session_state.logger.get_logs()
                except (KeyError, AttributeError):
                    # Session state might have been reset, ignore the error
                    pass
        
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
    """Clear logs and metadata from session state"""
    st.session_state.logs = ""
    st.session_state.scraping_status = "idle"
    st.session_state.thread_started = False
    st.session_state.scraping_thread = None
    
    # Stop any running logger
    try:
        if hasattr(st.session_state, 'logger') and st.session_state.logger is not None:
            st.session_state.logger.stop_capture()
            st.session_state.logger = None
    except (KeyError, AttributeError):
        pass
    
    # Also clear metadata display
    if 'last_metadata' in st.session_state:
        del st.session_state.last_metadata
    if 'show_full_metadata' in st.session_state:
        del st.session_state.show_full_metadata
    st.rerun()


def reset_session():
    """Reset the entire session state to start fresh"""
    # Clear all session state variables
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    
    # Reinitialize with defaults
    initialize_session_state()
    st.rerun()


if __name__ == "__main__":
    main()
