import os
import json
import re
import time
import shutil
from Transformation.shared.utils import check_file_exists, save_metadata

def slugify_filename(name):
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    return name.strip('_')

def find_exact_match(base_filename, custom_files):
    """Find exact match between base and custom files using identical names.
    Base files are now '<name>.json'; custom files are '<name>.json'.
    """
    base_name = os.path.splitext(base_filename)[0]
    for custom_file in custom_files:
        if os.path.splitext(custom_file)[0] == base_name:
            return custom_file
    return None

def merge_json_gpt(base_dir, custom_dir, output_dir, issues_dir_base, issues_dir_custom, system_prompt, client, source_web):
    issue_count = 0
    raw_total = 0
    merge_case_names = []
    merge_issue_cases = []
    merge_total = 0
    processed = 0

    custom_files = [f for f in os.listdir(custom_dir) if f.lower().endswith(".json")]

    for base_file in os.listdir(base_dir):
        if not base_file.lower().endswith(".json"):
            continue
        else:
            raw_total += 1

        # Find exact match for custom file
        custom_file = find_exact_match(base_file, custom_files)

        if custom_file:
            base_path = os.path.join(base_dir, base_file)
            custom_path = os.path.join(custom_dir, custom_file)
            
            # Create output filename based on custom file name
            output_filename = os.path.splitext(custom_file)[0] + ".json"
            output_path = os.path.join(output_dir, output_filename)

            # Check if output file already exists
            if check_file_exists(output_path):
                print(f"⏩ Skipping {base_file} + {custom_file} (output already exists)")
                processed += 1
                continue

            try:
                with open(base_path, 'r', encoding='utf-8') as bf, open(custom_path, 'r', encoding='utf-8') as cf:
                    base_json = json.load(bf)
                    custom_json = json.load(cf)

                success = False
                for attempt in range(3):
                    # Debug preview disabled per request
                    try:
                        print(f"🧠 Attempt {attempt + 1}: Merging {base_file} + {custom_file}")
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": system_prompt.strip()},
                                {"role": "user", "content": f"""
You will be provided two JSON objects.

BASE JSON:
{json.dumps(base_json, separators=(",", ":"), ensure_ascii=False)}

CUSTOM JSON:
{json.dumps(custom_json, separators=(",", ":"), ensure_ascii=False)}
"""}
                            ],
                            temperature=0.3,
                            max_tokens=8192
                        )

                        merged_output = response.choices[0].message.content.strip()

                        if not merged_output:
                            print(f"⚠️ GPT returned empty response. Attempt {attempt + 1}")
                            time.sleep(1)
                            continue

                        final_json_text = re.sub(r"^```json\s*|\s*```$", "", merged_output.strip(), flags=re.IGNORECASE)

                        if not final_json_text.strip():
                            print(f"⚠️ GPT response was blank on attempt {attempt + 1}")
                            time.sleep(1)
                            continue

                        try:
                            parsed = json.loads(final_json_text)
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            with open(output_path, "w", encoding="utf-8") as f:
                                json.dump(parsed, f, indent=2, ensure_ascii=False)
                            print(f"✅ Merged and saved: {output_filename}")
                            success = True
                            merge_case_names.append(os.path.splitext(custom_file)[0])
                            merge_total += 1
                            break

                        except json.JSONDecodeError as e:
                            print(f"❌ JSON Parse Error (attempt {attempt + 1}): {e}")
                            print("📥 GPT Raw Response:\n", merged_output[:1000], "...\n")
                            time.sleep(1)

                    except Exception as e:
                        print(f"❌ GPT/API Error (attempt {attempt + 1}): {e}")
                        time.sleep(1)

                # 🛑 Handle persistent failure
                if not success:
                    issue_count += 1
                    merge_issue_cases.append(custom_file)
                    print(f"⚠️ Final failure after 3 attempts: {base_file} + {custom_file}")
                    try:
                        os.makedirs(issues_dir_base, exist_ok=True)
                        os.makedirs(issues_dir_custom, exist_ok=True)
                        # Copy failed files into merge issues tree: .../merge/issues_cases/<source>/{base|custom}
                        shutil.copy(base_path, os.path.join(issues_dir_base, base_file))
                        shutil.copy(custom_path, os.path.join(issues_dir_custom, custom_file))
                        print(f"📁 Copied {base_file} to issues_dir_base and {custom_file} to issues_dir_custom.")
                    except Exception as copy_err:
                        print(f"❌ Failed to copy failed files: {copy_err}")

            except Exception as e:
                print(f"❌ Error processing {base_file} + {custom_file}: {e}")
                issue_count += 1
                merge_issue_cases.append(custom_file)
        else:
            print(f"❌ No exact match found for {base_file}")

    print(f"\n🔢 Total problematic files: {issue_count}")
    # Standardized 6-tuple: (issues, processed, filenames, issue_filenames, raw_count, skipped_existing)
    return issue_count, merge_total, merge_case_names, merge_issue_cases, raw_total, processed


def merge_issue_resolver(base_dir, custom_dir, output_dir, system_prompt, client, source_web):
    count = 0
    custom_files = [f for f in os.listdir(custom_dir) if f.lower().endswith(".json")]

    for base_file in os.listdir(base_dir):
        if not base_file.lower().endswith(".json"):
            continue

        # Find exact match for custom file
        custom_file = find_exact_match(base_file, custom_files)

        if custom_file:
            base_path = os.path.join(base_dir, base_file)
            custom_path = os.path.join(custom_dir, custom_file)
            
            # Create output filename based on custom file name
            output_filename = os.path.splitext(custom_file)[0] + ".json"
            output_path = os.path.join(output_dir, output_filename)

            # Check if output file already exists
            if check_file_exists(output_path):
                print(f"⏩ Skipping {base_file} + {custom_file} (output already exists)")
                continue

            try:
                with open(base_path, 'r', encoding='utf-8') as bf, open(custom_path, 'r', encoding='utf-8') as cf:
                    base_json = json.load(bf)
                    custom_json = json.load(cf)

                success = False
                for attempt in range(3):
                    # Debug preview disabled per request
                    try:
                        print(f"🧠 Attempt {attempt + 1}: Merging {base_file} + {custom_file}")
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": system_prompt.strip()},
                                {"role": "user", "content": f"""
You will be provided two JSON objects.

BASE JSON:
{json.dumps(base_json, separators=(",", ":"), ensure_ascii=False)}

CUSTOM JSON:
{json.dumps(custom_json, separators=(",", ":"), ensure_ascii=False)}
"""}
                            ],
                            temperature=0.3,
                            max_tokens=16000
                        )

                        merged_output = response.choices[0].message.content.strip()

                        if not merged_output:
                            print(f"⚠️ GPT returned empty response. Attempt {attempt + 1}")
                            time.sleep(1)
                            continue

                        final_json_text = re.sub(r"^```json\s*|\s*```$", "", merged_output.strip(), flags=re.IGNORECASE)

                        if not final_json_text.strip():
                            print(f"⚠️ GPT response was blank on attempt {attempt + 1}")
                            time.sleep(1)
                            continue

                        try:
                            parsed = json.loads(final_json_text)
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            with open(output_path, "w", encoding="utf-8") as f:
                                json.dump(parsed, f, indent=2, ensure_ascii=False)
                            print(f"✅ Merged and saved: {output_filename}")
                            success = True
                            count += 1
                            break

                        except json.JSONDecodeError as e:
                            print(f"❌ JSON Parse Error (attempt {attempt + 1}): {e}")
                            print("📥 GPT Raw Response:\n", merged_output[:1000], "...\n")
                            time.sleep(1)

                    except Exception as e:
                        print(f"❌ GPT/API Error (attempt {attempt + 1}): {e}")
                        time.sleep(1)

                # 🛑 Handle persistent failure
                if not success:
                    print(f"⚠️ Final failure after 3 attempts: {base_file} + {custom_file}")

            except Exception as e:
                print(f"❌ Error processing {base_file} + {custom_file}: {e}")
        else:
            print(f"❌ No exact match found for {base_file}")
    return count 