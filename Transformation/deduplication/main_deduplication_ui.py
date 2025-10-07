import streamlit as st
import threading
import time
import os
import sys
import json
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import engines - Use relative imports for files in same directory
from deduplication_engine import DeduplicationEngine
from unification_engine import UnificationEngine

load_dotenv()

# MongoDB Configuration - No hardcoded values, all configurable through UI

class StreamlitLogger:
    """Enhanced logger with real-time UI updates"""
    def __init__(self):
        self.logs = []
        self.capturing = False
    
    def start_capture(self):
        self.capturing = True
        self.logs = []
    
    def stop_capture(self):
        self.capturing = False
    
    def write(self, text):
        if self.capturing:
            if text is None:
                return
            normalized = (str(text) if not isinstance(text, str) else text).rstrip("\n") + "\n"
            self.logs.append(normalized)
            # Print all messages to console for debugging
            print(normalized.rstrip())
    
    def flush(self):
        pass
    
    def get_logs(self):
        """Get all captured logs as a single string"""
        return "".join(self.logs)
    
    def get_recent_logs(self, num_lines=10):
        """Get recent logs for real-time display"""
        return "".join(self.logs[-num_lines:])

def get_last_deduplication_metadata():
    """Get the most recent deduplication metadata from MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        
        # Use configurable metadata database and collection names
        metadata_db_name = st.session_state.get('metadata_db_name', "")
        dedup_metadata_collection_name = st.session_state.get('dedup_metadata_collection_name', "")
        
        db = client[metadata_db_name]
        collection = db[dedup_metadata_collection_name]
        
        # Get the most recent document
        last_metadata = collection.find_one(
            sort=[("deduplication_session.start_time", -1)]
        )
        
        if last_metadata:
            # Remove MongoDB internal fields
            last_metadata.pop("_id", None)
            return last_metadata
        else:
            return None
    except Exception as e:
        st.error(f"❌ Error retrieving metadata: {e}")
        return None

def get_last_unification_metadata():
    """Get the most recent unification metadata from MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        
        # Use configurable metadata database and collection names
        metadata_db_name = st.session_state.get('metadata_db_name', "")
        unify_metadata_collection_name = st.session_state.get('unify_metadata_collection_name', "")
        
        db = client[metadata_db_name]
        collection = db[unify_metadata_collection_name]
        
        # Get the most recent document
        last_metadata = collection.find_one(
            sort=[("unification_session.start_time", -1)]
        )
        
        if last_metadata:
            # Remove MongoDB internal fields
            last_metadata.pop("_id", None)
            return last_metadata
        else:
            return None
    except Exception as e:
        st.error(f"❌ Error retrieving unification metadata: {e}")
        return None

def get_document_counts():
    """Get total document counts from configured sources"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        
        # Get counts from configured sources for deduplication
        total_count = 0
        source_counts = {}
        
        # Check if we have configured sources for deduplication
        if hasattr(st, 'session_state') and 'num_sources_dedup' in st.session_state:
            num_sources = st.session_state.num_sources_dedup
            dedup_db = st.session_state.get('dedup_db_name', '')
            
            for i in range(num_sources):
                collection_name = st.session_state.get(f'collection_name_{i}', "")
                if collection_name:
                    try:
                        db = client[dedup_db]
                        collection = db[collection_name]
                        count = collection.count_documents({})
                        source_counts[f"source_{i}"] = count
                        total_count += count
                    except Exception as e:
                        st.error(f"❌ Error counting documents in {dedup_db}.{collection_name}: {e}")
                        source_counts[f"source_{i}"] = 0
        
        # If no sources configured, return empty counts
        if not source_counts:
            return {"total": 0, "sources": {}}
        
        return {
            "total": total_count,
            "sources": source_counts
        }
        
    except Exception as e:
        st.error(f"❌ Error retrieving document counts: {e}")
        return {"total": 0, "sources": {}}

def initialize_session_state():
    """Initialize Streamlit session state properly"""
    # Configuration state
    if 'mongo_uri' not in st.session_state:
        st.session_state.mongo_uri = "mongodb://localhost:27017"
    if 'similarity_threshold' not in st.session_state:
        st.session_state.similarity_threshold = 0.85
    
    # Deduplication configuration
    if 'num_sources_dedup' not in st.session_state:
        st.session_state.num_sources_dedup = 2
    
    # Initialize source directories (empty by default)
    for i in range(10):  # Support up to 10 sources
        if f'source_dir_{i}' not in st.session_state:
            st.session_state[f'source_dir_{i}'] = ""
    
    if 'dedup_db_name' not in st.session_state:
        st.session_state.dedup_db_name = ""
    if 'metadata_db_name' not in st.session_state:
        st.session_state.metadata_db_name = ""
    if 'metadata_collection_name' not in st.session_state:
        st.session_state.metadata_collection_name = ""
    if 'dedup_metadata_collection_name' not in st.session_state:
        st.session_state.dedup_metadata_collection_name = ""
    if 'unify_metadata_collection_name' not in st.session_state:
        st.session_state.unify_metadata_collection_name = ""
    
    # Unification configuration
    if 'num_sources' not in st.session_state:
        st.session_state.num_sources = 2
    if 'unified_db_name' not in st.session_state:
        st.session_state.unified_db_name = "UnifiedLegalDB"
    if 'unified_collection_name' not in st.session_state:
        st.session_state.unified_collection_name = "unified_legal_cases"
    
    # Source configuration (for unification)
    for i in range(10):  # Support up to 10 sources
        if f'source_{i}_db' not in st.session_state:
            st.session_state[f'source_{i}_db'] = ""
        if f'source_{i}_collection' not in st.session_state:
            # Set generic default collection names instead of hardcoded easylaw/eastlaw
            st.session_state[f'source_{i}_collection'] = f"source_{i}_collection"
    
    # Deduplication state
    if 'deduplication_status' not in st.session_state:
        st.session_state.deduplication_status = "idle"
    if 'deduplication_progress' not in st.session_state:
        st.session_state.deduplication_progress = 0
    if 'deduplication_logs' not in st.session_state:
        st.session_state.deduplication_logs = ""
    if 'deduplication_results' not in st.session_state:
        st.session_state.deduplication_results = None
    if 'deduplication_running' not in st.session_state:
        st.session_state.deduplication_running = False
    if 'deduplication_thread_started' not in st.session_state:
        st.session_state.deduplication_thread_started = False
    if 'start_time' not in st.session_state:
        st.session_state.start_time = None
    if 'thread_started' not in st.session_state:
        st.session_state.thread_started = False
    if 'logger' not in st.session_state:
        st.session_state.logger = None
    
    # Unification state
    if 'unification_status' not in st.session_state:
        st.session_state.unification_status = "idle"
    if 'unification_logs' not in st.session_state:
        st.session_state.unification_logs = ""
    if 'unification_results' not in st.session_state:
        st.session_state.unification_results = None
    if 'unification_running' not in st.session_state:
        st.session_state.unification_running = False
    if 'unification_thread_started' not in st.session_state:
        st.session_state.unification_thread_started = False
    
    # UI state
    if 'discovered_collections' not in st.session_state:
        st.session_state.discovered_collections = []
    if 'use_batch_processing' not in st.session_state:
        st.session_state.use_batch_processing = True
    if 'batch_size' not in st.session_state:
        st.session_state.batch_size = 5


def run_deduplication_thread(mongo_uri, similarity_threshold, merge_dir, dedup_db_name, collection_names, metadata_db_name, dedup_metadata_collection_name, logger):
    """Run deduplication in a separate thread with proper completion handling"""
    try:
        # Initialize deduplication engine with provided database name
        if not dedup_db_name:
            logger.write(f"❌ Error: No database name provided")
            return
        
        engine = DeduplicationEngine(
            mongo_uri=mongo_uri,
            similarity_threshold=similarity_threshold,
            db_name=dedup_db_name
        )
        
        logger.write(f"🚀 Starting optimized deduplication with NumPy acceleration")
        
        # Get source directories from session state
        num_sources = st.session_state.get('num_sources_dedup', 2)
        source_dirs = []
        for i in range(num_sources):
            source_dir = st.session_state.get(f'source_dir_{i}', "")
            if source_dir:
                source_dirs.append(source_dir)
        
        logger.write(f"📁 Processing {len(source_dirs)} source directories")
        for i, source_dir in enumerate(source_dirs):
            logger.write(f"   Source {i+1}: {source_dir}")
        
        # Process sources in pairs (2 at a time) - new logic: compare a&b, then b&c, etc.
        total_duplicates_removed = 0
        total_groups_found = 0
        total_files_compared = 0
        
        # Use provided collection names
        logger.write(f"📊 Processing {len(collection_names)} collection names")
        logger.write(f"📋 Collections: {', '.join(collection_names)}")
        
        if len(collection_names) < 2:
            logger.write(f"❌ Need at least 2 collection names. Found: {len(collection_names)}")
            return
        
        # Calculate rounds needed: if 3 sources → 2 rounds, if 4 sources → 3 rounds
        total_rounds = len(collection_names) - 1
        logger.write(f"🔄 Will process {total_rounds} rounds of pairwise comparison")
        
        # Compare sources pairwise: a&b, then b&c, then c&d, etc.
        for round_num in range(total_rounds):
            collection1_name = collection_names[round_num]
            collection2_name = collection_names[round_num + 1]
            
            logger.write(f"\n🔄 Processing Round {round_num + 1}/{total_rounds}: {collection1_name} ↔ {collection2_name}")
            
            # Update progress based on current round
            progress = 10 + (round_num * 80 // total_rounds)
            try:
                st.session_state.deduplication_progress = progress
            except:
                pass
            
            # Run deduplication for this pair
            try:
                result = engine.deduplicate_all_documents(merge_dir, [collection1_name, collection2_name])
                
                # Accumulate results
                total_duplicates_removed += result.get('duplicates_removed', 0)
                total_groups_found += result.get('duplicate_groups_found', 0)
                total_files_compared += result.get('collection1_documents', 0) + result.get('collection2_documents', 0)
                
                logger.write(f"✅ Round {round_num + 1} completed: {result.get('duplicates_removed', 0)} duplicates removed")
                
            except Exception as e:
                logger.write(f"❌ Error processing Round {round_num + 1}: {str(e)}")
                continue
        
        # Log final results
        logger.write(f"\n📊 Final Deduplication Results:")
        logger.write(f"   - Total Files Compared: {total_files_compared}")
        logger.write(f"   - Total Duplicate Groups: {total_groups_found}")
        logger.write(f"   - Total Duplicates Removed: {total_duplicates_removed}")
        
        # Save metadata using provided database and collection names
        logger.write(f"💾 Attempting to save metadata to: {metadata_db_name}.{dedup_metadata_collection_name}")
        
        # Validate metadata before saving
        if hasattr(engine, 'deduplication_metadata') and engine.deduplication_metadata:
            logger.write(f"📋 Metadata content: {len(engine.deduplication_metadata)} fields")
            metadata_saved = engine.save_deduplication_metadata(
                engine.deduplication_metadata, 
                metadata_db_name, 
                dedup_metadata_collection_name
            )
        else:
            logger.write(f"❌ No deduplication metadata available to save")
            metadata_saved = False
        
        if metadata_saved:
            logger.write(f"✅ Metadata saved successfully")
        else:
            logger.write(f"⚠️ Failed to save metadata")
        
        logger.write(f"\n✅ Deduplication completed successfully!")
        
        # Clean up
        engine.close()
        logger.stop_capture()
        
        # Update session state
        st.session_state.deduplication_status = "completed"
        st.session_state.deduplication_progress = 100
        st.session_state.thread_started = False
        st.session_state.deduplication_results = {
            "total_files_compared": total_files_compared,
            "duplicate_groups_found": total_groups_found,
            "duplicates_removed": total_duplicates_removed
        }
        
    except Exception as e:
        logger.write(f"❌ Error during deduplication: {str(e)}")
        st.session_state.deduplication_status = "error"
        st.session_state.deduplication_running = False
        st.session_state.thread_started = False
        if 'engine' in locals():
            engine.close()
        logger.stop_capture()

def run_unification_thread(mongo_uri, final_collections_info, unified_db_name, unified_collection_name, metadata_db_name, unify_metadata_collection_name, logger):
    """Run unification in a separate thread with proper completion handling"""
    try:
        # Initialize unification engine with provided metadata parameters
        logger.write(f"💾 Metadata configuration: DB={metadata_db_name}, Collection={unify_metadata_collection_name}")
        engine = UnificationEngine(mongo_uri, metadata_db_name, unify_metadata_collection_name)
        
        # Connect the UI logger to the engine
        engine.set_ui_logger(logger)
        
        logger.write(f"🚀 Starting schema unification process...")
        
        # Run unification
        result = engine.unify_collections(
            final_collections_info=final_collections_info,
            unified_db_name=unified_db_name,
            unified_collection_name=unified_collection_name
        )
        
        # Log results
        logger.write(f"\n📊 Unification Results:")
        logger.write(f"   - Total Processed: {result.get('total_processed', 0)}")
        logger.write(f"   - Total Unified: {result.get('total_unified', 0)}")
        logger.write(f"   - Duration: {result.get('duration', 0):.2f}s")
        
        if result.get('success', False):
            logger.write(f"✅ Unification completed successfully!")
        else:
            logger.write(f"❌ Unification failed: {result.get('error', 'Unknown error')}")
        
        # Clean up
        engine.close()
        logger.stop_capture()
        
        # Update session state
        st.session_state.unification_status = "completed"
        st.session_state.unification_progress = 100
        st.session_state.unification_thread_started = False
        st.session_state.unification_results = result
        
    except Exception as e:
        logger.write(f"❌ Error during unification: {str(e)}")
        st.session_state.unification_status = "error"
        st.session_state.unification_running = False
        st.session_state.unification_thread_started = False
        if 'engine' in locals():
            engine.close()
        logger.stop_capture()

def main():
    st.set_page_config(
        page_title="Legal Document Pipeline - Deduplication & Unification",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Important note at the top
    st.markdown("""
    <div style="background-color: #e3f2fd; border: 1px solid #2196f3; border-radius: 0.5rem; padding: 1rem; margin: 1rem 0;">
        <h4 style="color: #1976d2; margin: 0;">📋 Workflow Instructions</h4>
        <p style="color: #1976d2; margin: 0.5rem 0 0 0;">
            <strong>Step 1:</strong> Run deduplication first to remove duplicate documents<br>
            <strong>Step 2:</strong> Then run unification to create a unified schema<br>
            <strong>Note:</strong> Use the stop buttons to manually stop processes when needed
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Important note about deduplication requirements
    st.markdown("""
    <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 0.5rem; padding: 1rem; margin: 1rem 0;">
        <h4 style="color: #856404; margin: 0;">⚠️ Deduplication Requirements</h4>
        <p style="color: #856404; margin: 0.5rem 0 0 0;">
            <strong>Perform deduplication first</strong> to get rid of redundant data across sources of the same country.<br>
            <strong>For KSA:</strong> Only one case source - deduplication is not required.<br>
            <strong>Not required for:</strong> Statutes, Laws, Legislations, Constitutions.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Processing logic explanation
    st.markdown("""
    <div style="background-color: #e8f5e8; border: 1px solid #4caf50; border-radius: 0.5rem; padding: 1rem; margin: 1rem 0;">
        <h4 style="color: #2e7d32; margin: 0;">🔄 Processing Logic</h4>
        <p style="color: #2e7d32; margin: 0.5rem 0 0 0;">
            <strong>Multi-source processing:</strong> Sources are processed in pairs (2 at a time).<br>
            <strong>Example:</strong> If you have sources A, B, C, D → A↔B, then B↔C, then C↔D<br>
            <strong>Why pairs?</strong> The deduplication engine compares 2 sources at once for optimal performance.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Important requirements notes
    st.markdown("""
    <div style="background-color: #ffebee; border: 1px solid #f44336; border-radius: 0.5rem; padding: 1rem; margin: 1rem 0;">
        <h4 style="color: #c62828; margin: 0;">⚠️ Critical Requirements</h4>
        <p style="color: #c62828; margin: 0.5rem 0 0 0;">
            <strong>🔍 Deduplication:</strong> At least 2 sources required (for pair-wise comparison)<br>
            <strong>🔄 Unification:</strong> At least 1 source required (for schema generation)<br>
            <strong>📋 Schema:</strong> Generate unified schema before starting unification process
        </p>
    </div>
    """, unsafe_allow_html=True)
    
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
    .progress-container {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">Legal Data Pipeline</h1>', unsafe_allow_html=True)
    st.markdown('<h2 style="text-align: center; color: #666; margin-bottom: 2rem;">Deduplication & Schema Unification</h2>', unsafe_allow_html=True)
    st.markdown("### AI-powered optimization for legal document processing")
    
    # Sidebar Configuration
    st.sidebar.markdown("## Configuration")
    
    # MongoDB URI (shared)
    mongo_uri = st.sidebar.text_input(
        "MongoDB URI",
        value=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        help="MongoDB connection string"
    )
    
    # Deduplication Configuration
    st.sidebar.markdown("### Deduplication Settings")
    
    # Check if deduplication is running to freeze configuration
    is_dedup_running = st.session_state.deduplication_running
    
    # Model info (fixed to paraphrase-MiniLM-L3-v2)
    st.sidebar.info("🤖 **Model**: paraphrase-MiniLM-L3-v2 (Fixed)")
    st.sidebar.info("⚡ **Similarity Threshold**: 0.85 (Fixed)")
    st.sidebar.info("🚀 **Optimization**: NumPy acceleration")
    
    # Input directories configuration
    st.sidebar.markdown("#### Input Configuration")
    
    # Number of sources
    num_sources_dedup = st.sidebar.number_input(
        "Number of Sources",
        min_value=1,
        max_value=20,
        value=st.session_state.get('num_sources_dedup', 2),
        help="How many source directories to process",
        disabled=is_dedup_running
    )
    
    # Update session state when number changes
    if num_sources_dedup != st.session_state.get('num_sources_dedup', 2):
        st.session_state.num_sources_dedup = num_sources_dedup
        # Initialize new source directories if number increased
        for i in range(num_sources_dedup):
            if f'source_dir_{i}' not in st.session_state:
                st.session_state[f'source_dir_{i}'] = ""
    
    # Dynamic source directory inputs
    for i in range(num_sources_dedup):
        source_dir = st.sidebar.text_input(
            f"Source {i+1} Directory",
            value=st.session_state.get(f'source_dir_{i}', ""),
            help=f"Directory containing source {i+1} JSON files (REQUIRED)",
            placeholder="Enter full path to source directory",
            disabled=is_dedup_running
        )
        # Update session state when input changes
        if source_dir != st.session_state.get(f'source_dir_{i}', ""):
            st.session_state[f'source_dir_{i}'] = source_dir
    
    # MongoDB configuration
    st.sidebar.markdown("#### MongoDB Configuration")
    
    # Input/Output database name (same for deduplication)
    dedup_db_name = st.sidebar.text_input(
        "Database Name",
        value=st.session_state.get('dedup_db_name', ""),
        help="MongoDB database where collections will be created/processed (REQUIRED)",
        placeholder="Enter database name",
        disabled=is_dedup_running
    )
    # Update session state when input changes
    if dedup_db_name != st.session_state.get('dedup_db_name', ""):
        st.session_state.dedup_db_name = dedup_db_name
    
    # Collection names (one per source)
    st.sidebar.markdown("#### Collection Names")
    st.sidebar.info("Enter collection names for each source")
    
    # Collection name input fields in sidebar
    for i in range(num_sources_dedup):
        collection_key = f'collection_name_{i}'
        if collection_key not in st.session_state:
            st.session_state[collection_key] = ""
        
        # Use a unique key for each text input to ensure proper session state updates
        collection_name = st.sidebar.text_input(
            f"Collection {i+1} Name",
            value=st.session_state[collection_key],
            key=f"sidebar_collection_input_{i}",
            help=f"Enter the MongoDB collection name for source {i+1}",
            placeholder="e.g., uae_moj_cases_merge",
            disabled=is_dedup_running
        )
        
        # Force update session state - this ensures the value is always stored
        st.session_state[collection_key] = collection_name
    
    # Metadata configuration
    st.sidebar.markdown("#### Metadata Configuration")
    
    # Metadata database name
    metadata_db_name = st.sidebar.text_input(
        "Metadata Database Name",
        value=st.session_state.get('metadata_db_name', ""),
        help="Database to store deduplication metadata (REQUIRED)",
        placeholder="Enter metadata database name",
        disabled=is_dedup_running
    )
    # Update session state when input changes
    if metadata_db_name != st.session_state.get('metadata_db_name', ""):
        st.session_state.metadata_db_name = metadata_db_name
    
    # Metadata collection names
    dedup_metadata_collection_name = st.sidebar.text_input(
        "Deduplication Metadata Collection",
        value=st.session_state.get('dedup_metadata_collection_name', ""),
        help="Collection to store deduplication metadata (REQUIRED)",
        placeholder="e.g., deduplication_metadata",
        disabled=is_dedup_running
    )
    # Update session state when input changes
    if dedup_metadata_collection_name != st.session_state.get('dedup_metadata_collection_name', ""):
        st.session_state.dedup_metadata_collection_name = dedup_metadata_collection_name
    

    
    # Deduplication configuration status
    if is_dedup_running:
        st.sidebar.warning("🔒 Deduplication config locked")
    else:
        st.sidebar.success("✅ Deduplication config unlocked")
    
    # Unification Configuration
    st.sidebar.markdown("### Unification Settings")
    
    # Check if unification is running to freeze configuration
    is_unify_running = st.session_state.unification_running
    
    # Unified database settings
    unified_db_name = st.sidebar.text_input(
        "Unified Database Name",
        value=st.session_state.unified_db_name,
        help="Target database for unified documents",
        disabled=is_unify_running,
        key="unified_db_input"
    )
    
    # Update session state when input changes
    if unified_db_name != st.session_state.unified_db_name:
        st.session_state.unified_db_name = unified_db_name
    
    unified_collection_name = st.sidebar.text_input(
        "Unified Collection Name", 
        value=st.session_state.unified_collection_name,
        help="Target collection for unified documents",
        disabled=is_unify_running,
        key="unified_collection_input"
    )
    
    # Update session state when input changes
    if unified_collection_name != st.session_state.unified_collection_name:
        st.session_state.unified_collection_name = unified_collection_name
    
    # Unification metadata collection
    unify_metadata_collection_name = st.sidebar.text_input(
        "Unification Metadata Collection",
        value=st.session_state.get('unify_metadata_collection_name', ""),
        help="Collection to store unification metadata (REQUIRED)",
        placeholder="e.g., unification_metadata",
        disabled=is_unify_running
    )
    # Update session state when input changes
    if unify_metadata_collection_name != st.session_state.get('unify_metadata_collection_name', ""):
        st.session_state.unify_metadata_collection_name = unify_metadata_collection_name
    
    # Processing options
    st.sidebar.info("⚡ Single document processing enabled for better performance")
    
    # Note: Batch processing removed for simplicity and reliability
    
    # Unification configuration status
    if is_unify_running:
        st.sidebar.warning("🔒 Unification config locked")
    else:
        st.sidebar.success("✅ Unification config unlocked")
    
    # Main content area - Deduplication Section
    st.markdown("## 🔍 Deduplication")
    
    # Configuration lock warning
    if st.session_state.deduplication_running:
        st.markdown("""
        <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 0.5rem; padding: 1rem; margin: 1rem 0;">
            <h4 style="color: #856404; margin: 0;">🔒 Deduplication Configuration Locked</h4>
            <p style="color: #856404; margin: 0.5rem 0 0 0;">Deduplication settings are frozen during processing to ensure consistency.</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Configuration Summary
    st.markdown("### ⚙️ Current Configuration")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Input Directories**")
        num_sources = st.session_state.get('num_sources_dedup', 2)
        for i in range(num_sources):
            source_dir = st.session_state.get(f'source_dir_{i}', "")
            if source_dir:
                st.info(f"**Source {i+1}:** {source_dir}")
            else:
                st.warning(f"**Source {i+1}:** Not configured")
    
    with col2:
        st.markdown("**MongoDB Settings**")
        dedup_db = st.session_state.get('dedup_db_name', "")
        if dedup_db:
            st.info(f"**Database:** {dedup_db}")
        else:
            st.warning(f"**Database:** Not configured")
        

        
        st.info(f"**Similarity:** 0.85 (Fixed)")
    
    with col3:
        st.markdown("**Deduplication Metadata**")
        meta_db = st.session_state.get('metadata_db_name', "")
        dedup_meta_coll = st.session_state.get('dedup_metadata_collection_name', "")
        if meta_db:
            st.info(f"**Database:** {meta_db}")
        else:
            st.warning(f"**Database:** Not configured")
        if dedup_meta_coll:
            st.info(f"**Collection:** {dedup_meta_coll}")
        else:
            st.warning(f"**Collection:** Not configured")
        st.info(f"**Model:** paraphrase-MiniLM-L3-v2")
    
    # Get document counts
    counts = get_document_counts()
    
    if counts["total"] == 0:
        st.warning("⚠️ No documents found in database. Please ensure you have processed documents first.")
    else:
        # Display document counts
        st.info("**Document Counts**")
        col_a, col_b = st.columns([1, 2])
        with col_a:
            st.metric("Total Documents", counts["total"])
        with col_b:
            # Display source-specific counts
            if counts["sources"]:
                source_text = " | ".join([f"{k}: {v}" for k, v in counts["sources"].items()])
                st.metric("Source Documents", source_text)
            else:
                st.metric("Source Documents", "No sources configured")
        
        # Deduplication controls
        st.markdown("### Start Deduplication")
        
        # Deduplication controls
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.session_state.deduplication_running:
                st.warning("🔄 Deduplication is currently running...")
            else:
                # Validate configuration before allowing start
                config_valid = True
                validation_errors = []
                
                # Check if all required fields are filled
                num_sources = st.session_state.get('num_sources_dedup', 2)
                
                # Validate minimum sources requirement
                if num_sources < 2:
                    config_valid = False
                    validation_errors.append("Deduplication requires at least 2 sources for pair-wise comparison")
                
                for i in range(num_sources):
                    source_dir = st.session_state.get(f'source_dir_{i}', "")
                    if not source_dir:
                        config_valid = False
                        validation_errors.append(f"Source {i+1} directory is required")
                    
                    # Validate collection names
                    collection_name = st.session_state.get(f'collection_name_{i}', "")
                    if not collection_name:
                        config_valid = False
                        validation_errors.append(f"Collection {i+1} name is required")
                
                dedup_db = st.session_state.get('dedup_db_name', "")
                if not dedup_db:
                    config_valid = False
                    validation_errors.append("Database name is required")
                
                meta_db = st.session_state.get('metadata_db_name', "")
                if not meta_db:
                    config_valid = False
                    validation_errors.append("Metadata database name is required")
                
                dedup_meta_coll = st.session_state.get('dedup_metadata_collection_name', "")
                if not dedup_meta_coll:
                    config_valid = False
                    validation_errors.append("Deduplication metadata collection name is required")
                
                if config_valid:
                    if st.button("Start Deduplication", type="primary", use_container_width=True):
                        st.session_state.deduplication_running = True
                        st.session_state.deduplication_status = "running"
                        st.session_state.thread_started = False
                        st.session_state.deduplication_progress = 10  # Start at 10%
                        st.session_state.start_time = datetime.now()
                        st.rerun()
                else:
                    st.error("❌ Configuration incomplete. Please fill all required fields.")
                    with st.expander("🔍 Validation Errors", expanded=False):
                        for error in validation_errors:
                            st.error(f"• {error}")
        
        with col2:
            if st.session_state.deduplication_running:
                if st.button("Stop Deduplication", type="secondary", use_container_width=True):
                    st.session_state.deduplication_running = False
                    st.session_state.deduplication_status = "stopped"
                    st.session_state.thread_started = False
                    st.rerun()
        
        # Deduplication Status & Progress
        if st.session_state.deduplication_status != "idle":
            st.markdown("### 📊 Deduplication Status")
            
            status = st.session_state.deduplication_status
            if status == "running":
                st.info("🔄 Deduplication in progress...")
                if st.session_state.start_time:
                    elapsed = datetime.now() - st.session_state.start_time
                    st.metric("Elapsed Time", f"{elapsed.seconds}s")
            elif status == "completed":
                st.success("✅ Deduplication completed successfully!")
                st.info("🔓 Configuration unlocked - you can now run unification")
            elif status == "error":
                st.error("❌ Deduplication failed")
                st.info("🔓 Configuration unlocked - you can try again")
            elif status == "stopped":
                st.warning("⏹️ Deduplication stopped")
                st.info("🔓 Configuration unlocked")
            
            # Progress bar
            if st.session_state.deduplication_progress > 0:
                st.progress(st.session_state.deduplication_progress / 100)
                st.text(f"Progress: {st.session_state.deduplication_progress}%")
            
            # Estimated time remaining
            if st.session_state.start_time and st.session_state.deduplication_progress > 0:
                elapsed = datetime.now() - st.session_state.start_time
                if st.session_state.deduplication_progress < 100:
                    estimated_total = elapsed.seconds * 100 / st.session_state.deduplication_progress
                    remaining = estimated_total - elapsed.seconds
                    st.text(f"Estimated time remaining: {remaining:.0f}s")
        
        # Deduplication Results
        st.markdown("### Deduplication Results")
        last_metadata = get_last_deduplication_metadata()
        
        if last_metadata:
            session = last_metadata.get("deduplication_session", {})
            
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                st.metric("Files Compared", session.get("total_files_compared", 0))
            with col_b:
                st.metric("Duplicate Groups", session.get("duplicate_groups_found", 0))
            with col_c:
                st.metric("Duplicates Removed", session.get("total_duplicates_removed", 0))
            with col_d:
                st.metric("Model Used", session.get("model_used", "Unknown"))
            
            # View detailed results
            if st.button("View Detailed Deduplication Results", use_container_width=True):
                st.session_state.show_dedup_detailed_results = True
            
            if st.session_state.get('show_dedup_detailed_results', False):
                with st.expander("Detailed Deduplication Results", expanded=True):
                    st.json(last_metadata)
        else:
            st.info("No previous deduplication sessions found")
        
        # Deduplication Logs
        st.markdown("### 📋 Deduplication Logs")
        
        # Clear deduplication logs button
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🗑️ Clear Deduplication Logs", type="secondary"):
                st.session_state.deduplication_logs = ""
                st.rerun()
        
        # Deduplication log display
        if st.session_state.deduplication_logs:
            st.code(st.session_state.deduplication_logs, language="text")
        else:
            st.info("No deduplication logs available yet. Start deduplication to see progress.")
    
    # Unification Section
    st.markdown("---")
    st.markdown("## 🔄 Schema Unification")
    st.markdown("### Unify deduplicated documents to a common schema using GPT-4")
    
    # Configuration lock warning
    if st.session_state.unification_running:
        st.markdown("""
        <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 0.5rem; padding: 1rem; margin: 1rem 0;">
            <h4 style="color: #856404; margin: 0;">🔒 Unification Configuration Locked</h4>
            <p style="color: #856404; margin: 0.5rem 0 0 0;">Unification settings are frozen during processing to ensure consistency.</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Source Configuration
    st.markdown("### 📝 Source Configuration")
    
    # Number of sources (unlimited for unification)
    num_sources = st.number_input(
        "Number of Sources",
        min_value=1,
        max_value=50,
        value=2,
        help="How many data sources do you want to unify? (Unlimited for unification)",
        disabled=st.session_state.unification_running
    )
    
    # Clear existing collections if number changed
    if len(st.session_state.discovered_collections) != num_sources:
        st.session_state.discovered_collections = []
    
    # Add source inputs
    for i in range(num_sources):
        st.markdown(f"#### Source {i+1}")
        col1, col2 = st.columns(2)
        
        with col1:
            db_name = st.text_input(
                f"Database Name (Source {i+1})",
                value=st.session_state[f"source_{i}_db"],
                help=f"Database name for source {i+1}",
                key=f"db_{i}",
                disabled=st.session_state.unification_running
            )
            # Update session state when input changes
            if db_name != st.session_state[f"source_{i}_db"]:
                st.session_state[f"source_{i}_db"] = db_name
        
        with col2:
            collection_name = st.text_input(
                f"Collection Name (Source {i+1})",
                value=st.session_state[f"source_{i}_collection"],
                help=f"Collection name for source {i+1}",
                key=f"coll_{i}",
                disabled=st.session_state.unification_running
            )
            # Update session state when input changes
            if collection_name != st.session_state[f"source_{i}_collection"]:
                st.session_state[f"source_{i}_collection"] = collection_name
        
        # Add to collections list if not already there
        if i < len(st.session_state.discovered_collections):
            st.session_state.discovered_collections[i] = {
                "db_name": db_name,
                "collection_name": collection_name,
                "key": "case_title",  # Primary key field for document identification
                "filename_field": "filename",  # Field name that contains filename in documents
                "document_count": 0  # Will be updated when validated
            }
        else:
            st.session_state.discovered_collections.append({
                "db_name": db_name,
                "collection_name": collection_name,
                "key": "case_title",  # Primary key field for document identification
                "filename_field": "filename",  # Field name that contains filename in documents
                "document_count": 0  # Will be updated when validated
            })
    
    # Validate collections button
    if st.button("🔍 Validate Collections", disabled=st.session_state.unification_running):
        try:
            client = MongoClient(mongo_uri)
            valid_collections = []
            total_docs = 0
            
            for i, coll in enumerate(st.session_state.discovered_collections):
                try:
                    db = client[coll["db_name"]]
                    collection = db[coll["collection_name"]]
                    doc_count = collection.count_documents({})
                    
                    if doc_count > 0:
                        coll["document_count"] = doc_count
                        valid_collections.append(coll)
                        total_docs += doc_count
                        st.success(f"✅ Source {i+1}: {coll['db_name']}.{coll['collection_name']} ({doc_count} docs)")
                    else:
                        st.error(f"❌ Source {i+1}: Collection is empty or doesn't exist")
                except Exception as e:
                    st.error(f"❌ Source {i+1}: Error accessing collection - {e}")
            
            if valid_collections:
                st.session_state.discovered_collections = valid_collections
                st.success(f"🎉 Validated {len(valid_collections)} sources with {total_docs} total documents")
            else:
                st.error("❌ No valid collections found")
                
        except Exception as e:
            st.error(f"❌ Error validating collections: {e}")
    
    # Display configured sources
    if st.session_state.discovered_collections:
        st.markdown("### 📋 Configured Sources")
        for i, coll in enumerate(st.session_state.discovered_collections):
            col1, col2 = st.columns([3, 1])
            with col1:
                status_icon = "✅" if coll['document_count'] > 0 else "⚠️"
                st.text(f"{status_icon} Source {i+1}: {coll['db_name']}.{coll['collection_name']} ({coll['document_count']} docs)")
            with col2:
                if st.button(f"🗑️ Remove", key=f"remove_{i}", disabled=st.session_state.unification_running):
                    st.session_state.discovered_collections.pop(i)
                    st.rerun()
    else:
        st.info("💡 Configure your sources above and validate them to proceed")
    
            # Schema Generation
        st.markdown("### 🔧 Schema Generation")
        
        # Clear separation between Deduplication and Unification sections
        st.markdown("---")
        st.markdown("## 🔄 Unification")
    
    if st.button("Generate Unified Schema", disabled=st.session_state.unification_running):
        if st.session_state.discovered_collections:
            try:
                # Initialize unification engine with metadata parameters for schema generation
                metadata_db_name = st.session_state.get('metadata_db_name', '')
                unify_metadata_collection_name = st.session_state.get('unify_metadata_collection_name', '')
                engine = UnificationEngine(mongo_uri, metadata_db_name, unify_metadata_collection_name)
                max_key_doc = engine.find_max_key_document(st.session_state.discovered_collections)
                
                if max_key_doc:
                    unified_schema = engine.get_schema(max_key_doc)
                    
                    # Save schema to file
                    schema_file_path = os.path.join(PROJECT_ROOT, "unified_schema.json")
                    with open(schema_file_path, 'w') as f:
                        json.dump(unified_schema, f, indent=2, default=str)
                    
                    st.success(f"✅ Unified schema generated with {len(unified_schema)} fields")
                    st.info(f"📁 Schema saved to: {schema_file_path}")
                    
                    # Display schema preview
                    with st.expander("📋 View Generated Schema", expanded=False):
                        st.json(unified_schema)
                else:
                    st.error("❌ No documents found to generate schema")
            except Exception as e:
                st.error(f"❌ Error generating schema: {e}")
        else:
            st.warning("⚠️ Please add collections first")
    
    # Unification Control
    st.markdown("### 1️⃣ Start Unification")
    
    # Unification controls
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.session_state.unification_running:
            st.warning("🔄 Unification is currently running...")
        else:
            # Validate unification configuration before allowing start
            unification_config_valid = True
            unification_validation_errors = []
            
            # Check if at least 1 source is configured
            if num_sources < 1:
                unification_config_valid = False
                unification_validation_errors.append("Unification requires at least 1 source")
            
            # Check if all configured sources have valid DB and collection names
            for i in range(num_sources):
                db_name = st.session_state.get(f"source_{i}_db", "")
                collection_name = st.session_state.get(f"source_{i}_collection", "")
                if not db_name:
                    unification_config_valid = False
                    unification_validation_errors.append(f"Source {i+1} database name is required")
                if not collection_name:
                    unification_config_valid = False
                    unification_validation_errors.append(f"Source {i+1} collection name is required")
            
            # Check if unified DB and collection names are configured
            unified_db = st.session_state.get('unified_db_name', "")
            unified_collection = st.session_state.get('unified_collection_name', "")
            if not unified_db:
                unification_config_valid = False
                unification_validation_errors.append("Unified database name is required")
            if not unified_collection:
                unification_config_valid = False
                unification_validation_errors.append("Unified collection name is required")
            
            # Check if metadata configuration is complete
            metadata_db = st.session_state.get('metadata_db_name', "")
            unify_metadata_collection = st.session_state.get('unify_metadata_collection_name', "")
            if not metadata_db:
                unification_config_valid = False
                unification_validation_errors.append("Metadata database name is required")
            if not unify_metadata_collection:
                unification_config_valid = False
                unification_validation_errors.append("Unification metadata collection name is required")
            
            if unification_config_valid:
                if st.button("Start Schema Unification", type="primary", use_container_width=True):
                    st.session_state.unification_running = True
                    st.session_state.unification_status = "running"
                    st.session_state.unification_thread_started = False
                    st.rerun()
            else:
                st.error("❌ Unification configuration incomplete. Please fill all required fields.")
                with st.expander("Unification Validation Errors", expanded=False):
                    for error in unification_validation_errors:
                        st.error(f"• {error}")
    
    with col2:
        if st.session_state.unification_running:
            if st.button("Stop Unification", type="secondary", use_container_width=True):
                st.session_state.unification_running = False
                st.session_state.unification_status = "stopped"
                st.session_state.unification_thread_started = False
                st.rerun()
    
    # Results display
    if st.session_state.unification_results:
        results = st.session_state.unification_results
        if results.get('success'):
            st.markdown("### Unification Results")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Processed", results['total_processed'])
            with col2:
                st.metric("Unified", results['total_unified'])
            with col3:
                st.metric("Schema Keys", results['unified_schema_keys'])
            with col4:
                st.metric("Duration", f"{results['duration']:.1f}s")
            
            # Show batch processing info
            if results.get('use_batch_processing'):
                st.info(f"📦 Batch processing used with batch size: {results.get('batch_size', 5)}")
    
    # Unification Results from Metadata
    st.markdown("### 📊 Previous Unification Sessions")
    
    # Only try to get metadata if we have valid configuration
    metadata_db_name = st.session_state.get('metadata_db_name', "")
    if metadata_db_name:
        try:
            last_unification_metadata = get_last_unification_metadata()
            
            if last_unification_metadata:
                session = last_unification_metadata.get("unification_session", {})
                
                col_a, col_b, col_c, col_d = st.columns(4)
                with col_a:
                    st.metric("Sources", session.get("total_sources", 0))
                with col_b:
                    st.metric("Documents Processed", session.get("total_processed", 0))
                with col_c:
                    st.metric("Documents Unified", session.get("total_unified", 0))
                with col_d:
                    st.metric("Schema Keys", session.get("unified_schema_keys", 0))
                
                # View detailed results
                if st.button("📋 View Detailed Unification Results", key="unification_detailed", use_container_width=True):
                    st.session_state.show_unification_detailed_results = True
                
                if st.session_state.get('show_unification_detailed_results', False):
                    with st.expander("📊 Detailed Unification Results", expanded=True):
                        st.json(last_unification_metadata)
            else:
                st.info("No previous unification sessions found")
        except Exception as e:
            st.warning(f"⚠️ Could not load previous metadata: {str(e)}")
            st.info("Previous sessions will be available after configuration is complete")
    else:
        st.info("💡 Configure metadata database to view previous unification sessions")
    
    # Unification Logs
    st.markdown("### 📋 Unification Logs")
    
    # Clear unification logs button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Clear Unification Logs", type="secondary"):
            st.session_state.unification_logs = ""
            st.rerun()
    
    # Unification log display
    if st.session_state.unification_logs:
        st.code(st.session_state.unification_logs, language="text")
    else:
        st.info("No unification logs available yet. Start unification to see progress.")
    
    # Run deduplication if requested - ONLY ONCE
    if (st.session_state.deduplication_running and 
        st.session_state.deduplication_status == "running" and 
        not st.session_state.thread_started):
        
        # Initialize logger
        logger = StreamlitLogger()
        logger.start_capture()
        st.session_state.logger = logger
        
        # Get configuration from session state
        mongo_uri = st.session_state.mongo_uri
        similarity_threshold = st.session_state.similarity_threshold
        # Use the first source directory as merge_dir for deduplication
        merge_dir = st.session_state.get('source_dir_0', ".")
        
        # Get database name and collection names for deduplication
        dedup_db_name = st.session_state.get('dedup_db_name', '')
        collection_names = []
        num_sources = st.session_state.get('num_sources_dedup', 2)
        for i in range(num_sources):
            collection_name = st.session_state.get(f'collection_name_{i}', '')
            if collection_name:
                collection_names.append(collection_name)
        
        # Get metadata configuration for deduplication
        metadata_db_name = st.session_state.get('metadata_db_name', '')
        dedup_metadata_collection_name = st.session_state.get('dedup_metadata_collection_name', '')
        
        # Start deduplication in a separate thread - ONLY ONCE
        deduplication_thread = threading.Thread(
            target=run_deduplication_thread,
            args=(mongo_uri, similarity_threshold, merge_dir, dedup_db_name, collection_names, metadata_db_name, dedup_metadata_collection_name, logger)
        )
        deduplication_thread.daemon = True
        deduplication_thread.start()
        
        # Mark thread as started to prevent multiple threads
        st.session_state.thread_started = True
        st.session_state.deduplication_progress = 25  # Thread started
        
        # Auto-refresh during deduplication
        time.sleep(1)
        st.rerun()
    
    # Auto-refresh logs when running - but don't create new threads
    if st.session_state.deduplication_running and st.session_state.thread_started:
        # Update logs from logger if available
        if st.session_state.logger:
            logs = st.session_state.logger.get_logs()
            if logs:
                st.session_state.deduplication_logs = logs
        
        # Update progress based on logs (simple heuristic)
        if "Starting vectorized duplicate detection" in st.session_state.deduplication_logs:
            st.session_state.deduplication_progress = 50
        elif "Calculating similarity matrices" in st.session_state.deduplication_logs:
            st.session_state.deduplication_progress = 75
        elif "Found" in st.session_state.deduplication_logs and "duplicate groups" in st.session_state.deduplication_logs:
            st.session_state.deduplication_progress = 90
        elif "completed successfully" in st.session_state.deduplication_logs:
            st.session_state.deduplication_progress = 100
        
        # Auto-refresh every 2 seconds during deduplication
        time.sleep(2)
        st.rerun()
    
    # Run unification if requested - ONLY ONCE
    if (st.session_state.unification_running and 
        st.session_state.unification_status == "running" and 
        not st.session_state.unification_thread_started):
        
        # Initialize logger for unification
        unification_logger = StreamlitLogger()
        unification_logger.start_capture()
        st.session_state.unification_logger = unification_logger
        
        # Get configuration from session state
        mongo_uri = st.session_state.mongo_uri
        unified_db_name = st.session_state.unified_db_name
        unified_collection_name = st.session_state.unified_collection_name
        
        # Build collections info from discovered collections (validated sources)
        final_collections_info = []
        if st.session_state.discovered_collections:
            final_collections_info = st.session_state.discovered_collections.copy()
            # Ensure all discovered collections have the key field
            for coll in final_collections_info:
                if 'key' not in coll:
                    coll['key'] = 'case_title'  # Default key field
        else:
            # Fallback to session state sources if no discovered collections
            num_sources = st.session_state.num_sources
            for i in range(num_sources):
                db_name = st.session_state[f"source_{i}_db"]
                collection_name = st.session_state[f"source_{i}_collection"]
                final_collections_info.append({
                    "db_name": db_name,
                    "collection_name": collection_name,
                    "key": "case_title",  # Primary key field for document identification
                    "filename_field": "filename"  # Field name that contains filename in documents
                })
        
        # Get processing options from sidebar
        use_batch_processing = False # Single document processing
        batch_size = 1 # Single document processing
        
        # Get metadata configuration for unification
        metadata_db_name = st.session_state.get('metadata_db_name', '')
        unify_metadata_collection_name = st.session_state.get('unify_metadata_collection_name', '')
        
        # Start unification in a separate thread - ONLY ONCE
        unification_thread = threading.Thread(
            target=run_unification_thread,
            args=(mongo_uri, final_collections_info, unified_db_name, unified_collection_name, metadata_db_name, unify_metadata_collection_name, unification_logger)
        )
        unification_thread.daemon = True
        unification_thread.start()
        
        # Mark thread as started to prevent multiple threads
        st.session_state.unification_thread_started = True
        st.session_state.unification_progress = 10  # Thread started
        
        # Auto-refresh during unification
        time.sleep(1)
        st.rerun()
    
    # Auto-refresh unification logs when running - but don't create new threads
    if st.session_state.unification_running and st.session_state.unification_thread_started:
        # Update logs from logger if available
        if hasattr(st.session_state, 'unification_logger'):
            logs = st.session_state.unification_logger.get_logs()
            if logs:
                st.session_state.unification_logs = logs
                
                # Check if process has stopped due to error or completion
                if ("❌ Unification failed:" in logs and "Process will stop automatically" in logs) or \
                   ("✅ Unification completed successfully!" in logs) or \
                   ("🎉 Unification completed successfully!" in logs):
                    st.session_state.unification_running = False
                    st.session_state.unification_thread_started = False
                    st.rerun()
        
        # Auto-refresh every 1 second during unification for better responsiveness
        time.sleep(1)
        st.rerun()

if __name__ == "__main__":
    main()
