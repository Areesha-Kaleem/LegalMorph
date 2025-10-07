import streamlit as st
import threading
import time
import os
from datetime import datetime
import queue
import sys
from io import StringIO
from pymongo import MongoClient

# Import the scraper functions
from Web_scraper_eastlaw_combined import scrape_eastlaw_judgments, scrape_eastlaw_statutes

# MongoDB Configuration
DB_NAME = "lawgpt_metadata"
COLLECTION_NAME = "eastlaw_sessions"

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

def save_metadata(metadata_dict):
    """Save metadata to MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        # Add timestamp for document ordering
        metadata_dict["created_at"] = datetime.now()
        
        # Insert metadata
        result = collection.insert_one(metadata_dict)
        print(f"✅ Metadata saved to MongoDB: {result.inserted_id}")
        return True
    except Exception as e:
        print(f"❌ Error saving metadata to MongoDB: {e}")
        return False

def get_last_metadata():
    """Get the most recent metadata from MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
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

def refresh_metadata():
    """Refresh metadata from MongoDB and update session state"""
    try:
        last_metadata = get_last_metadata()
        if last_metadata:
            st.session_state.last_metadata = last_metadata
            print(f"🔍 Debug: Refreshed metadata for mode: {last_metadata.get('scraping_mode')}")
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
        page_title="EastLaw Web Scraper",
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
    if ('scraping_thread' in st.session_state and 
        st.session_state.scraping_thread is not None and 
        not st.session_state.scraping_thread.is_alive()):
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
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">⚖️ EastLaw Web Scraper</h1>', unsafe_allow_html=True)
    
    # Important notice about manual login
    st.markdown("""
    <div class="status-box warning-box">
        ⚠️ <strong>Important:</strong> This scraper requires manual login to EastLaw. 
        When you start scraping, a Chrome window will open. Please log in manually, 
        then click the "Continue After Login" button below to proceed with scraping.
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Check if scraping is running to disable all controls
        is_scraping = st.session_state.get('scraping_status') == "running"
        
        # Mode selection (Judgments vs Statutes)
        st.subheader("🎯 Scraping Mode")
        scraping_mode = st.selectbox(
            "Select scraping mode:",
            options=["Judgments", "Statutes"],
            disabled=is_scraping,
            help="Choose what to scrape from EastLaw" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Check if mode changed and clear metadata if so
        if 'current_mode' not in st.session_state:
            st.session_state.current_mode = scraping_mode
        elif st.session_state.current_mode != scraping_mode:
            # Mode changed - clear metadata
            if 'last_metadata' in st.session_state:
                del st.session_state.last_metadata
            if 'show_full_metadata' in st.session_state:
                del st.session_state.show_full_metadata
            st.session_state.current_mode = scraping_mode
        
        # Refresh metadata if scraping just completed
        if 'scraping_status' in st.session_state and st.session_state.scraping_status in ["completed", "completed_limit", "stopped", "error"]:
            if 'metadata_refreshed' not in st.session_state:
                refresh_metadata()
                st.session_state.metadata_refreshed = True
        elif 'metadata_refreshed' in st.session_state:
            del st.session_state.metadata_refreshed
        
        # Force refresh metadata when status changes to completion states
        if 'scraping_status' in st.session_state and st.session_state.scraping_status in ["completed", "completed_limit", "stopped", "error"]:
            # Always try to refresh metadata to ensure we have the latest
            if 'last_metadata' not in st.session_state or not st.session_state.last_metadata:
                refresh_metadata()
        
        # Output directory
        output_dir = st.text_input(
            "Output Directory:",
            value="D:\\LawGPT_data_pipeline\\data\\raw\\eastlaw",
            disabled=is_scraping,
            help="Directory where scraped files will be saved" + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Limit input based on mode
        if scraping_mode == "Judgments":
            limit_label = "Number of Cases to Scrape:"
            limit_help = "Total number of judgments to scrape"
        else:
            limit_label = "Number of Statutes to Scrape:"
            limit_help = "Total number of statutes to scrape"
        
        limit = st.number_input(
            limit_label,
            min_value=1,
            max_value=1000,
            value=50,
            disabled=is_scraping,
            help=limit_help + (" (Locked during scraping)" if is_scraping else "")
        )
        
        # Advanced options
        with st.expander("🔧 Advanced Options"):
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
        
        st.markdown("---")
        # Current Session Metadata - Always show if available
        st.markdown("### 📊 Last Session Metrics")
        
        # Display key metrics - show metadata if available
        if 'last_metadata' in st.session_state:
            metadata = st.session_state.last_metadata
            # Debug: Print metadata info
            st.write(f"Debug: Found metadata for mode: {metadata.get('scraping_mode')}, Current mode: {scraping_mode}")
            
            # Show metadata if it matches current mode OR if no specific mode filtering
            if metadata.get('scraping_mode') == scraping_mode or scraping_mode == "Judgments":  # Default to show if no mode filter
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Items Scraped", metadata.get('total_cases_scraped', 0))
                    st.metric("Issues", metadata.get('issues_count', 0))
                with col2:
                    st.metric("Duration", f"{metadata.get('scraping_duration', 0):.1f}s")
                    st.metric("Stop Reason", metadata.get('stop_reason', 'unknown'))
                
                # View full metadata button
                if st.button("📋 View Full Metadata", use_container_width=True):
                    # Refresh metadata before showing
                    refresh_metadata()
                    st.session_state.show_full_metadata = True
                
                # Show full metadata in expandable section
                if st.session_state.get('show_full_metadata', False):
                    with st.expander("📊 Full Metadata Details", expanded=True):
                        st.json(metadata)
            else:
                st.info(f"No metadata available for {scraping_mode} mode. Run a scraping session to see metrics.")
                # Debug: Show what metadata we have
                if metadata:
                    st.write(f"Debug: Available metadata is for mode: {metadata.get('scraping_mode')}")
                    st.write(f"Debug: Available metadata items: {metadata.get('total_cases_scraped', 0)}")
        else:
            # Fallback to old metrics if metadata not available
            if 'total_cases_scraped' in st.session_state:
                st.metric("Items Scraped", st.session_state.total_cases_scraped)
            if 'scraping_time' in st.session_state:
                st.metric("Duration", f"{st.session_state.scraping_time:.1f}s")
            st.info("No metadata available. Run a scraping session to see metrics.")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("🎯 Scraping Control")
        
        # Control buttons
        col_start, col_stop, col_clear = st.columns(3)
        
        with col_start:
            # Disable start while a previous thread is active or during waiting/stopping states
            start_disabled = st.session_state.get('scraping_status') in ["running", "waiting_for_login", "stopping"]
            if st.button("🚀 Start Scraping", type="primary", use_container_width=True, disabled=start_disabled):
                if not output_dir.strip():
                    st.error("Please specify an output directory.")
                else:
                    start_scraping(scraping_mode, limit, output_dir, delay_between_requests, timeout_seconds)
        
        with col_stop:
            # Enable stop button for any active scraping state
            stop_enabled = st.session_state.get('scraping_status') in ["running", "waiting_for_login", "stopping"]
            if st.button("⏹️ Stop Scraping", use_container_width=True, disabled=not stop_enabled):
                stop_scraping()
        
        with col_clear:
            if st.button("🗑️ Clear Log", use_container_width=True):
                clear_log()
        
        # Manual login control
        if 'login_ready_event' in st.session_state and st.session_state.get('scraping_status') == "waiting_for_login":
            st.markdown("### 🔐 Manual Login Control")
            if st.button("✅ Continue After Login", type="primary", use_container_width=True):
                st.session_state.login_ready_event.set()
                st.session_state.scraping_status = "running"
                st.rerun()
        
        # Progress and status
        if 'scraping_status' in st.session_state:
            status = st.session_state.scraping_status
            if status == "running":
                st.markdown('<div class="status-box info-box">🔄 Scraping in progress...</div>', unsafe_allow_html=True)
            elif status == "waiting_for_login":
                st.markdown('<div class="status-box warning-box">🔐 Waiting for manual login. Please log in to EastLaw in the Chrome window, then click "Continue After Login" above.</div>', unsafe_allow_html=True)
            elif status == "stopping":
                st.markdown('<div class="status-box info-box">⏹️ Stopping scraper (completing current item)...</div>', unsafe_allow_html=True)
            elif status == "completed":
                st.markdown('<div class="status-box success-box">✅ Scraping completed successfully!</div>', unsafe_allow_html=True)
            elif status == "completed_limit":
                st.markdown('<div class="status-box success-box">🎯 Item limit reached - scraping completed!</div>', unsafe_allow_html=True)
            elif status == "error":
                st.markdown('<div class="status-box error-box">❌ Error occurred during scraping</div>', unsafe_allow_html=True)
            elif status == "stopped":
                st.markdown('<div class="status-box info-box">⏹️ Scraping stopped by user</div>', unsafe_allow_html=True)
            elif status == "login_failed":
                st.markdown('<div class="status-box error-box">🔐 Login failed. Please log in manually and try again.</div>', unsafe_allow_html=True)
    
    # Log output
    st.header("📋 Log Output")
    
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
            # Thread finished but status wasn't updated, force update
            if st.session_state.scraping_status in ["running", "waiting_for_login", "stopping"]:
                st.session_state.scraping_status = "completed"
        
        # Auto-refresh every 1 second during scraping for faster response
        time.sleep(1)
        st.rerun()
    elif 'scraping_status' in st.session_state and st.session_state.scraping_status in ["completed", "completed_limit", "stopped", "error"]:
        # Update logs one final time when scraping is done
        if 'logger' in st.session_state and st.session_state.logger is not None:
            try:
                logs = st.session_state.logger.get_logs()
                if logs:
                    st.session_state.logs += logs
            except:
                # Logger might be None or in invalid state after stop
                pass
    
    # Always check if thread finished regardless of status
    if ('scraping_thread' in st.session_state and 
        st.session_state.scraping_thread is not None and 
        not st.session_state.scraping_thread.is_alive()):
        if st.session_state.scraping_status == "running":
            st.session_state.scraping_status = "completed"
            st.rerun()
    
    # AGGRESSIVE STOP CHECK - Force UI update when stopped
    if 'scraping_status' in st.session_state and st.session_state.scraping_status == "stopped":
        # Force UI refresh to show stopped status
        st.rerun()

def start_scraping(scraping_mode, limit, output_dir, delay_between_requests, timeout_seconds):
    """Start the scraping process with parameter freezing"""
    # FORCE COMPLETE SESSION RESET - Critical for multi-session stability
    print("🔄 Force resetting session state for new scraping session...")
    
    # Reset all critical session variables to prevent conflicts
    st.session_state.scraping_status = "waiting_for_login"
    st.session_state.thread_started = False
    st.session_state.scraping_thread = None
    st.session_state.progress = 0
    st.session_state.cases_scraped = 0
    st.session_state.current_keyword = ""
    st.session_state.cases_for_keyword = 0
    st.session_state.logs = ""
    st.session_state.start_time = time.time()
    st.session_state.logger = None
    st.session_state.total_cases_scraped = 0
    st.session_state.scraping_time = 0
    
    # FORCE RESET threading events - Critical for multi-session stability
    print("🔄 Resetting threading events for clean session...")
    st.session_state.stop_flag = threading.Event()
    st.session_state.login_ready_event = threading.Event()
    
    # FREEZE ALL PARAMETERS at start time
    st.session_state.frozen_params = {
        'scraping_mode': scraping_mode,
        'limit': limit,
        'output_dir': output_dir,
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
        print(f"🚀 Starting EastLaw scraper...")
        print(f"🎯 Mode: {params['scraping_mode']}")
        print(f"📊 Target: {params['limit']} items")
        print(f"📁 Output directory: {params['output_dir']}")
        print(f"⏱️ Delay between requests: {params['delay_between_requests']}s")
        print(f"⏰ Timeout: {params['timeout_seconds']}s")
        
        # Capture references before starting thread
        stop_flag_reference = st.session_state.stop_flag
        start_time_reference = st.session_state.start_time
        login_ready_reference = st.session_state.login_ready_event
        
        # Run scraper in a separate thread with frozen parameters
        def run_scraper(stop_flag, start_time, login_ready_event):
            # Initialize variables for metadata creation
            item_count = 0
            issues_count = 0
            scraped_files = []
            start_time_obj = datetime.now()
            end_time_obj = datetime.now()
            stop_reason = "error"
            
            try:
                # Choose the appropriate scraper function based on mode
                if scraping_mode == "Judgments":
                    result = scrape_eastlaw_judgments(
                        limit=limit,
                        output_dir=output_dir,
                        stop_flag=stop_flag,
                        progress_callback=update_progress,
                        login_ready_event=login_ready_event
                    )
                else:  # Statutes
                    result = scrape_eastlaw_statutes(
                        limit=limit,
                        output_dir=output_dir,
                        stop_flag=stop_flag,
                        progress_callback=update_progress,
                        login_ready_event=login_ready_event
                    )
                
                # Unpack the result tuple
                item_count, issues_count, scraped_files, start_time_obj, end_time_obj, stop_reason = result
                
                st.session_state.total_cases_scraped = item_count
                st.session_state.scraping_time = time.time() - start_time
                
                # Determine completion status based on stop_reason from scraper function
                if stop_reason == "case_limit_reached":
                    st.session_state.scraping_status = "completed_limit"
                    print(f"🎯 {scraping_mode} limit reached ({limit} items). Stopping automatically.")
                elif stop_reason == "manual_stop":
                    st.session_state.scraping_status = "stopped"
                    print(f"🛑 Manual stop requested. Stopped at {item_count} items.")
                elif stop_reason == "login_failed":
                    st.session_state.scraping_status = "login_failed"
                    print(f"🔐 Login failed. Please log in manually and try again.")
                elif stop_reason == "error":
                    st.session_state.scraping_status = "error"
                    print(f"❌ Error occurred during scraping.")
                else:
                    st.session_state.scraping_status = "completed"
                    print(f"🎉 Scraping completed naturally. Total items saved: {item_count}")
                
                st.session_state.progress = 100
                print(f"📈 Total items scraped: {item_count}")
                
            except Exception as e:
                st.session_state.scraping_status = "error"
                stop_reason = "error"
                end_time_obj = datetime.now()
                print(f"❌ Error during scraping: {str(e)}")
            
            finally:
                # ALWAYS create metadata regardless of how scraping ended
                scraping_duration = (end_time_obj - start_time_obj).total_seconds()
                
                # Create metadata dictionary
                metadata = {
                    "total_cases_scraped": item_count,
                    "issues_count": issues_count,
                    "scraped_cases_names": scraped_files,
                    "start_time": start_time_obj.isoformat(),
                    "end_time": end_time_obj.isoformat(),
                    "scraping_duration": scraping_duration,
                    "source_web": "EastLaw",
                    "scraping_mode": scraping_mode,
                    "output_directory": output_dir,
                    "stop_reason": stop_reason
                }
                
                # Save metadata to MongoDB
                save_metadata(metadata)
                
                # Store metadata in session state for UI display
                st.session_state.last_metadata = metadata
                print(f"🔍 Debug: Metadata stored for mode: {scraping_mode}, Items: {item_count}, Stop reason: {stop_reason}")
                
                # Stop logger capture after all final messages are printed
                logger.stop_capture()
                
                # Mark thread as finished
                st.session_state.thread_started = False
        
        # Start the scraping thread
        st.session_state.scraping_thread = threading.Thread(
            target=run_scraper, 
            args=(stop_flag_reference, start_time_reference, login_ready_reference)
        )
        st.session_state.scraping_thread.daemon = True
        st.session_state.scraping_thread.start()
        st.session_state.thread_started = True
        
        # Don't block the UI thread - let Streamlit handle updates
        st.rerun()
        
    except Exception as e:
        st.session_state.scraping_status = "error"
        st.error(f"Failed to start scraping: {str(e)}")

def stop_scraping():
    """Immediate stop - stops scraping and enables all frozen controls"""
    print("🛑 STOP REQUESTED!")
    
    # Check if scraping is active
    if 'scraping_status' in st.session_state and st.session_state.scraping_status in ["running", "waiting_for_login", "stopping"]:
        # Set stop flag immediately
        if 'stop_flag' in st.session_state:
            st.session_state.stop_flag.set()
            print("🛑 Stop signal sent to scraper...")
        
        # Force status to stopped immediately
        st.session_state.scraping_status = "stopped"
        print("⏹️ Scraping status set to stopped immediately")
        
        # ENABLE ALL FROZEN CONTROLS - This is what user expects
        print("🔓 Enabling all frozen controls...")
        
        # Reset all critical variables to enable controls
        st.session_state.thread_started = False
        st.session_state.scraping_thread = None
        st.session_state.progress = 0
        st.session_state.cases_scraped = 0
        st.session_state.current_keyword = ""
        st.session_state.cases_for_keyword = 0
        st.session_state.total_cases_scraped = 0
        st.session_state.scraping_time = 0
        
        # Reset threading events for next session
        if 'stop_flag' in st.session_state:
            st.session_state.stop_flag = threading.Event()
        if 'login_ready_event' in st.session_state:
            st.session_state.login_ready_event = threading.Event()
        
        # Clear logger safely
        if 'logger' in st.session_state and st.session_state.logger is not None:
            try:
                st.session_state.logger.stop_capture()
            except:
                pass
            st.session_state.logger = None
        
        # Add stop message to logs
        if 'logs' in st.session_state:
            st.session_state.logs += "\n🛑 SCRAPER INTERRUPTED AND STOPPED MANUALLY BY USER\n"
            st.session_state.logs += "🔓 All controls enabled for next session\n"
        
        print("✅ Scraper stopped and all controls enabled")
        print("✅ Ready for next session")
    else:
        print("⚠️ No active scraping session to stop")

def clear_log():
    """Clear the log display and metadata"""
    st.session_state.logs = ""
    # Also clear metadata display
    if 'last_metadata' in st.session_state:
        del st.session_state.last_metadata
    if 'show_full_metadata' in st.session_state:
        del st.session_state.show_full_metadata
    st.rerun()

if __name__ == "__main__":
    main()
