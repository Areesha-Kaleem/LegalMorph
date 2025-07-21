import os
import json
from pymongo import MongoClient

def load_json(json_dir):
    mongo_uri = "mongodb://localhost:27017"  # or your Atlas URI
    db_name = "TestCases"
    collection_name = "cases"

    # === CONNECT TO MONGODB ===
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    # === LOAD JSON FILES ===
    inserted_count = 0
    for filename in os.listdir(json_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(json_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        collection.insert_one(data)
                        inserted_count += 1
                    elif isinstance(data, list):
                        collection.insert_many(data)
                        inserted_count += len(data)
                    print(f"✅ Inserted from {filename}")
            except Exception as e:
                print(f"❌ Failed to insert {filename}: {e}")

    print(f"\n📦 Done. Total documents inserted: {inserted_count}")
