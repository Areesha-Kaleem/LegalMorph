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
from Web_scraper_easyLaw import scraper_easylaw

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
            print(f"🔍 Debug: Refreshed metadata for EasyLaw")
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

def main():
    st.set_page_config(
        page_title="EasyLaw Web Scraper",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load last metadata from MongoDB if not already loaded
    if 'last_metadata' not in st.session_state:
        last_metadata = get_last_metadata()
        if last_metadata:
            st.session_state.last_metadata = last_metadata
    
    # Check if thread finished but status wasn't updated
    if 'scraping_thread' in st.session_state and not st.session_state.scraping_thread.is_alive():
        if 'scraping_status' in st.session_state and st.session_state.scraping_status == "running":
            st.session_state.scraping_status = "completed"
            # Refresh metadata when scraping completes
            refresh_metadata()
    
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
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">Legal Data Pipeline</h1>', unsafe_allow_html=True)
    st.markdown('<h2 style="text-align: center; color: #666; margin-bottom: 2rem;">EasyLaw Web Scraper</h2>', unsafe_allow_html=True)
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        
        # Check if scraping is running to disable all controls
        is_scraping = st.session_state.get('scraping_status') == "running"
        
        # Case limit input
        case_limit = st.number_input(
            "Number of Cases to Scrape:",
            min_value=1,
            max_value=1000,
            value=50,
            disabled=is_scraping,
            help="Total number of unique cases to scrape across all keywords" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Output directory
        output_dir = st.text_input(
            "Output Directory:",
            value="D:\\LawGPT_data_pipeline\\data\\raw\\easylaw",
            disabled=is_scraping,
            help="Directory where scraped case files will be saved" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Keywords selection
        st.subheader("Search Keywords")
        
        # Initialize session state for keywords if not exists
        if 'custom_keywords' not in st.session_state:
            st.session_state.custom_keywords = ["murder", "land dispute", "domestic violence", "corruption", "divorce", "education"]
        
        # Add new keyword
        col_add, col_add_btn = st.columns([3, 1])
        with col_add:
            new_keyword = st.text_input(
                "Add new keyword:",
                placeholder="Enter keyword to add",
                disabled=is_scraping,
                help="Type a new keyword and click Add" + (" (Locked during scraping)" if is_scraping else "")
            )
        with col_add_btn:
            if st.button("Add", use_container_width=True, disabled=is_scraping):
                if new_keyword.strip() and new_keyword.strip() not in st.session_state.custom_keywords:
                    st.session_state.custom_keywords.append(new_keyword.strip())
                    st.success(f"Added keyword: {new_keyword.strip()}")
                    st.rerun()
                elif new_keyword.strip() in st.session_state.custom_keywords:
                    st.error("Keyword already exists!")
        
        # Display and select keywords
        selected_keywords = st.multiselect(
            "Select keywords to search:",
            options=st.session_state.custom_keywords,
            default=st.session_state.custom_keywords,
            disabled=is_scraping,
            help="Keywords to search for on EasyLaw" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Remove keyword functionality
        if st.session_state.custom_keywords:
            keyword_to_remove = st.selectbox(
                "Remove keyword:",
                options=st.session_state.custom_keywords,
                disabled=is_scraping,
                help="Select a keyword to remove" + (" (Locked during scraping)" if is_scraping else "")
            )
            if st.button("Remove Selected", use_container_width=True, disabled=is_scraping):
                st.session_state.custom_keywords.remove(keyword_to_remove)
                st.success(f"Removed keyword: {keyword_to_remove}")
                st.rerun()
        
        # Advanced options
        with st.expander("Advanced Options"):
            delay_between_requests = st.slider(
                "Delay between requests (seconds):",
                min_value=1,
                max_value=10,
                value=2,
                disabled=is_scraping,
                help="Delay to avoid overwhelming the server" + (" (Locked during scraping)" if is_scraping else "")
            )
            
            timeout_seconds = st.number_input(
                "Timeout (seconds):",
                min_value=5,
                max_value=60,
                value=15,
                disabled=is_scraping,
                help="Timeout for web requests" + (" (Locked during scraping)" if is_scraping else "")
            )
        
        # MongoDB Metadata Configuration
        st.subheader("MongoDB Metadata Configuration")
        metadata_db_name = st.text_input(
            "Metadata Database Name:",
            value=st.session_state.get('metadata_db_name', 'lawgpt_metadata'),
            disabled=is_scraping,
            help="MongoDB database name for storing metadata" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        metadata_collection_name = st.text_input(
            "Metadata Collection Name:",
            value=st.session_state.get('metadata_collection_name', 'easylaw_sessions'),
            disabled=is_scraping,
            help="MongoDB collection name for storing metadata" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Update session state with metadata configuration
        if not is_scraping:
            st.session_state.metadata_db_name = metadata_db_name
            st.session_state.metadata_collection_name = metadata_collection_name
        
        st.markdown("---")
        st.markdown("### Statistics")
        if 'total_cases_scraped' in st.session_state:
            st.metric("Total Cases Scraped", st.session_state.total_cases_scraped)
        if 'scraping_time' in st.session_state:
            st.metric("Scraping Time", f"{st.session_state.scraping_time:.2f}s")
        
        # Current Session Metadata
        if 'scraping_status' in st.session_state and st.session_state.scraping_status in ["completed", "completed_limit", "stopped", "error"]:
            # Auto-refresh metadata when scraping completes
            if 'metadata_refreshed' not in st.session_state:
                refresh_metadata(metadata_db_name, metadata_collection_name)
                st.session_state.metadata_refreshed = True
            elif st.session_state.scraping_status not in ["completed", "completed_limit", "stopped", "error"]:
                # Reset refresh flag when starting new session
                if 'metadata_refreshed' in st.session_state:
                    del st.session_state.metadata_refreshed
            
            st.markdown("### Last Session Metrics")
            
            # Display key metrics
            if 'last_metadata' in st.session_state:
                metadata = st.session_state.last_metadata
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Cases Scraped", metadata.get('total_cases_scraped', 0))
                    st.metric("Issues", metadata.get('issues_count', 0))
                with col2:
                    st.metric("Duration", f"{metadata.get('scraping_duration', 0):.1f}s")
                    st.metric("Stop Reason", metadata.get('stop_reason', 'unknown'))
                
                # View full metadata button
                if st.button("View Full Metadata", use_container_width=True):
                    st.session_state.show_full_metadata = True
                
                # Refresh metadata button
                if st.button("Refresh Metadata", use_container_width=True):
                    refresh_metadata(metadata_db_name, metadata_collection_name)
                    st.rerun()
                
                # Show full metadata in expandable section
                if st.session_state.get('show_full_metadata', False):
                    with st.expander("Full Metadata Details", expanded=True):
                        st.json(metadata)
            else:
                # Fallback to old metrics if metadata not available
                if 'total_cases_scraped' in st.session_state:
                    st.metric("Cases Scraped", st.session_state.total_cases_scraped)
                if 'scraping_time' in st.session_state:
                    st.metric("Duration", f"{st.session_state.scraping_time:.1f}s")
        else:
            st.info("Session metadata will appear after scraping")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("Scraping Control")
        
        # Control buttons
        col_start, col_stop, col_clear = st.columns(3)
        
        with col_start:
            start_disabled = st.session_state.get('scraping_status') == "running"
            if st.button("Start Scraping", type="primary", use_container_width=True, disabled=start_disabled):
                if not selected_keywords:
                    st.error("Please select at least one keyword to search for.")
                else:
                    start_scraping(case_limit, output_dir, selected_keywords, delay_between_requests, timeout_seconds, metadata_db_name, metadata_collection_name)
        
        with col_stop:
            stop_enabled = st.session_state.get('scraping_status') == "running"
            if st.button("Stop Scraping", use_container_width=True, disabled=not stop_enabled):
                stop_scraping()
        
        with col_clear:
            if st.button("Clear Log", use_container_width=True):
                clear_log()
        
        # Progress and status
        if 'scraping_status' in st.session_state:
            status = st.session_state.scraping_status
            if status == "running":
                st.markdown('<div class="status-box info-box">🔄 Scraping in progress...</div>', unsafe_allow_html=True)
            elif status == "stopping":
                st.markdown('<div class="status-box info-box">⏹️ Stopping scraper (completing current case)...</div>', unsafe_allow_html=True)
            elif status == "completed":
                st.markdown('<div class="status-box success-box">✅ Scraping completed successfully!</div>', unsafe_allow_html=True)
            elif status == "completed_limit":
                st.markdown('<div class="status-box success-box">🎯 Case limit reached - scraping completed!</div>', unsafe_allow_html=True)
            elif status == "error":
                st.markdown('<div class="status-box error-box">❌ Error occurred during scraping</div>', unsafe_allow_html=True)
            elif status == "stopped":
                st.markdown('<div class="status-box info-box">⏹️ Scraping stopped by user</div>', unsafe_allow_html=True)
    
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
        if 'logger' in st.session_state:
            logs = st.session_state.logger.get_logs()
            if logs:
                st.session_state.logs += logs
        
        # Check if scraping thread has finished
        if 'scraping_thread' in st.session_state and not st.session_state.scraping_thread.is_alive():
            # Thread finished but status wasn't updated, force update
            if st.session_state.scraping_status == "running":
                st.session_state.scraping_status = "completed"
        
        # Auto-refresh every 2 seconds during scraping
        time.sleep(2)
        st.rerun()
    elif 'scraping_status' in st.session_state and st.session_state.scraping_status in ["completed", "completed_limit", "stopped", "error"]:
        # Update logs one final time when scraping is done
        if 'logger' in st.session_state:
            logs = st.session_state.logger.get_logs()
            if logs:
                st.session_state.logs += logs
    
    # Always check if thread finished regardless of status
    if 'scraping_thread' in st.session_state and not st.session_state.scraping_thread.is_alive():
        if 'scraping_status' in st.session_state and st.session_state.scraping_status == "running":
            st.session_state.scraping_status = "completed"
            st.rerun()

def start_scraping(case_limit, output_dir, keywords, delay_between_requests, timeout_seconds, metadata_db_name, metadata_collection_name):
    """Start the scraping process with parameter freezing"""
    # Initialize session state
    st.session_state.scraping_status = "running"
    st.session_state.progress = 0
    st.session_state.cases_scraped = 0
    st.session_state.current_keyword = ""
    st.session_state.cases_for_keyword = 0
    st.session_state.logs = ""
    st.session_state.start_time = time.time()
    
    # Create thread-safe stop flag
    st.session_state.stop_flag = threading.Event()
    
    # FREEZE ALL PARAMETERS at start time
    st.session_state.frozen_params = {
        'case_limit': case_limit,
        'output_dir': output_dir,
        'keywords': keywords,
        'delay_between_requests': delay_between_requests,
        'timeout_seconds': timeout_seconds
    }
    
    # Create logger
    logger = StreamlitLogger()
    logger.start_capture()
    st.session_state.logger = logger  # Store logger in session state
    
    # Progress callback function
    def update_progress(current_keyword="", cases_for_keyword=0, total_cases=0, progress=0):
        st.session_state.current_keyword = current_keyword
        st.session_state.cases_for_keyword = cases_for_keyword
        st.session_state.total_cases_scraped = total_cases
        st.session_state.progress = progress
    
    try:
        # Log initial information with frozen parameters
        params = st.session_state.frozen_params
        print(f"🚀 Starting EasyLaw scraper...")
        print(f"📊 Target: {params['case_limit']} cases")
        print(f"📁 Output directory: {params['output_dir']}")
        print(f"🔍 Keywords: {', '.join(params['keywords'])}")
        print(f"⏱️ Delay between requests: {params['delay_between_requests']}s")
        print(f"⏰ Timeout: {params['timeout_seconds']}s")
        
        # Capture stop_flag reference before starting thread
        stop_flag_reference = st.session_state.stop_flag
        start_time_reference = st.session_state.start_time
        
        # Run scraper in a separate thread with frozen parameters
        def run_scraper(stop_flag, start_time, metadata_db_name, metadata_collection_name):
            try:
                # Pass parameters directly instead of accessing session state
                result = scraper_easylaw(
                    limit=case_limit,
                    keywords=keywords,
                    delay_between_requests=delay_between_requests,
                    timeout_seconds=timeout_seconds,
                    output_dir=output_dir,
                    stop_flag=stop_flag,  # Pass as parameter
                    progress_callback=update_progress  # Pass progress callback
                )
                
                # Unpack the result tuple
                case_count, issues_count, scraped_files, start_time_obj, end_time_obj, stop_reason = result
                
                st.session_state.total_cases_scraped = case_count
                st.session_state.scraping_time = time.time() - start_time
                
                # Calculate scraping duration
                scraping_duration = (end_time_obj - start_time_obj).total_seconds()
                
                # Create metadata dictionary
                metadata = {
                    "total_cases_scraped": case_count,
                    "issues_count": issues_count,
                    "scraped_cases_names": scraped_files,
                    "start_time": start_time_obj.isoformat(),
                    "end_time": end_time_obj.isoformat(),
                    "scraping_duration": scraping_duration,
                    "source_web": "EasyLaw",
                    "output_directory": output_dir,
                    "stop_reason": stop_reason
                }
                
                # Save metadata to MongoDB
                save_metadata(metadata, metadata_db_name, metadata_collection_name)
                
                # Store metadata in session state for UI display
                st.session_state.last_metadata = metadata
                
                # Determine completion status and log the stopping reason
                if case_count >= case_limit:
                    st.session_state.scraping_status = "completed_limit"
                    print(f"🎯 Case limit reached ({case_limit} cases). Stopping automatically.")
                elif stop_flag.is_set():
                    st.session_state.scraping_status = "stopped"
                    print(f"🛑 Manual stop requested. Stopped at {case_count} cases.")
                else:
                    st.session_state.scraping_status = "completed"
                    print(f"🎉 Scraping completed naturally. Total cases saved: {case_count}")
                
                st.session_state.progress = 100
                print(f"📈 Total cases scraped: {case_count}")
                
                # Stop logger capture after all final messages are printed
                logger.stop_capture()
                
            except Exception as e:
                st.session_state.scraping_status = "error"
                print(f"❌ Error during scraping: {str(e)}")
                logger.stop_capture()
            finally:
                # Ensure logger is stopped even if there was an error
                if logger:
                    logger.stop_capture()
        
        # Start the scraping thread with stop_flag and start_time as parameters
        st.session_state.scraping_thread = threading.Thread(target=run_scraper, args=(stop_flag_reference, start_time_reference, metadata_db_name, metadata_collection_name))
        st.session_state.scraping_thread.daemon = True
        st.session_state.scraping_thread.start()
        
        # Don't block the UI thread - let Streamlit handle updates
        st.rerun()
        
    except Exception as e:
        st.session_state.scraping_status = "error"
        st.error(f"Failed to start scraping: {str(e)}")

def stop_scraping():
    """Safe stop - sets flag for scraper to stop at next boundary"""
    if 'scraping_status' in st.session_state and st.session_state.scraping_status == "running":
        if 'stop_flag' in st.session_state:
            st.session_state.stop_flag.set()  # Signal stop
        st.session_state.scraping_status = "stopping"

def clear_log():
    """Clear the log display"""
    st.session_state.logs = ""
    st.rerun()

if __name__ == "__main__":
    main() 