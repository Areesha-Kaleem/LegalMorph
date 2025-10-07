import streamlit as st
import threading
import time
import os
import sys
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
import openai
import json

# Ensure project root is on sys.path so absolute imports like `Transformation.*` work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import transformation functions
from Transformation.cases.phase1_base import base_json_gpt, base_issue_resolver
from Transformation.cases.phase2_custom import custom_json_gpt, custom_issue_resolver
from Transformation.cases.phase3_merge import merge_json_gpt, merge_issue_resolver
from Transformation.statutes.phase1_base import base_statute_json_gpt, base_statute_issue_resolver
from Transformation.statutes.phase2_custom import custom_statutes_json_gpt, custom_statute_issue_resolver
from Transformation.statutes.phase3_merge import merge_statutes_json_gpt, merge_statutes_issue_resolver
from Transformation.config.prompts import *
from pymongo import MongoClient

load_dotenv()

# MongoDB Configuration - No hardcoded values, all configurable through UI

# Azure OpenAI defaults (from environment variables with fallbacks)
DEFAULT_AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
DEFAULT_AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-11-01-preview")
DEFAULT_AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")

# === Dynamic/hardcoded configuration helpers ===
# Deployment is stable across runs; keep default as requested but allow env override for flexibility.
DEFAULT_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

def resolve_max_tokens(data_type: str, phase_name: str) -> int:
    """Resolve max_tokens dynamically from environment. Never from UI.
    Falls back to safe defaults if env is not provided.
    Env keys supported:
      TRANSFORM_MAX_TOKENS_{DATA}_{PHASE}
    e.g., TRANSFORM_MAX_TOKENS_CASES_BASE=8192
    """
    key = f"TRANSFORM_MAX_TOKENS_{data_type.upper()}_{phase_name.upper()}"
    try:
        value = int(os.getenv(key, "8192"))
        return max(1024, value)
    except Exception:
        return 8192

def resolve_issue_dir(data_type: str, phase_name: str, source_web: str) -> str:
    """Resolve issues directory path including source (e.g., data/base/issues_cases/eastlaw).
    Per guideline, this is hardcoded (not user-configurable) yet centralized for easy future changes.
    """
    phase_dir = "base" if phase_name == "Base" else "custom" if phase_name == "Custom" else "merge"
    issues_folder = f"issues_{data_type}"
    # Build absolute path under project root to avoid manual string escapes
    return os.path.join(PROJECT_ROOT, "data", phase_dir, issues_folder, source_web)

def resolve_merge_issue_dirs(data_type: str, source_web: str) -> tuple[str, str]:
    """Merge issues dirs under merge path with base/custom subfolders.
    Example (cases,eastlaw):
      data/merge/issues_cases/eastlaw/base
      data/merge/issues_cases/eastlaw/custom
    """
    issues_folder = f"issues_{data_type}"
    root = os.path.join(PROJECT_ROOT, "data", "merge", issues_folder, source_web)
    base_issues = os.path.join(root, "base")
    custom_issues = os.path.join(root, "custom")
    return (base_issues, custom_issues)

class StreamlitLogger:
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
            # Normalize to one line per entry for professional, readable logs
            if text is None:
                return
            normalized = (str(text) if not isinstance(text, str) else text).rstrip("\n") + "\n"
            self.logs.append(normalized)
    
    def flush(self):
        pass

def save_phase_metadata(metadata, collection_name, db_name="lawgpt_metadata"):
    """Save transformation phase metadata to MongoDB with configurable database and collection names."""
    try:
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        
        db = client[db_name]
        collection = db[collection_name]
        
        # Add timestamp if not present
        if 'created_at' not in metadata:
            metadata['created_at'] = datetime.now().isoformat()
        
        # Insert the metadata
        result = collection.insert_one(metadata)
        return True
    except Exception as e:
        print(f"❌ Error saving metadata: {e}")
        return False

def get_last_metadata(metadata_db_name=None, metadata_collection_name=None):
    try:
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        
        # Require both parameters - no hardcoded fallbacks
        if not metadata_db_name or not metadata_collection_name:
            print("❌ Error: Both metadata_db_name and metadata_collection_name must be provided")
            return None
        
        db = client[metadata_db_name]
        collection = db[metadata_collection_name]
        
        # Get the most recent metadata
        latest = collection.find_one(sort=[('created_at', -1)])
        return latest
    except Exception as e:
        print(f"❌ Error retrieving metadata: {e}")
        return None

def setup_azure_client():
    try:
        api_key = os.getenv("AZURE_OPENAI_API_KEY", DEFAULT_AZURE_OPENAI_API_KEY)
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_OPENAI_API_VERSION)
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", DEFAULT_AZURE_OPENAI_ENDPOINT)

        if not api_key or not api_version or not azure_endpoint:
            raise ValueError("Missing Azure OpenAI credentials")

        client = openai.AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=azure_endpoint
        )
        return client
    except Exception as e:
        st.error(f"❌ Error setting up Azure client: {e}")
        return None

def run_transformation_phase(phase_name, phase_func, input_dir, output_dir, summarise_dir, issue_dir, 
                           deployment_name, client, system_prompt, summarization_prompt, token, source_web, 
                           data_type, country, db_name, logger, stop_event=None, metadata_db_name=None, metadata_collection_name=None, collection_name=None):
    """Run a single transformation phase"""
    start_time = datetime.now()
    
    try:
        logger.write(f"\n🚀 Starting {phase_name} phase for {data_type}...")
        logger.write(f"📁 Input: {input_dir}")
        logger.write(f"📁 Output: {output_dir}")
        
        # Check for stop event before proceeding
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ {phase_name} phase stopped by user")
            return None
        
        # Create directories if they don't exist
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(summarise_dir, exist_ok=True)
        os.makedirs(issue_dir, exist_ok=True)
        
        # Check for stop event again before running transformation
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ {phase_name} phase stopped by user")
            return None
        
        # Run the phase function
        result = phase_func(input_dir, output_dir, summarise_dir, issue_dir, deployment_name, 
                          client, system_prompt, summarization_prompt, token, source_web)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        # Create metadata for this phase
        if result:
            # Support both legacy (raw_count - processed) and new tuple shape
            if len(result) == 5:
                issue_count, processed_count, processed_files, issue_files, raw_count = result
                skipped_existing = None
            else:
                issue_count, processed_count, processed_files, issue_files, raw_count, skipped_existing = result
            
            metadata = {
                "country": country,
                "data_type": data_type,
                "total_raw": raw_count,
                "total": processed_count,  # total for this specific phase
                "issues_count": issue_count,
                "filenames": processed_files,
                "issue_filenames": issue_files,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration.total_seconds(),
                "source": source_web,
                "phase_name": phase_name,
                "database_name": db_name,
                "collection_name": collection_name,
                "metadata_database_name": metadata_db_name,
                "metadata_collection_name": metadata_collection_name
            }
            
            # Save metadata for this phase
            # Persist metadata using shared util
            metadata_success = save_phase_metadata(metadata, metadata_collection_name, metadata_db_name)
            metadata_id = None
            if metadata_success:
                metadata_id = "ok"
            if metadata_id:
                logger.write(f"💾 {phase_name} phase metadata saved with ID: {metadata_id}")
            
            logger.write(f"✅ {phase_name} phase completed\n" )
            logger.write(f"📊 {phase_name} Phase Results:\n")
            logger.write(f"- Raw files: {raw_count}\n")
            logger.write(f"- Processed: {processed_count}\n")
            logger.write(f"- Issues: {issue_count}\n")
            if skipped_existing is not None:
                logger.write(f"- Skipped (existing): {skipped_existing}\n")
            logger.write(f"- Duration: {duration}\n")
            
            # Auto-run issue resolver for Base/Custom phases when issues > 0
            try:
                if issue_count > 0 and phase_name in ["Base", "Custom"]:
                    # Check for stop event before running issue resolver
                    if stop_event and stop_event.is_set():
                        logger.write(f"⏹️ Issue resolver for {phase_name} stopped by user")
                        return result
                    
                    logger.write(f"🛠️ Running issue resolver for {phase_name} (issues: {issue_count})...")
                    if data_type == "cases":
                        if phase_name == "Base":
                            resolved = base_issue_resolver(
                                input_dir, output_dir, summarise_dir, deployment_name, client,
                                system_prompt, summarization_prompt, token, source_web,
                                resolve_issue_dir(data_type, phase_name, source_web)
                            )
                        else:
                            resolved = custom_issue_resolver(
                                input_dir, output_dir, summarise_dir, deployment_name, client,
                                system_prompt, summarization_prompt, token, source_web,
                                resolve_issue_dir(data_type, phase_name, source_web)
                            )
                    else:
                        if phase_name == "Base":
                            resolved = base_statute_issue_resolver(
                                input_dir, output_dir, summarise_dir, deployment_name, client,
                                system_prompt, summarization_prompt, token, source_web
                            )
                        else:
                            resolved = custom_statute_issue_resolver(
                                input_dir, output_dir, summarise_dir, deployment_name, client,
                                system_prompt, summarization_prompt, token, source_web
                            )
                    logger.write(f"- Issue resolver recovered files: {resolved}\n")
            except Exception as e:
                logger.write(f"⚠️ Issue resolver failed: {e}\n")
        
        return result
        
    except Exception as e:
        end_time = datetime.now()
        duration = end_time - start_time
        
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ {phase_name} phase stopped by user")
            # Create stopped metadata
            metadata = {
                "country": country,
                "data_type": data_type,
                "total_raw": 0,
                "total": 0,
                "issues_count": 0,
                "filenames": [],
                "issue_filenames": [],
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration.total_seconds(),
                "source": source_web,
                "phase_name": phase_name,
                "database_name": db_name,
                "collection_name": collection_name,
                "metadata_database_name": metadata_db_name,
                "metadata_collection_name": metadata_collection_name,
                "transformation_status": "stopped"
            }
        else:
            logger.write(f"❌ Error in {phase_name} phase: {e}")
            # Create error metadata
            metadata = {
                "country": country,
                "data_type": data_type,
                "total_raw": 0,
                "total": 0,
                "issues_count": 0,
                "filenames": [],
                "issue_filenames": [],
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration.total_seconds(),
                "source": source_web,
                "phase_name": phase_name,
                "database_name": db_name,
                "collection_name": collection_name,
                "metadata_database_name": metadata_db_name,
                "metadata_collection_name": metadata_collection_name,
                "error_message": str(e)
            }
        
        save_phase_metadata(metadata, metadata_collection_name, metadata_db_name)
        return None


def run_merge_phase(data_type, base_dir, custom_dir, merge_dir, deployment_name, client, system_prompt, token, source_web, db_name, country, logger, stop_event=None, metadata_db_name=None, metadata_collection_name=None, collection_name=None):
    """Run the merge phase (special signature) with proper metadata and issue resolution."""
    start_time = datetime.now()
    try:
        logger.write(f"\n🚀 Starting Merge phase for {data_type}...")
        logger.write(f"📁 Base Dir: {base_dir}")
        logger.write(f"📁 Custom Dir: {custom_dir}")
        logger.write(f"📁 Output (Merge) Dir: {merge_dir}")

        # Check for stop event before proceeding
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ Merge phase stopped by user")
            return None

        os.makedirs(merge_dir, exist_ok=True)

        issues_dir_base, issues_dir_custom = resolve_merge_issue_dirs(data_type, source_web)
        os.makedirs(issues_dir_base, exist_ok=True)
        os.makedirs(issues_dir_custom, exist_ok=True)

        # Check for stop event again before running transformation
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ Merge phase stopped by user")
            return None

        phase_func = merge_json_gpt if data_type == "cases" else merge_statutes_json_gpt
        # Merge functions expect: (base_dir, custom_dir, output_dir, issues_dir_base, issues_dir_custom, system_prompt, client, source_web)
        result = phase_func(base_dir, custom_dir, merge_dir, issues_dir_base, issues_dir_custom, system_prompt, client, source_web)

        end_time = datetime.now()
        duration = end_time - start_time

        if result:
            issue_count, processed_count, processed_files, issue_files, raw_count, skipped_existing = result

            metadata = {
                "country": country,
                "data_type": data_type,
                "total_raw": raw_count,
                "total": processed_count,
                "issues_count": issue_count,
                "filenames": processed_files,
                "issue_filenames": issue_files,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration.total_seconds(),
                "source": source_web,
                "phase_name": "Merge",
                "database_name": db_name,
                "collection_name": collection_name,
                "metadata_database_name": metadata_db_name,
                "metadata_collection_name": metadata_collection_name
            }

            save_phase_metadata(metadata, metadata_collection_name, metadata_db_name)

            logger.write(f"✅ Merge phase completed\n")
            logger.write(f"📊 Merge Phase Results:\n")
            logger.write(f"- Raw files: {raw_count}\n")
            logger.write(f"- Processed: {processed_count}\n")
            logger.write(f"- Issues: {issue_count}\n")
            logger.write(f"- Skipped (existing): {skipped_existing}\n")
            logger.write(f"- Duration: {duration}\n")

            # After saving merged JSONs and metadata, ingest into final_data DB
            try:
                ingest_merged_json_to_final_db(data_type, source_web, merge_dir, db_name, country, logger, collection_name)
            except Exception as ingest_err:
                logger.write(f"⚠️ Final DB ingest failed: {ingest_err}\n")

            # Auto-run merge issue resolver if needed
            try:
                if issue_count > 0:
                    # Check for stop event before running issue resolver
                    if stop_event and stop_event.is_set():
                        logger.write(f"⏹️ Merge issue resolver stopped by user")
                        return result
                    
                    logger.write("🛠️ Running issue resolver for Merge phase...")
                    if data_type == "cases":
                        resolved = merge_issue_resolver(base_dir, custom_dir, merge_dir, MERGE_PROMPT_CASES, client, source_web)
                    else:
                        resolved = merge_statutes_issue_resolver(base_dir, custom_dir, merge_dir, MERGE_PROMPT_STATUTES, client, source_web)
                    logger.write(f"- Merge issue resolver recovered files: {resolved}\n")
            except Exception as e:
                logger.write(f"⚠️ Merge issue resolver failed: {e}\n")

        return result
    except Exception as e:
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ Merge phase stopped by user")
            end_time = datetime.now()
            duration = end_time - start_time
            metadata = {
                "country": country,
                "data_type": data_type,
                "total_raw": 0,
                "total": 0,
                "issues_count": 0,
                "filenames": [],
                "issue_filenames": [],
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration.total_seconds(),
                "source": source_web,
                "phase_name": "Merge",
                "database_name": db_name,
                "collection_name": collection_name,
                 "transformation_status": "stopped"
            }
        else:
            logger.write(f"❌ Error in Merge phase: {e}")
            end_time = datetime.now()
            duration = end_time - start_time
            metadata = {
                "country": country,
                "data_type": data_type,
                "total_raw": 0,
                "total": 0,
                "issues_count": 0,
                "filenames": [],
                "issue_filenames": [],
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration.total_seconds(),
                "source": source_web,
                "phase_name": "Merge",
                "database_name": db_name,
                "collection_name": collection_name,
                "metadata_database_name": metadata_db_name,
                "metadata_collection_name": metadata_collection_name,
                "error_message": str(e),
            }
        save_phase_metadata(metadata, metadata_collection_name, metadata_db_name)
        return None

def ingest_merged_json_to_final_db(data_type, source_web, merge_dir, db_name, country, logger, collection_name=None):
    """Load merged JSON files into MongoDB database with user-specified collection names.
    Uses filename as upsert key to avoid duplicates.
    """
    # Use provided collection name or generate fallback
    if collection_name:
        coll_name = collection_name
        logger.write(f"📊 Using provided collection name: {coll_name}")
    else:
        # Fallback to generated collection name from directory path and country
        path_parts = merge_dir.replace("\\", "/").split("/")
        if len(path_parts) >= 2:
            pipeline_type = path_parts[-2]  # cases or statutes
            source_web_clean = path_parts[-1]  # source web name
            # Create collection name: country_source_web_pipeline_type
            coll_name = f"{country.lower()}_{source_web_clean}_{pipeline_type}"
        else:
            # Fallback to simple naming if path parsing fails
            coll_name = f"{country.lower()}_{source_web}_{data_type}"
        logger.write(f"📊 Using generated collection name: {coll_name}")
    
    logger.write(f"📊 Target collection: {coll_name}")
    
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    db = client[db_name]
    collection = db[coll_name]

    inserted = 0
    updated = 0
    total_files = 0
    for fname in os.listdir(merge_dir):
        if not fname.lower().endswith(".json"):
            continue
        total_files += 1
        fpath = os.path.join(merge_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                doc = json.load(f)
            # Attach metadata fields to help queries
            doc["filename"] = fname
            doc["source_web"] = source_web
            doc["data_type"] = data_type
            # Upsert by filename
            res = collection.update_one({"filename": fname}, {"$set": doc}, upsert=True)
            if res.upserted_id is not None:
                inserted += 1
            elif res.modified_count > 0:
                updated += 1
        except Exception as e:
            logger.write(f"⚠️ Failed to ingest {fname}: {e}\n")

    logger.write(f"💾 Final DB ingest complete → DB: final_data, Coll: {coll_name}, Files: {total_files}, Inserted: {inserted}, Updated: {updated}\n")

def run_complete_transformation(data_type, source_web, input_dir, base_dir, custom_dir, merge_dir, 
                              summarise_dir, issue_dir_unused, deployment_name, client, token_unused, db_name, country, logger, stop_event=None, metadata_db_name=None, metadata_collection_name=None, collection_name=None):
    """Run all three phases in sequence"""
    start_time = datetime.now()
    total_processed = 0
    total_issues = 0
    all_processed_files = []
    all_issue_files = []
    
    try:
        # Phase 1: Base
        logger.write(f"\n{'='*50}")
        logger.write(f"📋 PHASE 1: BASE TRANSFORMATION")
        logger.write(f"{'='*50}")
        
        # Resolve per-phase dynamic token & issues_dir (hardcoded)
        base_token = resolve_max_tokens(data_type, "Base")
        base_issue_dir = resolve_issue_dir(data_type, "Base", source_web)

        base_result = run_transformation_phase(
            "Base", 
            base_json_gpt if data_type == "cases" else base_statute_json_gpt,
            input_dir, base_dir, summarise_dir, base_issue_dir, deployment_name, client,
            BASE_PROMPT_CASES if data_type == "cases" else BASE_PROMPT_STATUTES,
            SUMMARIZATION_PROMPT_CASES if data_type == "cases" else SUMMARIZATION_PROMPT_STATUTES,
            base_token, source_web, data_type, country, db_name, logger, stop_event, metadata_db_name, metadata_collection_name, collection_name
        )
        
        if base_result:
            issue_count, processed_count, processed_files, issue_files, raw_count, skipped = base_result
            total_processed += processed_count
            total_issues += issue_count
            all_processed_files.extend(processed_files)
            all_issue_files.extend(issue_files)
            
            logger.write(f"📊 Base Phase Results:")
            logger.write(f"   Processed: {processed_count}")
            logger.write(f"   Issues: {issue_count}")
            logger.write(f"   Skipped: {skipped}")
        else:
            # Base phase was stopped or failed
            logger.write(f"⏹️ Base phase stopped or failed")
            return None
        
        # Check for stop event between phases
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ Transformation stopped by user after Base phase")
            return None
        
        # Phase 2: Custom
        logger.write(f"\n{'='*50}")
        logger.write(f"📋 PHASE 2: CUSTOM TRANSFORMATION")
        logger.write(f"{'='*50}")
        
        custom_token = resolve_max_tokens(data_type, "Custom")
        custom_issue_dir = resolve_issue_dir(data_type, "Custom", source_web)

        custom_result = run_transformation_phase(
            "Custom",
            custom_json_gpt if data_type == "cases" else custom_statutes_json_gpt,
            input_dir, custom_dir, summarise_dir, custom_issue_dir, deployment_name, client,
            CUSTOM_PROMPT_CASES if data_type == "cases" else CUSTOM_PROMPT_STATUTES,
            SUMMARIZATION_PROMPT_CASES if data_type == "cases" else SUMMARIZATION_PROMPT_STATUTES,
            custom_token, source_web, data_type, country, db_name, logger, stop_event, metadata_db_name, metadata_collection_name, collection_name
        )
        
        if custom_result:
            issue_count, processed_count, processed_files, issue_files, raw_count, skipped = custom_result
            total_processed += processed_count
            total_issues += issue_count
            all_processed_files.extend(processed_files)
            all_issue_files.extend(issue_files)
            
            logger.write(f"📊 Custom Phase Results:")
            logger.write(f"   Processed: {processed_count}")
            logger.write(f"   Issues: {issue_count}")
            logger.write(f"   Skipped: {skipped}")
        else:
            # Custom phase was stopped or failed
            logger.write(f"⏹️ Custom phase stopped or failed")
            return None
        
        # Check for stop event between phases
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ Transformation stopped by user after Custom phase")
            return None
        
        # Phase 3: Merge
        logger.write(f"\n{'='*50}")
        logger.write(f"📋 PHASE 3: MERGE TRANSFORMATION")
        logger.write(f"{'='*50}")
        
        merge_token = resolve_max_tokens(data_type, "Merge")
        # For merge, the worker function takes a single issues_dir but the resolver needs two; we set phase issues_dir anyway.
        merge_issue_dir = resolve_issue_dir(data_type, "Merge", source_web)

        merge_result = run_merge_phase(
            data_type,
            base_dir,
            custom_dir,
            merge_dir,
            deployment_name,
            client,
            MERGE_PROMPT_CASES if data_type == "cases" else MERGE_PROMPT_STATUTES,
            merge_token,
            source_web,
            db_name,
            country,
            logger,
            stop_event,
            metadata_db_name,
            metadata_collection_name,
            collection_name
        )
        
        if merge_result:
            issue_count, processed_count, processed_files, issue_files, raw_count, skipped = merge_result
            total_processed += processed_count
            total_issues += issue_count
            all_processed_files.extend(processed_files)
            all_issue_files.extend(issue_files)
        else:
            # Merge phase was stopped or failed
            logger.write(f"⏹️ Merge phase stopped or failed")
            return None

        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logger.write(f"\n{'='*50}")
        logger.write(f"🎉 TRANSFORMATION COMPLETED")
        logger.write(f"{'='*50}")
        logger.write(f"📊 Total Processed: {total_processed}")
        logger.write(f"❌ Total Issues: {total_issues}")
        logger.write(f"⏱️ Duration: {duration}")
        logger.write(f"✅ All phases completed successfully!")
        
        # Create summary metadata for UI display (individual phase metadata already saved)
        metadata = {
            "country": country,
            "data_type": data_type,
            "source_web": source_web,
            "input_directory": input_dir,
            "base_directory": base_dir,
            "custom_directory": custom_dir,
            "merge_directory": merge_dir,
            "database_name": db_name,
            "collection_name": collection_name,
            "metadata_database_name": metadata_db_name,
            "metadata_collection_name": metadata_collection_name,
            "total_processed": total_processed,
            "total_issues": total_issues,
            "processed_files": all_processed_files,
            "issue_files": all_issue_files,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration.total_seconds(),
            "transformation_status": "completed"
        }
        
        return metadata
        
    except Exception as e:
        if stop_event and stop_event.is_set():
            logger.write(f"⏹️ Complete transformation stopped by user")
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Create stopped metadata for UI display
            metadata = {
                "country": country,
                "database_name": db_name,
                "data_type": data_type,
                "source_web": source_web,
                "input_directory": input_dir,
                "base_directory": base_dir,
                "custom_directory": custom_dir,
                "merge_directory": merge_dir,
                "collection_name": collection_name,
                "metadata_database_name": metadata_db_name,
                "metadata_collection_name": metadata_collection_name,
                "total_processed": total_processed,
                "total_issues": total_issues,
                "processed_files": all_processed_files,
                "issue_files": all_issue_files,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration.total_seconds(),
                "transformation_status": "stopped"
            }
        else:
            logger.write(f"❌ Error in complete transformation: {e}")
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Create error metadata for UI display
            metadata = {
                "country": country,
                "database_name": db_name,
                "data_type": data_type,
                "source_web": source_web,
                "input_directory": input_dir,
                "base_directory": base_dir,
                "custom_directory": custom_dir,
                "merge_directory": merge_dir,
                "collection_name": collection_name,
                "metadata_database_name": metadata_db_name,
                "metadata_collection_name": metadata_collection_name,
                "total_processed": total_processed,
                "total_issues": total_issues,
                "processed_files": all_processed_files,
                "issue_files": all_issue_files,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration.total_seconds(),
                "transformation_status": "error",
                "error_message": str(e)
            }
        
        return metadata

def main():
    st.set_page_config(
        page_title="Legal Data Transformation Pipeline",
        page_icon="⚖️",
        layout="wide"
    )
    
    st.title("Legal Data Pipeline")
    st.markdown("### Legal Data Transformation")
    st.markdown("Transform legal text files into structured JSON format")
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
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
    
    # Initialize session state
    if 'transformation_status' not in st.session_state:
        st.session_state.transformation_status = "idle"
    if 'transformation_thread' not in st.session_state:
        st.session_state.transformation_thread = None
    if 'stop_event' not in st.session_state:
        st.session_state.stop_event = threading.Event()
    if 'logs' not in st.session_state:
        st.session_state.logs = []
    if 'last_metadata' not in st.session_state:
        st.session_state.last_metadata = None
    if 'show_full_metadata' not in st.session_state:
        st.session_state.show_full_metadata = False
    if 'log_scroll_position' not in st.session_state:
        st.session_state.log_scroll_position = 0

    
    # Setup Azure client
    client = setup_azure_client()
    if not client:
        st.error("❌ Failed to setup Azure client. Please check your environment variables.")
        return
    
    # UI Configuration
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Disable inputs only while actively running/processing
        is_processing = st.session_state.transformation_status in ["running", "processing"]
        
        # Country selection (at the top)
        country = st.selectbox(
            "🌍 Country",
            ["PAK", "UAE", "KSA"],
            help="Select the country for legal data transformation",
            disabled=is_processing
        )
        
        # Data type selection (country-specific)
        if country == "PAK":
            data_type_options = ["cases", "statutes"]
            data_type_help = "Select whether to transform cases or statutes"
        else:  # UAE and KSA
            data_type_options = ["cases", "laws"]
            data_type_help = "Select whether to transform cases or laws"
        
        data_type = st.selectbox(
            "📋 Data Type",
            data_type_options,
            help=data_type_help,
            disabled=is_processing
        )
        
        # Source web selection (country and data type specific)
        source_web_options = []
        source_web_help = ""
        
        if country == "PAK":
            if data_type == "cases":
                source_web_options = ["easylaw", "eastlaw"]
                source_web_help = "Select the source website for cases"
            else:  # statutes
                source_web_options = ["eastlaw"]
                source_web_help = "Statutes are only available from EastLaw"
        elif country == "UAE":
            if data_type == "cases":
                source_web_options = ["moj cases", "adjd", "difc"]
                source_web_help = "Select the source for UAE cases"
            else:  # laws
                source_web_options = ["moj laws", "uae constitution", "uae legislation"]
                source_web_help = "Select the source for UAE laws"
        else:  # KSA
            if data_type == "cases":
                source_web_options = ["moj cases ksa"]
                source_web_help = "Cases are only available from MOJ Cases KSA"
            else:  # laws
                source_web_options = ["moj laws ksa", "personal status law", "anti cyber crime law", "saudilegal"]
                source_web_help = "Select the source for KSA laws"
        
        source_web = st.selectbox(
            "🌐 Source Web",
            source_web_options,
            help=source_web_help,
            disabled=is_processing
        )
        
        # Show info for single source options
        if len(source_web_options) == 1:
            if country == "PAK" and data_type == "statutes":
                st.info("📚 Statutes are only available from EastLaw")
            elif country == "KSA" and data_type == "cases":
                st.info("📚 Cases are only available from MOJ Cases KSA")
        
        # Phase selection
        phase_option = st.radio(
            "Select transformation option:",
            ["Run All Phases", "Phase 1: Base", "Phase 2: Custom", "Phase 3: Merge"],
            help="Choose to run all phases or a specific phase",
            disabled=is_processing
        )
        
        # Collection name configuration (defined before columns for scope access)
        st.subheader("📊 Collection Names")
        collection_name = st.text_input(
            "Final Data Collection Name",
            value="",
            help="Name of the MongoDB collection to store final transformed data",
            placeholder="e.g., uae_moj_cases_merge",
            disabled=is_processing
        )
        
        st.subheader("🔧 Configuration")
        
        # Database configuration
        st.subheader("🗄️ Database Configuration")
        db_name = st.text_input(
            "Final Data Database Name",
            value="final_data",
            help="Name of the MongoDB database to store transformed data",
            disabled=is_processing
        )
        
        metadata_db_name = st.text_input(
            "Metadata Database Name",
            value="lawgpt_metadata",
            help="Name of the MongoDB database to store transformation metadata",
            disabled=is_processing
        )
        
        metadata_collection_name = st.text_input(
            "Metadata Collection Name",
            value="transformation_metadata",
            help="Name of the MongoDB collection to store transformation metadata",
            disabled=is_processing
        )
        
        # Determine the correct data type for pipeline routing
        pipeline_data_type = "cases" if data_type == "cases" else "statutes"
        
        # Directory configuration
        st.subheader("📁 Directory Configuration")
        
        input_dir = st.text_input(
            "Input Directory",
            value=f"D:\\LawGPT_data_pipeline\\data\\raw\\{source_web}\\{'cases' if data_type == 'cases' else 'statutes'}\\text_{data_type}" if source_web == "eastlaw" else f"D:\\LawGPT_data_pipeline\\data\\raw\\{source_web}\\text_{source_web}",
            help="Directory containing .txt files to transform",
            disabled=is_processing
        )
        
        base_dir = st.text_input(
            "Base Output Directory",
            value=f"D:\\LawGPT_data_pipeline\\data\\base\\{pipeline_data_type}\\{source_web}",
            help="Directory for base phase output",
            disabled=is_processing
        )
        
        custom_dir = st.text_input(
            "Custom Output Directory",
            value=f"D:\\LawGPT_data_pipeline\\data\\custom\\{pipeline_data_type}\\{source_web}",
            help="Directory for custom phase output",
            disabled=is_processing
        )
        
        merge_dir = st.text_input(
            "Merge Output Directory",
            value=f"D:\\LawGPT_data_pipeline\\data\\merge\\{pipeline_data_type}\\{source_web}",
            help="Directory for merge phase output",
            disabled=is_processing
        )
        
        summarise_dir = st.text_input(
            "Summarization Directory",
            value=f"D:\\LawGPT_data_pipeline\\data\\summarise\\{pipeline_data_type}\\{source_web}",
            help="Directory for summarized text files",
            disabled=is_processing
        )
        
        # Issues directory is optional operationally; per rules we hardcode it in code, not via UI.
        # Kept out of the UI to reduce config surface and avoid misuse.
        
        # Azure configuration
        st.subheader("🔑 Azure Configuration")
        # Deployment name is stable; keep dynamic via env default but not editable via UI.
        deployment_name = DEFAULT_DEPLOYMENT_NAME
        st.text(f"Deployment: {deployment_name}")
        # Token/max_tokens handling must be dynamic via env/config only, never via UI per rules.
    
    with col2:
        st.subheader("🎮 Controls")
        
        # Start button: enabled unless actively running/processing
        start_disabled = st.session_state.transformation_status in ["running", "processing"]
        if st.button("Start Transformation", use_container_width=True, disabled=start_disabled):
            print(f"🚀 Start button clicked! Status: {st.session_state.transformation_status}")
            print(f"📋 Phase option: {phase_option}")
            print(f"📁 Input dir: {input_dir}")
            
            if not input_dir or not os.path.exists(input_dir):
                st.error("❌ Input directory does not exist!")
                return
            
            if not collection_name:
                st.error("❌ Collection name is required!")
                return
            
            print("✅ Input directory exists, starting transformation...")
            
            # Reset stop event for new transformation
            st.session_state.stop_event.clear()
            st.session_state.transformation_status = "running"
            
            # Do NOT clear previous logs automatically; keep them until user clicks Clear Logs
            # Add a visible session header for separation
            if 'logs' not in st.session_state:
                st.session_state.logs = []
            start_marker = f"\n===== New Transformation Session @ {datetime.now().isoformat()} =====\n"
            st.session_state.logs.append(start_marker)
            
            # Initialize a shared logger instance BEFORE starting the thread so UI can poll it
            shared_logger = StreamlitLogger()
            shared_logger.start_capture()
            st.session_state.logger = shared_logger
            
            # Start transformation in a separate thread
            def run_transformation(logger, stop_event):
                # Route all print output to the UI logger so phase-level prints appear in the app
                stdout_backup, stderr_backup = sys.stdout, sys.stderr
                sys.stdout, sys.stderr = logger, logger
                
                try:
                    print(f"🔄 Starting transformation with phase_option: {phase_option}")
                    
                    # Check for stop event before starting
                    if stop_event.is_set():
                        print("⏹️ Transformation stopped before starting")
                        st.session_state.transformation_status = "stopped"
                        return
                    
                    if phase_option == "Run All Phases":
                        print("🚀 Running complete transformation...")
                        # Resolve optional issue directories in code (hardcoded) per rules
                        # Base/custom phases use a single issues_dir; merge uses two separate issue dirs internally.
                        metadata = run_complete_transformation(
                            data_type, source_web, input_dir, base_dir, custom_dir, merge_dir,
                            summarise_dir, None, deployment_name, client, None, db_name, country, logger, stop_event, metadata_db_name, metadata_collection_name, collection_name
                        )
                    else:
                        # Run individual phase
                        # For merge phases, we need to create wrapper functions since they have different signatures
                        def merge_wrapper_cases(input_dir, output_dir, summarise_dir, issue_dir, deployment_name, client, system_prompt, summarization_prompt, token, source_web):
                            # Merge functions expect: (base_dir, custom_dir, output_dir, issues_dir_base, issues_dir_custom, system_prompt, client, source_web)
                            base_dir = os.path.join(PROJECT_ROOT, "data", "base", data_type, source_web)
                            custom_dir = os.path.join(PROJECT_ROOT, "data", "custom", data_type, source_web)
                            issues_dir_base, issues_dir_custom = resolve_merge_issue_dirs(data_type, source_web)
                            # Create directories for merge phase
                            os.makedirs(output_dir, exist_ok=True)
                            os.makedirs(issues_dir_base, exist_ok=True)
                            os.makedirs(issues_dir_custom, exist_ok=True)
                            return merge_json_gpt(base_dir, custom_dir, output_dir, issues_dir_base, issues_dir_custom, system_prompt, client, source_web)
                        
                        def merge_wrapper_statutes(input_dir, output_dir, summarise_dir, issue_dir, deployment_name, client, system_prompt, summarization_prompt, token, source_web):
                            # Merge functions expect: (base_dir, custom_dir, output_dir, issues_dir_base, issues_dir_custom, system_prompt, client, source_web)
                            base_dir = os.path.join(PROJECT_ROOT, "data", "base", data_type, source_web)
                            custom_dir = os.path.join(PROJECT_ROOT, "data", "custom", data_type, source_web)
                            issues_dir_base, issues_dir_custom = resolve_merge_issue_dirs(data_type, source_web)
                            # Create directories for merge phase
                            os.makedirs(output_dir, exist_ok=True)
                            os.makedirs(issues_dir_base, exist_ok=True)
                            os.makedirs(issues_dir_custom, exist_ok=True)
                            return merge_statutes_json_gpt(base_dir, custom_dir, output_dir, issues_dir_base, issues_dir_custom, system_prompt, client, source_web)
                        
                        phase_map = {
                            "Phase 1: Base": (base_json_gpt if data_type == "cases" else base_statute_json_gpt,
                                             BASE_PROMPT_CASES if data_type == "cases" else BASE_PROMPT_STATUTES),
                            "Phase 2: Custom": (custom_json_gpt if data_type == "cases" else custom_statutes_json_gpt,
                                               CUSTOM_PROMPT_CASES if data_type == "cases" else CUSTOM_PROMPT_STATUTES),
                            "Phase 3: Merge": (merge_wrapper_cases if data_type == "cases" else merge_wrapper_statutes,
                                              MERGE_PROMPT_CASES if data_type == "cases" else MERGE_PROMPT_STATUTES)
                        }
                        
                        phase_func, system_prompt = phase_map[phase_option]
                        summarization_prompt = SUMMARIZATION_PROMPT_CASES if data_type == "cases" else SUMMARIZATION_PROMPT_STATUTES
                        
                        # Determine output directory based on phase
                        output_dir = base_dir if "Base" in phase_option else custom_dir if "Custom" in phase_option else merge_dir
                        # Hardcode issue_dir per rules
                        issue_dir = resolve_issue_dir(data_type, phase_option.split(": ")[1], source_web)
                        # Resolve dynamic token (max_tokens) from env/config
                        token = resolve_max_tokens(data_type, phase_option.split(": ")[1])
                        
                        result = run_transformation_phase(
                            phase_option.split(": ")[1],
                            phase_func,
                            input_dir, output_dir, summarise_dir, issue_dir, deployment_name, client,
                            system_prompt, summarization_prompt, token, source_web, data_type, country, db_name, logger, stop_event, metadata_db_name, metadata_collection_name, collection_name
                        )
                        
                        if result:
                            # Metadata is already saved in run_transformation_phase
                            # Just create a summary for UI display
                            metadata = {
                                "country": country,
                                "data_type": data_type,
                                "source_web": source_web,
                                "phase": phase_option,
                                "input_directory": input_dir,
                                "output_directory": output_dir,
                                "database_name": db_name,
                                "collection_name": collection_name,
                                "metadata_database_name": metadata_db_name,
                                "metadata_collection_name": metadata_collection_name,
                                "total_processed": result[1] if result else 0,
                                "total_issues": result[0] if result else 0,
                                "processed_files": result[2] if result else [],
                                "issue_files": result[3] if result else [],
                                "transformation_status": "completed"
                            }
                            
                            # Auto-ingest merged JSONs to final DB if this was a merge phase
                            if "Merge" in phase_option:
                                # Check for stop event before DB ingest
                                if stop_event.is_set():
                                    logger.write("⏹️ DB ingest skipped due to stop event")
                                else:
                                    try:
                                        ingest_merged_json_to_final_db(data_type, source_web, output_dir, db_name, country, logger, collection_name)
                                    except Exception as ingest_err:
                                        logger.write(f"⚠️ Final DB ingest failed: {ingest_err}\n")
                        else:
                            # Check if stopped or failed
                            if stop_event.is_set():
                                metadata = {
                                    "country": country,
                                    "data_type": data_type,
                                    "source_web": source_web,
                                    "phase": phase_option,
                                    "input_directory": input_dir,
                                    "output_directory": output_dir,
                                    "database_name": db_name,
                                    "collection_name": collection_name,
                                    "metadata_database_name": metadata_db_name,
                                    "metadata_collection_name": metadata_collection_name,
                                    "transformation_status": "stopped"
                                }
                            else:
                                metadata = {
                                    "country": country,
                                    "data_type": data_type,
                                    "source_web": source_web,
                                    "phase": phase_option,
                                    "input_directory": input_dir,
                                    "output_directory": output_dir,
                                    "database_name": db_name,
                                    "collection_name": collection_name,
                                    "metadata_database_name": metadata_db_name,
                                    "metadata_collection_name": metadata_collection_name,
                                    "transformation_status": "error"
                                }
                    
                    # Check for stop event before updating session state
                    if stop_event.is_set():
                        st.session_state.transformation_status = "stopped"
                        logger.write(f"⏹️ {phase_option} stopped by user")
                    else:
                        # Update session state
                        st.session_state.last_metadata = metadata
                        # Set completed status
                        st.session_state.transformation_status = "completed"
                        logger.write(f"✅ {phase_option} completed successfully!")
                    
                except Exception as e:
                    if stop_event.is_set():
                        logger.write(f"⏹️ Transformation stopped by user during execution")
                        st.session_state.transformation_status = "stopped"
                    else:
                        logger.write(f"❌ Transformation error: {e}")
                        st.session_state.transformation_status = "error"
                finally:
                    # Restore original stdout/stderr no matter what
                    sys.stdout, sys.stderr = stdout_backup, stderr_backup
                    logger.stop_capture()
                    # Persist logs snapshot for post-run viewing
                    st.session_state.logs = logger.logs
                    # Ensure UI leaves running state so controls re-enable
                    if st.session_state.get("transformation_status") in ["running", "processing"]:
                        if stop_event.is_set():
                            st.session_state.transformation_status = "stopped"
                        else:
                            st.session_state.transformation_status = "completed"
                
                # Check for stop event before final sleep
                if not stop_event.is_set():
                    # Do not call st.rerun() from background thread; the main app loop auto-refreshes
                    time.sleep(0.5)  # Ensure logs are captured
            
            print("🧵 Creating transformation thread...")
            # Create a local reference to the stop event to avoid session state access issues in background thread
            local_stop_event = st.session_state.stop_event
            st.session_state.transformation_thread = threading.Thread(target=run_transformation, args=(shared_logger, local_stop_event))
            st.session_state.transformation_thread.daemon = True  # Make thread daemon so it stops when main thread ends
            st.session_state.transformation_thread.start()
            print("✅ Thread started successfully!")
        
        # Stop button: only enabled while actively running/processing
        if st.button("Stop Transformation", use_container_width=True,
                    disabled=st.session_state.transformation_status not in ["running", "processing"]):
            # Set the stop event to signal all threads to stop
            st.session_state.stop_event.set()
            st.session_state.transformation_status = "stopping"
            
            # Wait a moment for threads to respond to stop event
            time.sleep(0.5)
            
            # Force terminate the thread if it's still running
            if st.session_state.transformation_thread and st.session_state.transformation_thread.is_alive():
                try:
                    # Note: In Python, we can't forcefully kill threads, but we can mark them as daemon
                    # and let them finish naturally when the main thread ends
                    st.session_state.transformation_thread.join(timeout=2.0)
                    if st.session_state.transformation_thread.is_alive():
                        print("⚠️ Thread termination timeout - thread will finish naturally")
                except Exception as e:
                    print(f"⚠️ Error stopping thread: {e}")
            
            st.session_state.transformation_status = "stopped"
            st.rerun()
        
        # Clear logs button
        if st.button("Clear Logs", use_container_width=True):
            st.session_state.logs = []
            st.session_state.last_metadata = None
            st.session_state.show_full_metadata = False
            st.rerun()
        

    
    # Progress and status
    if 'transformation_status' in st.session_state:
        status = st.session_state.transformation_status
        
        status_messages = {
            "running": {
                "message": "🔄 Transformation in progress...",
                "class": "info-box"
            },
            "processing": {
                "message": "⚙️ Processing data...",
                "class": "info-box"
            },
            "stopping": {
                "message": "⏹️ Stopping transformation...",
                "class": "warning-box"
            },
            "stopped": {
                "message": "⏹️ Transformation stopped by user.",
                "class": "info-box"
            },
            "completed": {
                "message": "✅ Transformation completed successfully! Check the metadata below for details.",
                "class": "success-box"
            },
            "error": {
                "message": "❌ Error occurred during transformation. Check logs for details.",
                "class": "error-box"
            },
            "idle": {
                "message": "⏸️ Ready to start transformation. Configure settings and click Start.",
                "class": "info-box"
            }
        }
        
        # Get status message and class
        status_info = status_messages.get(status, {
            "message": f"⚠️ Unknown status: {status}",
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
    log_text = ""
    if st.session_state.get('transformation_status') in ["running", "processing"] and st.session_state.get('logger'):
        # Live logs during run from shared logger instance
        log_text = "".join(st.session_state.logger.logs)
    elif st.session_state.get('logs'):
        log_text = "".join(st.session_state.logs)
    
    if log_text:
        log_placeholder.code(log_text, language="text")
    
    # Metadata display
    if st.session_state.last_metadata:
        st.subheader("Last Session Metadata")
        
        metadata = st.session_state.last_metadata
        
        # Display key metrics
        col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns(9)
        with col1:
            st.metric("Country", metadata.get('country', 'N/A'))
        with col2:
            st.metric("Data Type", metadata.get('data_type', 'N/A'))
        with col3:
            st.metric("Source Web", metadata.get('source_web', 'N/A'))
        with col4:
            if 'phase_name' in metadata:
                st.metric("Phase", metadata.get('phase_name', 'N/A'))
            else:
                st.metric("Total Processed", metadata.get('total_processed', 0))
        with col5:
            if 'total' in metadata:
                st.metric("Processed", metadata.get('total', 0))
            else:
                st.metric("Total Issues", metadata.get('total_issues', 0))
        with col6:
            st.metric("Final DB", metadata.get('database_name', 'N/A'))
        with col7:
            st.metric("Collection", metadata.get('collection_name', 'N/A'))
        with col8:
            st.metric("Metadata DB", metadata.get('metadata_database_name', 'N/A'))
        with col9:
            st.metric("Metadata Coll", metadata.get('metadata_collection_name', 'N/A'))
        
        # Show full metadata button
        if st.button("📋 View Full Metadata"):
            st.session_state.show_full_metadata = not st.session_state.show_full_metadata
        
        if st.session_state.show_full_metadata:
            st.json(metadata)
    
    # Auto-refresh for running transformations
    if st.session_state.transformation_status in ["running", "processing"]:
        # Periodically refresh to stream logs while background thread prints
        time.sleep(1.0)
        st.rerun()
    elif st.session_state.transformation_status == "stopped":
        # Force refresh when stopped to update UI immediately
        st.rerun()

if __name__ == "__main__":
    main() 