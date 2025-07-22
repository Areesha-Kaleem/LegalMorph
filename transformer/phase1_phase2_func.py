import os
import json
import time
import tiktoken
import shutil
from dotenv import load_dotenv
import re
import json5

load_dotenv()


# === Token helper ===
def count_tokens(text, model="your model name"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


# === Chunking for summarization ===
def split_text_into_token_chunks(text, max_tokens_per_chunk=120000):
    enc = tiktoken.encoding_for_model("your deployment name")
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
        model="model name",
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


# === Main Loop ===
def base_json_gpt(input_dir, output_dir, summarise_dir, issue_dir, deployment_name, client, system_prompt,
                  summarization_prompt, token):
    issue_count = 0
    # === Load single base schema ===
    base_schema_path = "D:\\LegalMorph\\transformer\\base_schema_template.json"
    with open(base_schema_path, "r", encoding="utf-8") as f:
        schema_template = f.read()
    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue

        print(f"\n📄 Processing {filename}")
        file_path = os.path.join(input_dir, filename)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                case_text = f.read()

            case_text = summarize_text_if_needed(case_text, filename, summarise_dir, deployment_name,
                                                 summarization_prompt, client)
            success = False
            for attempt in range(3):
                try:
                    raw_response = call_gpt_with_schema(schema_template, case_text, system_prompt, deployment_name,
                                                        client, token)
                    parsed_json = try_parse_json(raw_response, filename)
                    if parsed_json:
                        out_path = os.path.join(output_dir, filename.replace(".txt", "_base.json"))
                        with open(out_path, "w", encoding="utf-8") as f:
                            json.dump(parsed_json, f, indent=2, ensure_ascii=False)
                        print(f"✅ Saved to {out_path}")
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
                dest_path = os.path.join(issue_dir, filename)
                shutil.copy(file_path, dest_path)
                print(f"⚠️ Moved problematic file to issue dir: {dest_path}")

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            issue_count += 1
            dest_path = os.path.join(issue_dir, filename)
            shutil.copy(file_path, dest_path)
    print(f"\n🚨 Total files with issues: {issue_count}")
    return issue_count


def base_issue_resolver(input_dir, output_dir, summarise_dir, deployment_name, client, system_prompt,
                        summarization_prompt, token):
    # === Load single base schema ===
    base_schema_path = "D:\\LegalMorph\\transformer\\base_schema_template.json"
    with open(base_schema_path, "r", encoding="utf-8") as f:
        schema_template = f.read()
    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue

        print(f"\n📄 Processing {filename}")
        file_path = os.path.join(input_dir, filename)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                case_text = f.read()

            case_text = summarize_text_if_needed(case_text, filename, summarise_dir, deployment_name,
                                                 summarization_prompt, client)
            for attempt in range(3):
                try:
                    raw_response = call_gpt_with_schema(schema_template, case_text, system_prompt, deployment_name,
                                                        client, token)
                    parsed_json = try_parse_json(raw_response, filename)
                    if parsed_json:
                        out_path = os.path.join(output_dir, filename.replace(".txt", "_base.json"))
                        with open(out_path, "w", encoding="utf-8") as f:
                            json.dump(parsed_json, f, indent=2, ensure_ascii=False)
                        print(f"✅ Saved to {out_path}")
                        break
                    else:
                        print(f"🔁 Retry {attempt + 1}")
                        time.sleep(2)
                except Exception as e:
                    print(f"❌ GPT call failed: {e}")
                    time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")


def custom_json_gpt(input_dir, output_dir, summarise_dir, issue_dir, deployment_name, client, system_prompt,
                    summarization_prompt, token):
    issue_count = 0
    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue

        file_path = os.path.join(input_dir, filename)
        print(f"\n📄 Processing {filename}")

        try:
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
                    output_filename = f"_{re.sub(r'[^a-zA-Z0-9]+', '_', filename[:-4].lower())}.json"
                    output_path = os.path.join(output_dir, output_filename)

                    fixed_json = extract_and_fix_json(raw_response, filename, output_path)
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
                issue_dest = os.path.join(issue_dir, filename)
                shutil.copy(file_path, issue_dest)
                print(f"⚠️ Moved problematic file to issue dir: {issue_dest}")

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            issue_count += 1
            issue_dest = os.path.join(issue_dir, filename)
            shutil.copy(file_path, issue_dest)

    print(f"\n🚨 Total files with issues: {issue_count}")
    return issue_count


def custom_issue_resolver(input_dir, output_dir, summarise_dir, deployment_name, client, system_prompt,
                          summarization_prompt, token):
    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".txt"):
            continue

        file_path = os.path.join(input_dir, filename)
        print(f"\n📄 Processing {filename}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                case_text = f.read()

            case_text = summarize_text_if_needed(case_text, filename, summarise_dir, deployment_name,
                                                 summarization_prompt, client)

            raw_response = None
            for attempt in range(3):
                raw_response = call_gpt_for_file(case_text, client, system_prompt, token)
                output_filename = f"_{re.sub(r'[^a-zA-Z0-9]+', '_', filename[:-4].lower())}.json"
                output_path = os.path.join(output_dir, output_filename)

                fixed_json = extract_and_fix_json(raw_response, filename, output_path)
                if fixed_json:
                    break
                else:
                    print(
                        f"🔁 Retry attempt {attempt + 1} failed. Retrying..." if attempt == 0 or attempt == 1 else "❌"
                                                                                                                  "Final attempt failed.")
                    time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
