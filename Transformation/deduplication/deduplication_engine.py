import os
import sys
import json
import hashlib
import shutil
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import numpy as np
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import logging

# Import send2trash for system recycle bin functionality
try:
    import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False
    print("⚠️ send2trash not available. Will use local trash directory.")

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import model manager
from model_manager import get_deduplication_model

# Global model instance to avoid multiple loads
_global_model = None

def get_global_model():
    """Get global model instance - loads only once"""
    global _global_model
    if _global_model is None:
        _global_model = get_deduplication_model()
    return _global_model

class DeduplicationEngine:
    """
    Optimized deduplication engine for legal documents with NumPy-accelerated semantic similarity comparison.
    Uses batch processing and vectorized operations for maximum performance.
    """
    
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", 
                 similarity_threshold: float = 0.85, db_name: str = "final_data"):
        """
        Initialize the deduplication engine.
        
        Args:
            mongo_uri: MongoDB connection string
            similarity_threshold: Threshold for semantic similarity (0.0 to 1.0)
            db_name: Database name to use for deduplication
        """
        self.mongo_uri = mongo_uri
        self.similarity_threshold = similarity_threshold
        self.model_name = "paraphrase-MiniLM-L3-v2"
        self.db_name = db_name
        
        # Setup logging first
        self.setup_logging()
        
        # Initialize MongoDB connection
        self.client = MongoClient(mongo_uri)
        self.final_db = self.client[db_name]
        
        # Get global model instance (loads only once)
        self.model = get_global_model()
        if self.model is None:
            raise RuntimeError("Failed to load paraphrase-MiniLM-L3-v2 model. Please run 'python verify_model.py' first.")
        self.log_to_ui(f"Loaded sentence transformer model: {self.model_name}")
        
        # Metadata tracking
        self.deduplication_metadata = {
            "deduplication_session": {
                "start_time": datetime.now().isoformat(),
                "model_used": self.model_name,
                "similarity_threshold": similarity_threshold,
                "total_files_compared": 0,
                "duplicate_groups_found": 0,
                "total_duplicates_removed": 0,
                "duplicate_groups": []
            }
        }
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('deduplication.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Add a custom logger that can be used for UI output
        self.ui_logger = None
    
    def set_ui_logger(self, ui_logger):
        """Set a UI logger for real-time output."""
        self.ui_logger = ui_logger
    
    def log_to_ui(self, message):
        """Log message to UI if available, otherwise to console."""
        if self.ui_logger:
            self.ui_logger.write(message)
        else:
            self.logger.info(message)
    
    def get_field_value(self, doc: Dict, field_name: str) -> str:
        """
        Safely extract field value from document, handling nested structures.
        
        Args:
            doc: Document dictionary
            field_name: Field name to extract
            
        Returns:
            Extracted value as string, or empty string if not found
        """
        try:
            value = doc.get(field_name, "")
            if isinstance(value, (list, dict)):
                # Convert complex structures to string representation
                return json.dumps(value, sort_keys=True, ensure_ascii=False)
            return str(value) if value is not None else ""
        except Exception:
            return ""
    
    def count_json_fields(self, doc: Dict) -> int:
        """
        Count total number of fields in JSON document.
        
        Args:
            doc: Document dictionary
            
        Returns:
            Number of fields
        """
        def count_fields_recursive(obj):
            if isinstance(obj, dict):
                return sum(1 + count_fields_recursive(v) for v in obj.values())
            elif isinstance(obj, list):
                return sum(count_fields_recursive(item) for item in obj)
            else:
                return 0
        
        return count_fields_recursive(doc)
    
    def batch_encode_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Encode texts in batches for better performance.
        
        Args:
            texts: List of text strings to encode
            batch_size: Batch size for processing
            
        Returns:
            NumPy array of embeddings
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = self.model.encode(batch_texts)
            all_embeddings.append(batch_embeddings)
        
        return np.vstack(all_embeddings)
    
    def find_duplicates_vectorized(self, docs1: List[Dict], docs2: List[Dict]) -> List[List[Dict]]:
        """
        Find duplicates using NumPy-optimized vectorized operations.
        
        Args:
            docs1: List of documents from first collection
            docs2: List of documents from second collection
            
        Returns:
            List of duplicate groups
        """
        if not docs1 or not docs2:
            return []
        
        self.logger.info(f"Starting vectorized duplicate detection...")
        self.logger.info(f"Collection 1 docs: {len(docs1)}, Collection 2 docs: {len(docs2)}")
        
        # Extract texts for batch processing
        docs1_titles = [self.get_field_value(doc, 'case_title') for doc in docs1]
        docs1_summaries = [self.get_field_value(doc, 'summary_vector_notes') for doc in docs1]
        docs2_titles = [self.get_field_value(doc, 'case_title') for doc in docs2]
        docs2_summaries = [self.get_field_value(doc, 'summary_vector_notes') for doc in docs2]
        
        # Filter out empty texts
        valid_docs1_indices = [i for i, (title, summary) in enumerate(zip(docs1_titles, docs1_summaries)) 
                              if title and summary]
        valid_docs2_indices = [i for i, (title, summary) in enumerate(zip(docs2_titles, docs2_summaries)) 
                              if title and summary]
        
        if not valid_docs1_indices or not valid_docs2_indices:
            self.logger.info("No valid documents for comparison")
            return []
        
        # Get valid texts
        valid_docs1_titles = [docs1_titles[i] for i in valid_docs1_indices]
        valid_docs1_summaries = [docs1_summaries[i] for i in valid_docs1_indices]
        valid_docs2_titles = [docs2_titles[i] for i in valid_docs2_indices]
        valid_docs2_summaries = [docs2_summaries[i] for i in valid_docs2_indices]
        
        self.logger.info(f"Processing {len(valid_docs1_titles)} valid docs from collection 1 vs {len(valid_docs2_titles)} valid docs from collection 2")
        
        # Batch encode all texts at once
        self.logger.info("Encoding collection 1 documents...")
        docs1_title_embeddings = self.batch_encode_texts(valid_docs1_titles)
        docs1_summary_embeddings = self.batch_encode_texts(valid_docs1_summaries)
        
        self.logger.info("Encoding collection 2 documents...")
        docs2_title_embeddings = self.batch_encode_texts(valid_docs2_titles)
        docs2_summary_embeddings = self.batch_encode_texts(valid_docs2_summaries)
        
        # Calculate similarity matrices using NumPy
        self.logger.info("Calculating similarity matrices...")
        title_similarities = cosine_similarity(docs1_title_embeddings, docs2_title_embeddings)
        summary_similarities = cosine_similarity(docs1_summary_embeddings, docs2_summary_embeddings)
        
        # Find duplicates using vectorized operations
        self.logger.info("Finding duplicates...")
        duplicate_groups = []
        processed_docs1 = set()
        processed_docs2 = set()
        
        # Find pairs where both title and summary are similar
        duplicate_pairs = np.where((title_similarities >= self.similarity_threshold) & 
                                  (summary_similarities >= self.similarity_threshold))
        
        # Group duplicates
        for docs1_idx, docs2_idx in zip(duplicate_pairs[0], duplicate_pairs[1]):
            if docs1_idx in processed_docs1 or docs2_idx in processed_docs2:
                continue
            
            # Get original document indices
            original_docs1_idx = valid_docs1_indices[docs1_idx]
            original_docs2_idx = valid_docs2_indices[docs2_idx]
            
            # Create duplicate group
            duplicate_group = [docs1[original_docs1_idx], docs2[original_docs2_idx]]
            
            # Log similarity scores
            title_sim = title_similarities[docs1_idx, docs2_idx]
            summary_sim = summary_similarities[docs1_idx, docs2_idx]
            
            self.logger.info(f"Found duplicate: Collection 1 doc {original_docs1_idx} ↔ Collection 2 doc {original_docs2_idx}")
            self.logger.info(f"   Title similarity: {title_sim:.3f}, Summary similarity: {summary_sim:.3f}")
            
            duplicate_groups.append(duplicate_group)
            processed_docs1.add(docs1_idx)
            processed_docs2.add(docs2_idx)
        
        self.logger.info(f"Found {len(duplicate_groups)} duplicate groups")
        return duplicate_groups
    
    def select_kept_document(self, duplicate_group: List[Dict]) -> Tuple[Dict, List[Dict]]:
        """
        Select which document to keep from a duplicate group.
        
        Args:
            duplicate_group: List of duplicate documents
            
        Returns:
            Tuple of (kept_document, removed_documents)
        """
        # Sort by number of fields (ascending - fewer fields wins)
        sorted_group = sorted(duplicate_group, key=self.count_json_fields)
        
        kept_document = sorted_group[0]
        removed_documents = sorted_group[1:]
        
        return kept_document, removed_documents
    
    def delete_document_from_db(self, doc: Dict, collection_name: str = None) -> bool:
        """
        Delete document from MongoDB.
        
        Args:
            doc: Document to delete
            collection_name: Name of the collection to delete from (if not provided, will try to infer)
            
        Returns:
            True if deletion was successful
        """
        try:
            if collection_name:
                # Use the provided collection name
                collection = self.final_db[collection_name]
            else:
                # Try to infer collection name from source_web (fallback)
                source_web = doc.get("source_web", "")
                if source_web:
                    # Try different possible collection name patterns
                    possible_names = [
                        f"{source_web}_cases",
                        f"{source_web}_merge",
                        source_web
                    ]
                    
                    for name in possible_names:
                        if name in self.final_db.list_collection_names():
                            collection = self.final_db[name]
                            break
                    else:
                        self.logger.error(f"Could not find collection for source_web: {source_web}")
                        return False
                else:
                    self.logger.error("No collection_name provided and no source_web found in document")
                    return False
            
            result = collection.delete_one({"_id": doc["_id"]})
            return result.deleted_count > 0
        except Exception as e:
            self.logger.error(f"Error deleting document from DB: {e}")
            return False
    
    def send_file_to_trash(self, doc: Dict, merge_dir: str) -> bool:
        """
        Send document file to system recycle bin instead of permanent deletion.
        
        Args:
            doc: Document metadata
            merge_dir: Directory containing the files
            
        Returns:
            True if move to recycle bin was successful
        """
        try:
            filename = doc.get("filename", "")
            if not filename:
                return False
            
            file_path = os.path.join(merge_dir, filename)
            if not os.path.exists(file_path):
                return False
            
            # Use system recycle bin if available
            if SEND2TRASH_AVAILABLE:
                send2trash.send2trash(file_path)
            else:
                # Fallback to local trash directory
                trash_dir = os.path.join(merge_dir, "trash")
                os.makedirs(trash_dir, exist_ok=True)
                trash_path = os.path.join(trash_dir, filename)
                shutil.move(file_path, trash_path)
            
            self.logger.info(f"Moved {filename} to recycle bin")
            return True
        except Exception as e:
            self.logger.error(f"Error moving file {filename} to recycle bin: {e}")
            return False
    
    def deduplicate_all_documents(self, merge_dir: str, collection_names: List[str] = None) -> Dict[str, Any]:
        """
        Deduplicate documents using NumPy-optimized vectorized operations.
        
        Args:
            merge_dir: Directory containing merged JSON files
            collection_names: List of collection names to deduplicate
            
        Returns:
            Deduplication results and metadata
        """
        self.logger.info("Starting optimized deduplication with NumPy acceleration")
        
        # Update progress: 10% - Starting
        try:
            import streamlit as st
            if hasattr(st, 'session_state'):
                st.session_state.deduplication_progress = 10
        except ImportError:
            pass
        
        # Use provided collection names
        if collection_names and len(collection_names) >= 2:
            collection1_name = collection_names[0]
            collection2_name = collection_names[1]
            self.logger.info(f"Using provided collection names: {collection1_name} and {collection2_name}")
        else:
            # No fallback - require collection names to be provided
            self.logger.error("No collection names provided. Deduplication requires at least 2 collection names.")
            return {
                "collection1_documents": 0,
                "collection2_documents": 0,
                "duplicate_groups_found": 0,
                "duplicates_removed": 0,
                "duplicate_groups": [],
                "error": "No collection names provided"
            }
        
        # Get documents from both collections
        collection1 = self.final_db[collection1_name]
        collection2 = self.final_db[collection2_name]
        
        docs1 = list(collection1.find({}))
        docs2 = list(collection2.find({}))
        
        self.logger.info(f"Found {len(docs1)} documents in {collection1_name} and {len(docs2)} documents in {collection2_name}")
        
        # Update progress: 25% - Documents loaded
        try:
            import streamlit as st
            if hasattr(st, 'session_state'):
                st.session_state.deduplication_progress = 25
        except ImportError:
            pass
        
        # Update metadata
        total_comparisons = len(docs1) * len(docs2)
        self.deduplication_metadata["deduplication_session"]["total_files_compared"] = total_comparisons
        
        if len(docs1) == 0 or len(docs2) == 0:
            self.logger.info("No documents to compare")
            return {
                "collection1_documents": len(docs1),
                "collection2_documents": len(docs2),
                "duplicate_groups_found": 0,
                "duplicates_removed": 0,
                "duplicate_groups": []
            }
        
        # Find duplicates using vectorized operations
        duplicate_groups = self.find_duplicates_vectorized(docs1, docs2)
        
        # Update progress: 75% - Duplicates found
        try:
            import streamlit as st
            if hasattr(st, 'session_state'):
                st.session_state.deduplication_progress = 75
        except ImportError:
            pass
        
        # Process each duplicate group
        processed_groups = []
        total_removed = 0
        
        for group_idx, duplicate_group in enumerate(duplicate_groups):
            self.logger.info(f"Processing duplicate group {group_idx + 1}/{len(duplicate_groups)}")
            
            # Select which document to keep (fewer fields wins)
            kept_doc, removed_docs = self.select_kept_document(duplicate_group)
            
            # Delete removed documents from DB and move files to recycle bin
            removed_metadata = []
            for removed_doc in removed_docs:
                # Determine which collection this document belongs to
                # Check if it's from collection1 or collection2
                if removed_doc in docs1:
                    collection_name_to_delete = collection1_name
                elif removed_doc in docs2:
                    collection_name_to_delete = collection2_name
                else:
                    # Fallback: try to infer from source_web
                    collection_name_to_delete = None
                
                # Delete from DB first
                db_deleted = self.delete_document_from_db(removed_doc, collection_name_to_delete)
                
                # Move file to recycle bin
                file_moved = self.send_file_to_trash(removed_doc, merge_dir)
                
                removed_metadata.append({
                    "filename": removed_doc.get("filename", ""),
                    "source_web": removed_doc.get("source_web", ""),
                    "object_id": str(removed_doc.get("_id", "")),
                    "db_deleted": db_deleted,
                    "file_moved_to_recycle_bin": file_moved
                })
                
                if db_deleted:
                    total_removed += 1
            
            # Create group metadata
            group_metadata = {
                "group_id": group_idx + 1,
                "kept_document": {
                    "filename": kept_doc.get("filename", ""),
                    "source_web": kept_doc.get("source_web", ""),
                    "object_id": str(kept_doc.get("_id", "")),
                    "field_count": self.count_json_fields(kept_doc)
                },
                "removed_documents": removed_metadata,
                "total_in_group": len(duplicate_group)
            }
            
            processed_groups.append(group_metadata)
        
        # Update session metadata
        self.deduplication_metadata["deduplication_session"]["duplicate_groups_found"] = len(duplicate_groups)
        self.deduplication_metadata["deduplication_session"]["total_duplicates_removed"] = total_removed
        self.deduplication_metadata["deduplication_session"]["duplicate_groups"] = processed_groups
        
        # Update progress: 100% - Complete
        try:
            import streamlit as st
            if hasattr(st, 'session_state'):
                st.session_state.deduplication_progress = 100
        except ImportError:
            pass
        
        return {
            "collection1_documents": len(docs1),
            "collection2_documents": len(docs2),
            "duplicate_groups_found": len(duplicate_groups),
            "duplicates_removed": total_removed,
            "duplicate_groups": processed_groups
        }
    
    def save_deduplication_metadata(self, metadata: Dict[str, Any], metadata_db_name: str = None, metadata_collection_name: str = None) -> bool:
        """
        Save deduplication metadata to MongoDB.
        
        Args:
            metadata: Deduplication metadata
            metadata_db_name: Database name for metadata (uses configured value if provided)
            metadata_collection_name: Collection name for metadata (uses configured value if provided)
            
        Returns:
            True if save was successful
        """
        try:
            # Add end time
            metadata["deduplication_session"]["end_time"] = datetime.now().isoformat()
            
            # Use configured metadata database and collection names
            if metadata_db_name:
                metadata_db = self.client[metadata_db_name]
            else:
                self.logger.error("No metadata database name provided")
                return False
            
            if metadata_collection_name:
                metadata_collection = metadata_db[metadata_collection_name]
            else:
                self.logger.error("No metadata collection name provided")
                return False
            
            result = metadata_collection.insert_one(metadata)
            self.logger.info(f"Saved deduplication metadata with ID: {result.inserted_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving deduplication metadata: {e}")
            return False
    
    def get_deduplication_summary(self) -> Dict[str, Any]:
        """
        Get summary of current deduplication session.
        
        Returns:
            Summary of deduplication results
        """
        session = self.deduplication_metadata["deduplication_session"]
        return {
            "session_info": {
                "start_time": session["start_time"],
                "model_used": session["model_used"],
                "similarity_threshold": session["similarity_threshold"]
            },
            "results": {
                "total_files_compared": session["total_files_compared"],
                "duplicate_groups_found": session["duplicate_groups_found"],
                "total_duplicates_removed": session["total_duplicates_removed"]
            }
        }
    
    def close(self):
        """Clean up resources"""
        if hasattr(self, 'client'):
            self.client.close()
