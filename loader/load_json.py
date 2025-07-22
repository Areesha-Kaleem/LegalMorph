import os
import json
from pymongo import MongoClient

def load_json(json_dir, name, collection):
    mongo_uri = "mongodb://localhost:27017"  # or your Atlas URI
    db_name = name
    collection_name = collection

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


def txt_json_db():
    # MongoDB connection setup
    client = MongoClient("mongodb://localhost:27017/")  # change this if you're using remote DB
    db = client["Raw"]
    collection = db["Legal_raw_cases"]

    # Directory containing .txt files
    text_dir = "D:\\LegalMorph\\data"

    # Loop through all .txt files and insert into MongoDB
    for filename in os.listdir(text_dir):
        if filename.endswith(".txt"):
            file_path = os.path.join(text_dir, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()

            doc = {
                "id": os.path.splitext(filename)[0],  # filename without .txt
                "raw_data": raw_text
            }

            # Insert into MongoDB
            collection.insert_one(doc)
            print(f"✅ Inserted {filename} into MongoDB")

    print("🎉 All .txt files inserted successfully.")
