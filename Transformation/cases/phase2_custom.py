import os
import time
import shutil
import re
from Transformation.shared.utils import (
    call_gpt_for_file, extract_and_fix_json, summarize_text_if_needed,
    check_file_exists
)

def custom_json_gpt(input_dir, output_dir, summarise_dir, issue_dir, deployment_name, client, system_prompt,
                    summarization_prompt, token, source_web):
    issue_count = 0
    total_count = 0
    case_names = []
    issue_names = []
    raw_count = 0
    processed = 0

    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue
        else:
            raw_count += 1

        file_path = os.path.join(input_dir, filename)
        # Use original txt filename base for easier merge matching (custom file == base name without suffix)
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
                case_text = f.read()

            case_text = summarize_text_if_needed(
                case_text,
                filename,
                summarise_dir,
                deployment_name,
                summarization_prompt,
                client
            )

            raw_response = None
            success = False
            for attempt in range(3):
                try:
                    raw_response = call_gpt_for_file(case_text, client, system_prompt, token)

                    fixed_json = extract_and_fix_json(raw_response, filename, output_path)
                    if fixed_json:
                        success = True
                        case_names.append(filename)
                        total_count += 1
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
                issue_names.append(filename)
                issue_dest = os.path.join(issue_dir, filename)
                shutil.copy(file_path, issue_dest)
                print(f"⚠️ Moved problematic file to issue dir: {issue_dest}")

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            issue_count += 1
            issue_names.append(filename)
            issue_dest = os.path.join(issue_dir, filename)
            shutil.copy(file_path, issue_dest)
            print(f"⚠️ Moved problematic file to issue dir: {issue_dest}")

    print(f"\n🚨 Total files with issues: {issue_count}")
    return issue_count, total_count, case_names, issue_names, raw_count, processed


def custom_issue_resolver(input_dir, output_dir, summarise_dir, deployment_name, client, system_prompt,
                          summarization_prompt, token, source_web, issue_dir):
    count = 0
    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue

        file_path = os.path.join(input_dir, filename)
        # Match the same convention as main custom phase
        output_filename = filename.replace(".txt", ".json")
        output_path = os.path.join(output_dir, output_filename)

        # Check if output file already exists
        if check_file_exists(output_path):
            print(f"⏩ Skipping {filename} (output already exists)")
            continue

        try:
            print(f"\n📄 Processing {filename}")
            with open(file_path, "r", encoding="utf-8") as f:
                case_text = f.read()

            case_text = summarize_text_if_needed(case_text, filename, summarise_dir, deployment_name,
                                                 summarization_prompt, client)

            raw_response = None
            for attempt in range(3):
                raw_response = call_gpt_for_file(case_text, client, system_prompt, token)

                fixed_json = extract_and_fix_json(raw_response, filename, output_path)
                if fixed_json:
                    count += 1
                    break
                else:
                    print(
                        f"🔁 Retry attempt {attempt + 1} failed. Retrying..." if attempt == 0 or attempt == 1 else "❌"
                                                                                                                  "Final attempt failed.")
                    time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
    return count 