import os
import json
import tiktoken
from dotenv import load_dotenv
import re
import json5
from datetime import datetime
from pymongo import MongoClient

# Centralized DB name for all pipeline metadata
# Keep this hardcoded for operational consistency across apps.
# If needed, future devs can move this to env var without touching call sites.
DB_NAME = "lawgpt_metadata"

load_dotenv()

# === Token helper ===
def count_tokens(text, model="gpt-4-1106-preview"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))

# === Chunking for summarization ===
def split_text_into_token_chunks(text, max_tokens_per_chunk=120000):
    enc = tiktoken.encoding_for_model("gpt-4o")
    tokens = enc.encode(text)
    for i in range(0, len(tokens), max_tokens_per_chunk):
        yield enc.decode(tokens[i:i + max_tokens_per_chunk])

# === Summarize large input ===
def summarize_text_if_needed(text, filename, summarized_dir, deployment_name, summarization_prompt, client):
    max_input_tokens = 70000
    token_count = count_tokens(text)

    if token_count <= max_input_tokens:
        return text

    print(f"🧹 Text too long ({token_count} tokens). Summarizing...")

    summarized_chunks = []
    for chunk in split_text_into_token_chunks(text, 90000):
        try:
            response = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": summarization_prompt},
                    {"role": "user", "content": chunk}
                ],
                temperature=0.3,
                max_tokens=8192
            )
            summarized_chunks.append(response.choices[0].message.content.strip())
        except Exception as e:
            print(f"❌ Chunk summarization failed: {e}")
            return text  # fallback

    summary = "\n\n".join(summarized_chunks)
    with open(os.path.join(summarized_dir, filename), "w", encoding="utf-8") as f:
        f.write(summary)
    return summary

# === GPT call ===
def call_gpt_with_schema(schema, text, system_prompt, deployment_name, client, token):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Base Schema:\n{schema}\n\nCase Text:\n{text}"}
    ]
    response = client.chat.completions.create(
        model=deployment_name,
        messages=messages,
        temperature=0.2,
        max_tokens=token
    )
    return response.choices[0].message.content.strip()

def call_gpt_for_file(case_text, client, system_prompt, token):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": case_text}
        ],
        temperature=0.2,
        max_tokens=token,
    )
    return response.choices[0].message.content.strip()

# === JSON parse helper ===
def try_parse_json(text, filename):
    try:
        parsed = json.loads(text)
        return parsed
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}")
        print(f"🔎 Raw GPT response from {filename}:\n{text}")
        return None

def extract_and_fix_json(raw_text, file_name, output_path=None):
    clean_text = raw_text.strip()
    clean_text = re.sub(r"^```json\s*|\s*```$", "", clean_text, flags=re.DOTALL).strip()

    try:
        parsed_json = json.loads(clean_text)
        print("✅ Parsed successfully with standard JSON.")
    except json.JSONDecodeError as e:
        print(f"⚠️ Standard JSON failed: {e}")
        try:
            parsed_json = json5.loads(clean_text)
            print("✅ Parsed successfully using json5.")
        except Exception as ex:
            print(f"❌ json5 also failed: {ex}")
            print(f"\n🔎 Failed file: {file_name}")
            print("🔎 Full raw GPT response:\n")
            print(raw_text)
            return None

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(parsed_json, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved to: {output_path}")

    return parsed_json

# === File existence check ===
def check_file_exists(output_path):
    """Check if output file already exists"""
    return os.path.exists(output_path)

# === Load schema ===
def load_schema(schema_path):
    """Load schema from JSON file"""
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"❌ Error loading schema from {schema_path}: {e}")
        return None

# === Save metadata ===
def save_metadata(metadata_dict, collection_name):
    """Save metadata to MongoDB"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        # Use unified database for all pipeline metadata (extraction + transformation)
        db = client[DB_NAME]
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