import os
import json
import time
import shutil
from Transformation.shared.utils import (
    call_gpt_with_schema, try_parse_json, summarize_text_if_needed,
    check_file_exists, load_schema
)

def base_statute_json_gpt(input_dir, output_dir, summarise_dir, issue_dir, deployment_name, client, system_prompt,
                          summarization_prompt, token, source_web):
    issue_count = 0
    raw_total = 0
    base_total = 0
    base_names = []
    issue_names = []
    processed = 0

    # === Load single base schema ===
    # Resolve schema path directly from shared folder
    base_dir = os.path.dirname(__file__)
    base_schema_path = os.path.join(os.path.dirname(base_dir), "shared", "base_schema_statutes.json")
    schema_template = load_schema(base_schema_path)
    if not schema_template:
        print(f"❌ Failed to load base schema from: {base_schema_path}")
        return issue_count, base_total, base_names, issue_names, raw_total

    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue
        else:
            raw_total += 1

        file_path = os.path.join(input_dir, filename)
        output_filename = filename.replace(".txt", ".json")
        output_path = os.path.join(output_dir, output_filename)

        # Check if output file already exists
        if check_file_exists(output_path):
            print(f"⏩ Skipping {filename} (output already exists)")
            processed += 1
            continue

        try:
            print(f"\n📄 Processing {filename}")
            with open(file_path, "r", encoding="utf-8") as f:
                statute_text = f.read()

            statute_text = summarize_text_if_needed(statute_text, filename, summarise_dir, deployment_name,
                                                   summarization_prompt, client)
            success = False
            for attempt in range(3):
                try:
                    raw_response = call_gpt_with_schema(schema_template, statute_text, system_prompt, deployment_name,
                                                        client, token)
                    parsed_json = try_parse_json(raw_response, filename)
                    if parsed_json:
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(parsed_json, f, indent=2, ensure_ascii=False)
                        print(f"✅ Saved to {output_path}")
                        success = True
                        base_total += 1
                        base_names.append(filename)
                        break
                    else:
                        print(f"🔁 Retry {attempt + 1}")
                        time.sleep(2)
                except Exception as e:
                    print(f"❌ GPT call failed: {e}")
                    time.sleep(2)

            if not success:
                issue_count += 1
                issue_names.append(filename)
                dest_path = os.path.join(issue_dir, filename)
                shutil.copy(file_path, dest_path)
                print(f"⚠️ Moved problematic file to issue dir: {dest_path}")

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            issue_count += 1
            issue_names.append(filename)
            dest_path = os.path.join(issue_dir, filename)
            shutil.copy(file_path, dest_path)
            print(f"⚠️ Moved problematic file to issue dir: {dest_path}")

    print(f"\n🚨 Total files with issues: {issue_count}")
    # Standardized 6-tuple: (issues, processed, filenames, issue_filenames, raw_count, skipped_existing)
    return issue_count, base_total, base_names, issue_names, raw_total, processed


def base_statute_issue_resolver(input_dir, output_dir, summarise_dir, deployment_name, client, system_prompt,
                                summarization_prompt, token, source_web):
    count = 0
    # === Load single base schema ===
    base_schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared", "base_schema_statutes.json")
    schema_template = load_schema(base_schema_path)
    if not schema_template:
        print(f"❌ Failed to load base schema from: {base_schema_path}")
        return count

    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue

        file_path = os.path.join(input_dir, filename)
        output_filename = filename.replace(".txt", ".json")
        output_path = os.path.join(output_dir, output_filename)

        # Check if output file already exists
        if check_file_exists(output_path):
            print(f"⏩ Skipping {filename} (output already exists)")
            continue

        try:
            print(f"\n📄 Processing {filename}")
            with open(file_path, "r", encoding="utf-8") as f:
                statute_text = f.read()

            statute_text = summarize_text_if_needed(statute_text, filename, summarise_dir, deployment_name,
                                                   summarization_prompt, client)
            for attempt in range(3):
                try:
                    raw_response = call_gpt_with_schema(schema_template, statute_text, system_prompt, deployment_name,
                                                        client, token)
                    parsed_json = try_parse_json(raw_response, filename)
                    if parsed_json:
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(parsed_json, f, indent=2, ensure_ascii=False)
                        print(f"✅ Saved to {output_path}")
                        count += 1
                        break
                    else:
                        print(f"🔁 Retry {attempt + 1}")
                        time.sleep(2)
                except Exception as e:
                    print(f"❌ GPT call failed: {e}")
                    time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
    return count 