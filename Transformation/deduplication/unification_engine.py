import os
import json
import logging
from typing import Dict, List, Any, Optional
from openai import AzureOpenAI
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime

load_dotenv()

class UnificationEngine:
    """
    Engine for unifying schema across different legal document collections.
    """
    
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", 
                 metadata_db_name: str = None, metadata_collection_name: str = None):
        """
        Initialize the unification engine.
        
        Args:
            mongo_uri: MongoDB connection URI
            metadata_db_name: Database name for metadata storage
            metadata_collection_name: Collection name for metadata storage
        """
        self.mongo_uri = mongo_uri
        self.mongo_client = MongoClient(mongo_uri)
        self.metadata_db_name = metadata_db_name
        self.metadata_collection_name = metadata_collection_name
        self.setup_logging()
        
        # Initialize OpenAI client with values from environment variables
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-11-01-preview"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        self.logger.info("Unification engine initialized successfully")
    
    def setup_logging(self):
        """Setup logging configuration."""
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
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
    
    def get_schema(self, doc: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract schema from a document.
        
        Args:
            doc: Document to analyze
            
        Returns:
            Schema dictionary with field names and types
        """
        schema = {}
        for key, value in doc.items():
            # Skip _id field - MongoDB will auto-generate it
            if key != "_id":
                schema[key] = type(value).__name__
        return schema
    
    def find_max_key_document(self, final_collections_info: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """
        Find the document with the maximum number of keys across all collections.
        
        Args:
            final_collections_info: List of collection information
            
        Returns:
            Document with maximum keys or None
        """
        highest_key_doc = None
        highest_key_count = 0
        
        self.log_to_ui("Searching for document with maximum schema complexity...")
        self.log_to_ui(f"Collections to search: {final_collections_info}")
        
        for source in final_collections_info:
            db_name = source["db_name"]
            collection_name = source["collection_name"]
            self.log_to_ui(f"Checking collection: {db_name}.{collection_name}")
            
            try:
                collection = self.mongo_client[db_name][collection_name]
                doc_count = collection.count_documents({})
                self.log_to_ui(f"Found {doc_count} documents in {db_name}.{collection_name}")
                
                if doc_count == 0:
                    self.log_to_ui(f"⚠️ No documents found in {db_name}.{collection_name}")
                    continue
                
                max_key_doc = None
                max_key_count = 0
                
                for doc in collection.find():
                    key_count = len(doc.keys())
                    if key_count > max_key_count:
                        max_key_count = key_count
                        max_key_doc = doc
                
                if max_key_doc:
                    self.log_to_ui(f"Found max key document in '{db_name}.{collection_name}' with {max_key_count} keys")
                    if max_key_count > highest_key_count:
                        highest_key_count = max_key_count
                        highest_key_doc = max_key_doc
                        
            except Exception as e:
                self.log_to_ui(f"❌ Error accessing collection {db_name}.{collection_name}: {e}")
        
        if highest_key_doc:
            self.log_to_ui(f"Selected unified schema with {highest_key_count} keys")
        else:
            self.log_to_ui("❌ No documents found to create unified schema")
            
        return highest_key_doc
    
    def unify_document(self, doc: Dict[str, Any], unified_schema: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Unify a single document to match the target schema using GPT.
        
        Args:
            doc: Document to unify
            unified_schema: Target schema to conform to
            
        Returns:
            Unified document or None if failed
        """
        try:
            # Remove _id for processing
            doc_copy = doc.copy()
            doc_copy.pop("_id", None)
            
            # Construct GPT prompt
            system_prompt = """You are an expert legal data normalizer specializing in legal documents. Your task is to conform JSON documents to a consistent schema while maintaining data integrity and legal accuracy.

CRITICAL RULES:
1. Return ONLY valid JSON - no markdown, no explanations, no extra text
2. Preserve all original information - never lose data
3. Use "N/A" for missing fields, never leave them empty
4. Maintain data types as specified in the schema
5. For legal names, preserve exact spelling and formatting
6. For dates, maintain consistent format (YYYY-MM-DD if possible)
7. For lists, ensure they are proper JSON arrays
8. For nested objects, maintain structure integrity"""

            user_prompt = f"""
You are normalizing a legal case document to match a unified schema. This is for legal cases from legal data sources.

SCHEMA DEFINITION:
{json.dumps(unified_schema, indent=2, default=str)}

SOURCE DOCUMENT:
{json.dumps(doc_copy, indent=2, default=str)}

INSTRUCTIONS:
1. Map fields intelligently - look for similar field names and content
2. Extract information from text fields if needed (e.g., extract parties from case title)
3. Handle data type conversions properly (string to list, etc.)
4. For missing fields, use "N/A"
5. Preserve all original data - don't lose any information
6. Ensure the output matches the exact schema structure

Return ONLY the unified JSON object with no additional text or formatting.
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0
            )
            
            unified_json = response.choices[0].message.content.strip()
            
            # Clean up the response - remove any markdown formatting
            if unified_json.startswith("```json"):
                unified_json = unified_json.replace("```json", "").replace("```", "").strip()
            elif unified_json.startswith("```"):
                unified_json = unified_json.replace("```", "").strip()
            
            unified_data = json.loads(unified_json)
            unified_data.pop("_id", None)
            
            # Validate that all schema fields are present
            missing_fields = []
            for field in unified_schema.keys():
                if field not in unified_data:
                    missing_fields.append(field)
                    unified_data[field] = "N/A"
            
            if missing_fields:
                self.logger.warning(f"GPT missed fields: {missing_fields}, added as 'N/A'")
            
            return unified_data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse GPT response as JSON: {e}")
            self.logger.debug(f"Raw GPT response: {unified_json}")
            return None
        except Exception as e:
            self.logger.error(f"Error unifying document: {e}")
            return None
    


    def unify_collections(
        self,
        final_collections_info: List[Dict[str, str]],
        unified_db_name: str,
        unified_collection_name: str,
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Unify all collections to a common schema.
        
        Args:
            final_collections_info: List of collection information
            unified_db_name: Target database name
            unified_collection_name: Target collection name
            progress_callback: Optional callback for progress updates
            
        Returns:
            Unification results and metadata
        """
        start_time = datetime.now()
        self.log_to_ui("🚀 Starting schema unification process...")
        
        # Note: Deduplication should be run first for best results
        self.log_to_ui("💡 Note: It's recommended to run deduplication first for best results")
        
        # Check if unified schema file exists, if not generate it automatically
        schema_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "unified_schema.json")
        if not os.path.exists(schema_file_path):
            self.log_to_ui("⚠️ Unified schema file not found. Generating automatically...")
            max_key_doc = self.find_max_key_document(final_collections_info)
            if max_key_doc:
                unified_schema = self.get_schema(max_key_doc)
                with open(schema_file_path, 'w') as f:
                    json.dump(unified_schema, f, indent=2, default=str)
                self.log_to_ui(f"✅ Auto-generated unified schema with {len(unified_schema)} fields")
            else:
                return {
                    "success": False,
                    "error": "No documents found to create unified schema",
                    "total_processed": 0,
                    "total_unified": 0,
                    "duration": 0
                }
        else:
            self.log_to_ui("✅ Found existing unified schema file")
            # Load existing schema instead of regenerating
            try:
                with open(schema_file_path, 'r') as f:
                    unified_schema = json.load(f)
                self.log_to_ui(f"📋 Loaded existing unified schema with {len(unified_schema)} keys")
            except Exception as e:
                self.log_to_ui(f"⚠️ Error loading existing schema, regenerating: {e}")
                # Fallback to regeneration if loading fails
                max_key_doc = self.find_max_key_document(final_collections_info)
                if max_key_doc:
                    unified_schema = self.get_schema(max_key_doc)
                    with open(schema_file_path, 'w') as f:
                        json.dump(unified_schema, f, indent=2, default=str)
                    self.log_to_ui(f"✅ Regenerated unified schema with {len(unified_schema)} fields")
                else:
                    return {
                        "success": False,
                        "error": "No documents found to create unified schema",
                        "total_processed": 0,
                        "total_unified": 0,
                        "duration": 0
                    }
        
        # Step 2: Get target collection
        unified_collection = self.mongo_client[unified_db_name][unified_collection_name]
        
        # Step 3: Process each collection
        total_processed = 0
        total_unified = 0
        total_documents = 0
        
        # Count total documents for progress tracking
        for info in final_collections_info:
            try:
                collection = self.mongo_client[info['db_name']][info['collection_name']]
                total_documents += collection.count_documents({})
            except Exception as e:
                self.log_to_ui(f"❌ Error counting documents in {info['db_name']}.{info['collection_name']}: {e}")
        
        self.log_to_ui(f"📊 Total documents to process: {total_documents}")
        
        # Process collections with single document processing (faster and more reliable)
        self.log_to_ui(f"⚡ Using single document processing for better performance")
        
        for info in final_collections_info:
            db_name = info['db_name']
            collection_name = info['collection_name']
            key_field = info['key']
            
            self.log_to_ui(f"🔄 Processing {db_name}.{collection_name}")
            
            try:
                collection = self.mongo_client[db_name][collection_name]
                
                for doc in collection.find():
                    total_processed += 1
                    file_id = str(doc.get(key_field, "Unknown_ID"))
                    
                    # Check if document already exists in unified collection
                    existing_doc = unified_collection.find_one({key_field: file_id})
                    if existing_doc:
                        self.log_to_ui(f"⏭️ Skipping document {file_id} - already exists in unified collection")
                        continue
                    
                    self.log_to_ui(f"📄 Unifying document {total_processed}/{total_documents}: {file_id}")
                    
                    unified_doc = self.unify_document(doc, unified_schema)
                    
                    if unified_doc:
                        try:
                            # Ensure _id is not present - MongoDB will auto-generate it
                            unified_doc.pop("_id", None)
                            
                            # Insert document
                            result = unified_collection.insert_one(unified_doc)
                            total_unified += 1
                            self.log_to_ui(f"✅ Successfully unified and inserted document: {file_id}")
                        except Exception as e:
                            self.log_to_ui(f"❌ Failed to insert unified document {file_id}: {e}")
                            # Log the problematic document for debugging
                            self.log_to_ui(f"🔍 Problematic document keys: {list(unified_doc.keys()) if unified_doc else 'None'}")
                    else:
                        self.log_to_ui(f"⚠️ Failed to unify document: {file_id}")
                    
                    # Update progress
                    if progress_callback:
                        progress = int((total_processed / total_documents) * 100)
                        progress_callback(progress)
                        
            except Exception as e:
                self.log_to_ui(f"❌ Error processing collection {db_name}.{collection_name}: {e}")
        
        duration = (datetime.now() - start_time).total_seconds()
        
        results = {
            "success": True,
            "total_processed": total_processed,
            "total_unified": total_unified,
            "unified_schema_keys": len(unified_schema),
            "duration": duration,
            "unified_schema": unified_schema,
            "use_batch_processing": False,  # Always false now
            "batch_size": 1  # Always 1 for single document processing
        }
        
        self.log_to_ui(f"🎉 Unification completed successfully!")
        self.log_to_ui(f"📊 Processed: {total_processed}, Unified: {total_unified}, Duration: {duration:.2f}s")
        
        # Save metadata to MongoDB
        try:
            if not self.metadata_db_name or not self.metadata_collection_name:
                self.log_to_ui(f"❌ Cannot save metadata: DB='{self.metadata_db_name}', Collection='{self.metadata_collection_name}'")
                self.log_to_ui(f"💡 Please configure metadata database and collection names in the UI")
                metadata_saved = False
            else:
                self.log_to_ui(f"💾 Attempting to save metadata to: {self.metadata_db_name}.{self.metadata_collection_name}")
                metadata_saved = self.save_unification_metadata(
                    results, final_collections_info, unified_db_name, unified_collection_name,
                    self.metadata_db_name, self.metadata_collection_name
                )
                if metadata_saved:
                    self.log_to_ui("💾 Unification metadata saved successfully")
                else:
                    self.log_to_ui("⚠️ Failed to save unification metadata")
        except Exception as e:
            self.log_to_ui(f"❌ Error saving metadata: {e}")
            metadata_saved = False
        
        return results

    def discover_collections(self, db_name: str, collection_pattern: str = None) -> List[Dict[str, str]]:
        """
        Dynamically discover collections in a database.
        
        Args:
            db_name: Database name to search
            collection_pattern: Optional pattern to filter collections (e.g., "*Cases*")
            
        Returns:
            List of collection information
        """
        try:
            db = self.mongo_client[db_name]
            collections = db.list_collection_names()
            
            discovered = []
            for collection_name in collections:
                # Apply pattern filter if provided
                if collection_pattern:
                    if collection_pattern not in collection_name:
                        continue
                
                # Try to determine the key field by sampling a document
                try:
                    sample_doc = db[collection_name].find_one()
                    if sample_doc:
                        # Common key field patterns
                        key_field = None
                        for field in ['journal_no', 'case_title', 'case_id', 'id', 'title']:
                            if field in sample_doc:
                                key_field = field
                                break
                        
                        if not key_field:
                            key_field = list(sample_doc.keys())[0]  # Use first field as fallback
                        
                        discovered.append({
                            "db_name": db_name,
                            "collection_name": collection_name,
                            "key": key_field,
                            "document_count": db[collection_name].count_documents({})
                        })
                        
                except Exception as e:
                    self.logger.warning(f"Could not analyze collection {collection_name}: {e}")
            
            self.logger.info(f"Discovered {len(discovered)} collections in {db_name}")
            return discovered
            
        except Exception as e:
            self.logger.error(f"Error discovering collections in {db_name}: {e}")
            return []
    

    
    def save_unification_metadata(self, result: Dict[str, Any], final_collections_info: List[Dict[str, str]], 
                                 unified_db_name: str, unified_collection_name: str, 
                                 metadata_db_name: str = None, metadata_collection_name: str = None) -> bool:
        """
        Save unification metadata to MongoDB.
        
        Args:
            result: Unification result dictionary
            final_collections_info: Source collections information
            unified_db_name: Target database name
            unified_collection_name: Target collection name
            metadata_db_name: Database name for metadata storage
            metadata_collection_name: Collection name for metadata storage
            
        Returns:
            True if metadata saved successfully, False otherwise
        """
        try:
            # Create metadata document
            metadata = {
                "unification_session": {
                    "start_time": datetime.now().isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "status": "completed" if result.get('success') else "failed",
                    "total_sources": len(final_collections_info),
                    "total_processed": result.get('total_processed', 0),
                    "total_unified": result.get('total_unified', 0),
                    "unified_schema_keys": result.get('unified_schema_keys', 0),
                    "duration_seconds": result.get('duration', 0),
                    "use_batch_processing": result.get('use_batch_processing', True),
                    "batch_size": result.get('batch_size', 5),
                    "error": result.get('error', None)
                },
                "source_collections": final_collections_info,
                "target_collection": {
                    "database": unified_db_name,
                    "collection": unified_collection_name
                },
                "unified_schema": result.get('unified_schema', {}),
                "created_at": datetime.now()
            }
            
            # Use provided metadata database and collection names
            if metadata_db_name:
                metadata_db = self.mongo_client[metadata_db_name]
            else:
                self.logger.error("No metadata database name provided")
                return False
            
            if metadata_collection_name:
                metadata_collection = metadata_db[metadata_collection_name]
            else:
                self.logger.error("No metadata collection name provided")
                return False
            
            # Insert metadata
            result_id = metadata_collection.insert_one(metadata)
            
            self.logger.info(f"Unification metadata saved with ID: {result_id.inserted_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving unification metadata: {e}")
            return False
    
    def get_last_unification_metadata(self, metadata_db_name: str = None, metadata_collection_name: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the most recent unification metadata from MongoDB.
        
        Args:
            metadata_db_name: Database name for metadata storage
            metadata_collection_name: Collection name for metadata storage
            
        Returns:
            Most recent metadata document or None
        """
        try:
            # Use provided metadata database and collection names
            if metadata_db_name:
                metadata_db = self.mongo_client[metadata_db_name]
            else:
                self.logger.error("No metadata database name provided")
                return None
            
            if metadata_collection_name:
                metadata_collection = metadata_db[metadata_collection_name]
            else:
                self.logger.error("No metadata collection name provided")
                return None
            
            # Get the most recent document
            last_metadata = metadata_collection.find_one(
                sort=[("unification_session.start_time", -1)]
            )
            
            if last_metadata:
                # Remove MongoDB internal fields
                last_metadata.pop("_id", None)
                return last_metadata
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Error retrieving unification metadata: {e}")
            return None
    
    def close(self):
        """Clean up resources"""
        if hasattr(self, 'mongo_client'):
            self.mongo_client.close()
