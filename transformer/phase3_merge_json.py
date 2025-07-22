import os
import json
import re
import difflib
import time
import shutil

def slugify_filename(name):
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    return name.strip('_')

def find_best_match(slug_base, slug_custom_files, match_threshold):
    matches = difflib.get_close_matches(slug_base, slug_custom_files, n=1, cutoff=match_threshold)
    return matches[0] if matches else None

def extract_json_and_name(gpt_output):
    # Remove wrapping triple backticks if any
    clean_output = re.sub(r"^```json\s*|\s*```$", "", gpt_output.strip(), flags=re.IGNORECASE | re.MULTILINE)

    # If output starts with FILENAME line, skip it
    lines = clean_output.splitlines()
    if lines and lines[0].strip().lower().startswith("filename:"):
        json_part = "\n".join(lines[1:]).strip()
        return json_part

    return clean_output


def merge_json_gpt(base_dir, custom_dir, output_dir, issues_dir_base, issues_dir_custom, system_prompt, client, match_threshold):
    issue_count = 0

    custom_files_map = {
        slugify_filename(f): f for f in os.listdir(custom_dir) if f.lower().endswith(".json")
    }

    for base_file in os.listdir(base_dir):
        if not base_file.lower().endswith(".json"):
            continue

        slug_base = slugify_filename(base_file.replace("base", ""))
        best_slug_match = find_best_match(slug_base, list(custom_files_map.keys()), match_threshold)

        if best_slug_match:
            custom_file = custom_files_map[best_slug_match]
            base_path = os.path.join(base_dir, base_file)
            custom_path = os.path.join(custom_dir, custom_file)

            with open(base_path, 'r', encoding='utf-8') as bf, open(custom_path, 'r', encoding='utf-8') as cf:
                base_json = json.load(bf)
                custom_json = json.load(cf)

            print("\n📦 === GPT Input Preview ===")
            print("📄 BASE JSON:", json.dumps(base_json, indent=2, ensure_ascii=False)[:1500], "...\n")
            print("📄 CUSTOM JSON:", json.dumps(custom_json, indent=2, ensure_ascii=False)[:1500], "...\n")

            success = False
            for attempt in range(3):
                try:
                    print(f"🧠 Attempt {attempt + 1}: Merging {base_file} + {custom_file}")
                    response = client.chat.completions.create(
                        model="model name",
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
                        output_filename = os.path.splitext(custom_file)[0] + ".json"
                        output_path = os.path.join(output_dir, output_filename)
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(parsed, f, indent=2, ensure_ascii=False)
                        print(f"✅ Merged and saved: {output_filename}")
                        success = True
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
                print(f"⚠️ Final failure after 3 attempts: {base_file} + {custom_file}")
                try:
                    shutil.copy(base_path, os.path.join(issues_dir_base, base_file))
                    shutil.copy(custom_path, os.path.join(issues_dir_custom, custom_file))
                    print(f"📁 Copied {base_file} to issues_dir_base and {custom_file} to issues_dir_custom.")
                except Exception as copy_err:
                    print(f"❌ Failed to copy failed files: {copy_err}")
        else:
            print(f"❌ No match found for {base_file}")

    print(f"\n🔢 Total problematic files: {issue_count}")
    return issue_count

def merge_issue_resolver(base_dir, custom_dir, output_dir, system_prompt, client, match_threshold):
    custom_files_map = {
        slugify_filename(f): f for f in os.listdir(custom_dir) if f.lower().endswith(".json")
    }

    for base_file in os.listdir(base_dir):
        if not base_file.lower().endswith(".json"):
            continue

        slug_base = slugify_filename(base_file.replace("base", ""))
        best_slug_match = find_best_match(slug_base, list(custom_files_map.keys()), match_threshold)

        if best_slug_match:
            custom_file = custom_files_map[best_slug_match]
            base_path = os.path.join(base_dir, base_file)
            custom_path = os.path.join(custom_dir, custom_file)

            with open(base_path, 'r', encoding='utf-8') as bf, open(custom_path, 'r', encoding='utf-8') as cf:
                base_json = json.load(bf)
                custom_json = json.load(cf)

            print("\n📦 === GPT Input Preview ===")
            print("📄 BASE JSON:", json.dumps(base_json, indent=2, ensure_ascii=False)[:1500], "...\n")
            print("📄 CUSTOM JSON:", json.dumps(custom_json, indent=2, ensure_ascii=False)[:1500], "...\n")

            success = False
            for attempt in range(3):
                try:
                    print(f"🧠 Attempt {attempt + 1}: Merging {base_file} + {custom_file}")
                    response = client.chat.completions.create(
                        model="model name",
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
                        output_filename = os.path.splitext(custom_file)[0] + ".json"
                        output_path = os.path.join(output_dir, output_filename)
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(parsed, f, indent=2, ensure_ascii=False)
                        print(f"✅ Merged and saved: {output_filename}")
                        success = True
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
        else:
            print(f"❌ No match found for {base_file}")
