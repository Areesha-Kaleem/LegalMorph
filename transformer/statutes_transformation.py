import json
import time
import tiktoken
from dotenv import load_dotenv
import re
import json5
from pymongo import MongoClient
from difflib import get_close_matches

load_dotenv()

def count_tokens(text, model="gpt-4-1106-preview"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


# === Chunking for summarization ===
def split_text_into_token_chunks(text, max_tokens_per_chunk=120000):
    enc = tiktoken.encoding_for_model("gpt-4o")
    tokens = enc.encode(text)
    for i in range(0, len(tokens), max_tokens_per_chunk):
        yield enc.decode(tokens[i:i + max_tokens_per_chunk])

def insert_text_to_mongodb(text, title, mongo_uri, db_name, collection_name):
    """
    Inserts a document with 'title' and 'content' into the specified MongoDB collection.
    """
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        document = {
            "title": title,
            "content": text
        }

        result = collection.insert_one(document)
        print(f"✅ Document inserted with _id: {result.inserted_id}")
        return str(result.inserted_id)

    except Exception as e:
        print(f"❌ Failed to insert document: {e}")
        return None

def fetch_statute_data(mongo_uri, db_name, collection_name):
    """
    Connects to MongoDB and returns:
    - ids: list of _id values as strings
    - titles: list of titles
    - contents: list of contents
    - total_count: total number of documents in the collection
    """
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        results = collection.find({}, {"_id": 1, "title": 1, "content": 1})

        ids = []
        titles = []
        contents = []

        for doc in results:
            ids.append(str(doc["_id"]))  # Convert ObjectId to string
            titles.append(doc.get("title", ""))
            contents.append(doc.get("content", ""))

        total_count = collection.count_documents({})

        return ids, titles, contents, total_count

    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return [], [], [], 0


def store_json_to_mongodb(parsed_json, mongo_uri, db_name, collection_name):
    """
    Inserts the parsed_json dictionary directly into the specified MongoDB collection.
    """
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        result = collection.insert_one(parsed_json)
        print(f"✅ JSON document inserted with _id: {result.inserted_id}")
        return str(result.inserted_id)

    except Exception as e:
        print(f"❌ Failed to insert JSON into MongoDB: {e}")
        return None


def summarize_long_statute_text(text, statute_name, deployment_name, summarization_prompt, client):
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
    insert_text_to_mongodb(summary,statute_name, mongo_uri = "mongodb://localhost:27017/", db_name = "Summarized_statutes", collection_name = "SummaryStatute")
    return summary

def call_gpt_for_base(schema, text, system_prompt, deployment_name, client, token):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Base Schema:\n{schema}\n\nStatute Text:\n{text}"}
    ]
    response = client.chat.completions.create(
        model=deployment_name,
        messages=messages,
        temperature=0.2,
        max_tokens=token
    )
    return response.choices[0].message.content.strip()

def call_gpt_for_custom(statute_text, client, system_prompt, token):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": statute_text}
        ],
        temperature=0.2,
        max_tokens=token,
    )
    return response.choices[0].message.content.strip()

def try_parse_json(text, Statutename):
    try:
        parsed = json.loads(text)
        return parsed
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}")
        print(f"🔎 Raw GPT response from {Statutename}:\n{text}")
        return None


def extract_and_fix_json(raw_text, statute_name):
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
            print(f"\n🔎 Failed file: {statute_name}")
            print("🔎 Full raw GPT response:\n")
            print(raw_text)
            return None

    store_json_to_mongodb(
        parsed_json=parsed_json,
        mongo_uri="mongodb://localhost:27017/",
        db_name="Custom_statutes",
        collection_name="statutes_custom_json"
    )

    return parsed_json

def base_statute_json_gpt(deployment_name, client, system_prompt, summarization_prompt, token):
    issue_count = 0
    # === Load single base schema ===
    base_schema_path = "D:\\LegalMorph\\transformer\\base_schema_statute.json"
    with open(base_schema_path, "r", encoding="utf-8") as f:
        schema_template = f.read()
    ids, titles, contents, count = fetch_statute_data(mongo_uri="mongodb://localhost:27017/", db_name= "Raw_statutes", collection_name= "statutes_raw_json")
    for i in range(0,count):
        statute_text = contents[i]
        statute_name = titles[i]
        print(f"\n📄 Processing {titles[i]}")

        try:
            text = summarize_long_statute_text(statute_text, statute_name, deployment_name,
                                                 summarization_prompt, client)
            success = False
            for attempt in range(3):
                try:
                    raw_response = call_gpt_for_base(schema_template, text, system_prompt, deployment_name,
                                                        client, token)
                    parsed_json = try_parse_json(raw_response, statute_name)
                    if parsed_json:
                        store_json_to_mongodb(parsed_json,mongo_uri="mongodb://localhost:27017/", db_name="Base_statutes",collection_name="statutes_base_json")
                        success = True
                        break
                    else:
                        print(f"🔁 Retry {attempt + 1}")
                        time.sleep(2)
                except Exception as e:
                    print(f"❌ GPT call failed: {e}")
                    time.sleep(2)

            if not success:
                issue_count += 1
                insert_text_to_mongodb(
                    text= statute_text,
                    title= statute_name,
                    mongo_uri="mongodb://localhost:27017/",
                    db_name="Issues_Base_statutes",
                    collection_name="statutes_issues"
                )

                print("⚠️ Moved problematic file to issues collection")

        except Exception as e:
            print(f"❌ Error processing {statute_name}: {e}")
            issue_count += 1
            insert_text_to_mongodb(
                text=statute_text,
                title=statute_name,
                mongo_uri="mongodb://localhost:27017/",
                db_name="Issues_Base_statutes",
                collection_name="statutes_issues"
            )
    print(f"\n🚨 Total files with issues: {issue_count}")
    return issue_count


def base_statute_issue_resolver(deployment_name, client, system_prompt, summarization_prompt, token):
    # === Load single base schema ===
    base_schema_path = "D:\\LegalMorph\\transformer\\base_schema_statute.json"
    with open(base_schema_path, "r", encoding="utf-8") as f:
        schema_template = f.read()
    ids, titles, contents, count = fetch_statute_data(mongo_uri="mongodb://localhost:27017/", db_name="Issues_Base_statutes",
                                                      collection_name="statutes_issues")
    for i in range (0,count):
        statute_text = contents[i]
        statute_name = titles[i]
        print(f"\n📄 Processing {titles[i]}")

        try:
            text = summarize_long_statute_text(statute_text, statute_name, deployment_name, summarization_prompt, client)
            for attempt in range(3):
                try:
                    raw_response = call_gpt_for_base(schema_template, text, system_prompt, deployment_name,
                                                        client, token)
                    parsed_json = try_parse_json(raw_response, statute_name)
                    if parsed_json:
                        store_json_to_mongodb(parsed_json,mongo_uri="mongodb://localhost:27017/", db_name="Base_statutes",collection_name="statutes_base_json")
                        break
                    else:
                        print(f"🔁 Retry {attempt + 1}")
                        time.sleep(2)
                except Exception as e:
                    print(f"❌ GPT call failed: {e}")
                    time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing {statute_name}: {e}")

def custom_statutes_json_gpt(deployment_name, client, system_prompt, summarization_prompt, token):
    issue_count = 0
    ids, titles, contents, count = fetch_statute_data(mongo_uri="mongodb://localhost:27017/", db_name="Raw_statutes",
                                                      collection_name="statutes_raw_json")
    for i in range(0,count):
        statute_text = contents[i]
        statute_name = titles[i]
        print(f"\n📄 Processing {titles[i]}")

        try:
            text = summarize_long_statute_text(statute_text, statute_name, deployment_name, summarization_prompt, client)

            raw_response = None
            success = False
            for attempt in range(3):
                try:
                    raw_response = call_gpt_for_custom(text, client, system_prompt, token)
                    fixed_json = extract_and_fix_json(raw_response, statute_name)
                    if fixed_json:
                        success = True
                        break
                    else:
                        print(
                            f"🔁 Retry attempt {attempt + 1} failed. Retrying..." if attempt < 2 else "❌ Final "
                                                                                                     "attempt failed."
                        )
                        time.sleep(2)
                except Exception as e:
                    print(f"❌ GPT call failed: {e}")
                    time.sleep(2)

            if not success:
                issue_count += 1
                insert_text_to_mongodb(
                    text=statute_text,
                    title=statute_name,
                    mongo_uri="mongodb://localhost:27017/",
                    db_name="Issues_Custom_statutes",
                    collection_name="statutes_issues"
                )
                print("⚠️ Moved problematic file to issues collection")

        except Exception as e:
            print(f"❌ Error processing {statute_name}: {e}")
            issue_count += 1
            insert_text_to_mongodb(
                text=statute_text,
                title=statute_name,
                mongo_uri="mongodb://localhost:27017/",
                db_name="Issues_Custom_statutes",
                collection_name="statutes_issues"
            )

    print(f"\n🚨 Total files with issues: {issue_count}")
    return issue_count

def custom_statute_issue_resolver(deployment_name, client, system_prompt, summarization_prompt, token):
    ids, titles, contents, count = fetch_statute_data(mongo_uri="mongodb://localhost:27017/",
                                                      db_name="Issues_Custom_statutes",
                                                      collection_name="statutes_issues")
    for i in range(0,count):
        statute_text = contents[i]
        statute_name = titles[i]
        print(f"\n📄 Processing {titles[i]}")
        try:
            text = summarize_long_statute_text(statute_text, statute_name, deployment_name, summarization_prompt, client)

            raw_response = None
            for attempt in range(3):
                raw_response = call_gpt_for_custom(text, client, system_prompt, token)

                fixed_json = extract_and_fix_json(raw_response, statute_name)
                if fixed_json:
                    break
                else:
                    print(
                        f"🔁 Retry attempt {attempt + 1} failed. Retrying..." if attempt == 0 or attempt == 1 else "❌"
                                                                                                                  "Final attempt failed.")
                    time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing {statute_name}: {e}")



def normalize_string(s):
    return re.sub(r'[^a-z0-9]+', '', s.lower()) if s else ''

def extract_json_and_name(gpt_output):
    clean_output = re.sub(r"^```json\s*|\s*```$", "", gpt_output.strip(), flags=re.IGNORECASE | re.MULTILINE)
    lines = clean_output.splitlines()
    if lines and lines[0].strip().lower().startswith("filename:"):
        return "\n".join(lines[1:]).strip()
    return clean_output


def normalize_string(s):
    return s.strip().lower()

def merge_statutes_from_db(system_prompt, openai_client, threshold=0.85):
    mongo_uri = "mongodb://localhost:27017"
    base_db_name = "Base_statutes"
    base_collection_name = "statutes_base_json"
    custom_db_name = "Custom_statutes"
    custom_collection_name = "statutes_custom_json"
    output_db_name = "Final_statutes"
    output_collection_name = "statutes_merged_final_json"

    client = MongoClient(mongo_uri)
    base_col = client[base_db_name][base_collection_name]
    custom_col = client[custom_db_name][custom_collection_name]
    output_col = client[output_db_name][output_collection_name]

    custom_docs = list(custom_col.find())
    custom_map = {
        normalize_string(doc.get("title", "")): doc for doc in custom_docs
    }
    custom_keys = list(custom_map.keys())

    issue_count = 0

    for base_doc in base_col.find():
        base_name_key = normalize_string(base_doc.get("Statute_Name", ""))
        match_list = get_close_matches(base_name_key, custom_keys, n=1, cutoff=threshold)
        match_key = match_list[0] if match_list else None

        if not match_key:
            print(f"❌ No close match for statute: {base_doc.get('Statute_Name')}")
            continue

        custom_match = custom_map[match_key]

        print(f"\n🧠 Merging: {base_doc.get('Statute_Name')} ↔️ {custom_match.get('title')}")
        success = False
        base_doc.pop('_id', None)
        custom_match.pop('_id', None)

        for attempt in range(3):
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt.strip()},
                        {"role": "user", "content": f"""
You will be provided two JSON objects.

BASE JSON:
{json.dumps(base_doc, separators=(",", ":"), ensure_ascii=False)}

CUSTOM JSON:
{json.dumps(custom_match, separators=(",", ":"), ensure_ascii=False)}
"""}
                    ],
                    temperature=0.3,
                    max_tokens=8192
                )

                merged_output = response.choices[0].message.content.strip()
                if not merged_output:
                    print(f"⚠️ Empty GPT response on attempt {attempt+1}")
                    time.sleep(1)
                    continue

                final_json_text = extract_json_and_name(merged_output)

                try:
                    parsed = json.loads(final_json_text)
                    output_col.insert_one(parsed)
                    print(f"✅ Inserted: {parsed.get('Statute_Name', '[Unknown]')}")
                    success = True
                    break

                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    print(merged_output[:500])
                    time.sleep(1)

            except Exception as e:
                print(f"❌ GPT/API Error: {e}")
                time.sleep(1)

        if not success:
            issue_count += 1
            print(f"⚠️ Failed merge for: {base_doc.get('Statute_Name')}")

    print(f"\n🔢 Total failed merges: {issue_count}")
    return issue_count
