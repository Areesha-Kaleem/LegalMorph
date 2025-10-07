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
from saudilegal import scrape_saudilegal

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
            print(f"🔍 Debug: Refreshed metadata for SaudiLegal Overview")
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
        default_collection_name = st.session_state.get('metadata_collection_name', 'saudilegal_scrapping')
        last_metadata = get_last_metadata(default_db_name, default_collection_name)
        if last_metadata:
            st.session_state.last_metadata = last_metadata

def main():
    st.set_page_config(
        page_title="SaudiLegal Overview Scraper",
        page_icon="⚖️",
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
                           st.session_state.get('metadata_collection_name', 'saudilegal_scrapping'))
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
    st.markdown('<h3 style="text-align: center; color: #888; margin-bottom: 2rem;">For SaudiLegal Overview</h3>', unsafe_allow_html=True)
    
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
        html_output_dir = st.text_input(
            "HTML Output Directory:",
            value=st.session_state.get('html_output_dir', "D:\\LawGPT_data_pipeline\\data\\ksa\\raw\\saudilegal\\raw_html"),
            help="Directory for saving HTML files"
        )
        
        text_output_dir = st.text_input(
            "Text Output Directory:",
            value=st.session_state.get('text_output_dir', "D:\\LawGPT_data_pipeline\\data\\ksa\\raw\\saudilegal\\raw_text"),
            help="Directory for saving text files"
        )
        
        # Scraping settings
        st.subheader("Scraping Settings")
        base_url = st.text_input(
            "Base URL:",
            value=st.session_state.get('base_url', "https://www.saudilegal.com/saudi-law-overview/real-estate"),
            help="Starting URL for scraping"
        )
        
        headless_mode = st.checkbox(
            "Headless Mode",
            value=st.session_state.get('headless_mode', False),
            help="Run browser in headless mode"
        )
        
        # Exclusions configuration
        st.subheader("Excluded Pages")
        st.write("Pages to skip during scraping:")
        
        # Default exclusions
        default_exclusions = ["doing-business-in-saudi-arabia", "dispute-resolution"]
        current_exclusions = st.session_state.get('exclusions', default_exclusions)
        
        # Display current exclusions
        for i, exclusion in enumerate(current_exclusions):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.text_input(f"Exclusion {i+1}:", value=exclusion, key=f"exclusion_{i}", disabled=True)
            with col2:
                if st.button("🗑️", key=f"remove_{i}", help="Remove this exclusion"):
                    current_exclusions.remove(exclusion)
                    st.session_state.exclusions = current_exclusions
                    st.rerun()
        
        # Add new exclusion
        new_exclusion = st.text_input("Add new exclusion:", placeholder="Enter page slug to exclude")
        if st.button("Add Exclusion") and new_exclusion.strip():
            if new_exclusion.strip() not in current_exclusions:
                current_exclusions.append(new_exclusion.strip())
                st.session_state.exclusions = current_exclusions
                st.rerun()
        
        # MongoDB metadata configuration
        st.subheader("MongoDB Metadata Configuration")
        metadata_db_name = st.text_input(
            "Metadata Database Name:",
            value=st.session_state.get('metadata_db_name', 'LawGPT_Metadata_KSA'),
            help="MongoDB database name for metadata"
        )
        
        metadata_collection_name = st.text_input(
            "Metadata Collection Name:",
            value=st.session_state.get('metadata_collection_name', 'saudilegal_scrapping'),
            help="MongoDB collection name for metadata"
        )
        
        # Update session state with configuration
        st.session_state.html_output_dir = html_output_dir
        st.session_state.text_output_dir = text_output_dir
        st.session_state.base_url = base_url
        st.session_state.headless_mode = headless_mode
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
            start_disabled = is_scraping or not html_output_dir.strip() or not text_output_dir.strip()
            if st.button("Start Scraping", type="primary", use_container_width=True, disabled=start_disabled):
                if not html_output_dir.strip() or not text_output_dir.strip():
                    st.error("Please specify both HTML and text output directories.")
                else:
                    start_scraping(
                        base_url, headless_mode, html_output_dir, text_output_dir,
                        current_exclusions, metadata_db_name, metadata_collection_name
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


def start_scraping(base_url, headless_mode, html_output_dir, text_output_dir, exclusions, metadata_db_name, metadata_collection_name):
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
        print(f"Starting SaudiLegal Overview scraper...")
        print(f"Base URL: {base_url}")
        print(f"Headless Mode: {headless_mode}")
        print(f"HTML Output Directory: {html_output_dir}")
        print(f"Text Output Directory: {text_output_dir}")
        print(f"Excluded Pages: {exclusions}")
        
        # Run scraper in a separate thread
        def run_scraper():
            try:
                print("=" * 50)
                print("Starting SaudiLegal Overview scraping...")
                print("=" * 50)
                
                # Call the scraper with all configurable parameters
                scrape_saudilegal(
                    headless=headless_mode,
                    base_url=base_url,
                    html_output_dir=html_output_dir,
                    text_output_dir=text_output_dir,
                    exclusions=exclusions,
                    metadata_db_name=metadata_db_name,
                    metadata_collection_name=metadata_collection_name
                )
                
                print("=" * 50)
                print("SaudiLegal Overview scraping completed successfully!")
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
