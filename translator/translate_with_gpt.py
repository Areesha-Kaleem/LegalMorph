import os
import sys
import argparse
import time
from typing import List, Tuple

# Optional token encoder for accurate chunking (falls back gracefully if missing)
try:
    import tiktoken  # type: ignore
except Exception:
    tiktoken = None

# Azure OpenAI client
try:
    import openai  # type: ignore
except Exception as e:
    print("Please install the openai package: pip install openai")
    raise e


DEFAULT_OUTPUT_DIR = os.path.join("data", "uae", "raw", "adjd", "translated_text")

# Built-in Azure OpenAI defaults (matches Transformation config)
DEFAULT_AZURE_OPENAI_API_KEY = "EkkatBw5ktWZPOs3unXeiH5lNAKpMAYOYJqQuaOpiAGjDHDY4xZUJQQJ99BGACYeBjFXJ3w3AAAAACOGtZUY"
DEFAULT_AZURE_OPENAI_API_VERSION = "2024-11-01-preview"
DEFAULT_AZURE_OPENAI_ENDPOINT = "https://data-ai-interns.cognitiveservices.azure.com/"
DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-4o"


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_encoder(model: str):
    if tiktoken is None:
        return None
    # gpt-4o uses cl100k_base-compatible encoding; fallback to cl100k_base
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, encoder) -> int:
    if encoder is None:
        # Rough fallback: assume ~4 chars/token
        return max(1, len(text) // 4)
    return len(encoder.encode(text))


def chunk_by_tokens(text: str, max_tokens: int, encoder) -> List[str]:
    if encoder is None:
        # Fallback chunking by characters with rough estimate
        approx_chars = max_tokens * 4
        return [text[i:i+approx_chars] for i in range(0, len(text), approx_chars)]
    tokens = encoder.encode(text)
    chunks: List[str] = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i:i+max_tokens]
        chunks.append(encoder.decode(chunk_tokens))
    return chunks


def translate_chunk_azure(client, deployment: str, chunk: str, temperature: float = 0.2, max_retries: int = 3, retry_delay: float = 2.0) -> str:
    """Translate a single chunk with Azure OpenAI (gpt-4o deployment)."""
    system_prompt = (
        "You are a professional legal translator. Translate Arabic to English faithfully. "
        "Preserve numerals, headings, line breaks, and section structure. "
        "Do not summarize or add commentary. Output English only."
    )
    user_prompt = (
        "Translate the following Arabic legal text to English. Keep numerals as-is and preserve formatting.\n\n" + chunk
    )
    last_err = None
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=deployment,  # Azure uses deployment name in the 'model' field
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            time.sleep(retry_delay * attempt)
    raise RuntimeError(f"Translation failed after {max_retries} attempts: {last_err}")


def translate_text(text: str, max_input_tokens: int) -> str:
    """Chunk by tokens and translate with Azure OpenAI only."""
    # Initialize Azure OpenAI client (hardcoded defaults)
    print("[info] Initializing Azure OpenAI client...")
    client = openai.AzureOpenAI(
        api_key=DEFAULT_AZURE_OPENAI_API_KEY,
        api_version=DEFAULT_AZURE_OPENAI_API_VERSION,
        azure_endpoint=DEFAULT_AZURE_OPENAI_ENDPOINT,
    )
    deployment = DEFAULT_AZURE_OPENAI_DEPLOYMENT
    print(f"[info] Using deployment: {deployment}")

    # Token counting and chunking
    encoder = get_encoder(deployment)
    total_tokens = count_tokens(text, encoder)
    print(f"[info] Total tokens: {total_tokens}")
    if total_tokens <= max_input_tokens:
        print("[info] Single-shot translation (within token limit)")
        return translate_chunk_azure(client, deployment, text)
    # Chunk
    chunks = chunk_by_tokens(text, max_input_tokens, encoder)
    print(f"[info] Chunking into {len(chunks)} parts (max_input_tokens={max_input_tokens})")
    translated_parts: List[str] = []
    for idx, ch in enumerate(chunks, 1):
        print(f"[info] Translating chunk {idx}/{len(chunks)}")
        translated = translate_chunk_azure(client, deployment, ch)
        translated_parts.append(translated)
    return "\n\n".join(translated_parts).strip()


def build_output_path(input_path: str, output_dir: str) -> str:
    base = os.path.basename(input_path)
    return os.path.join(output_dir, base)


def translate_file(input_file: str, output_dir: str, max_input_tokens: int) -> Tuple[str, str]:
    """Translate a single .txt file and write the output next to output_dir, mirroring filename.

    Skips translation if the output file already exists.
    """
    out_path = build_output_path(input_file, output_dir)
    if os.path.exists(out_path):
        print(f"[skip] Exists: {out_path}")
        return input_file, out_path
    print(f"[info] Reading: {input_file}")
    raw_text = read_text_file(input_file)
    translated = translate_text(raw_text, max_input_tokens)
    write_text_file(out_path, translated)
    print(f"[ok] Saved: {out_path}")
    return input_file, out_path


def translate_directory(input_dir: str, output_dir: str, max_input_tokens: int) -> None:
    """Translate all .txt files under input_dir recursively."""
    total = 0
    ok = 0
    for root, _, files in os.walk(input_dir):
        for name in files:
            if not name.lower().endswith(".txt"):
                continue
            in_path = os.path.join(root, name)
            rel = os.path.relpath(in_path, input_dir)
            out_path = os.path.join(output_dir, rel)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            if os.path.exists(out_path):
                print(f"[skip] Exists: {out_path}")
                continue
            total += 1
            try:
                print(f"[run] Translating: {in_path}")
                _, saved = translate_file(in_path, os.path.dirname(out_path), max_input_tokens)
                ok += 1
            except Exception as e:
                print(f"[err] Failed: {in_path} -> {e}")
    print(f"[summary] Done. Files processed: {total}, succeeded: {ok}, failed: {total-ok}")


def main():
    """CLI entrypoint: Azure-only translation, no runtime API config needed."""
    parser = argparse.ArgumentParser(description="Translate Arabic TXT files to English using Azure OpenAI gpt-4o with token-aware chunking.")
    parser.add_argument("--input", required=True, help="Path to a .txt file or a directory containing .txt files")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for translated files")
    parser.add_argument("--max-input-tokens", type=int, default=60000, help="Max tokens per request (safe margin below model limit)")
    args = parser.parse_args()

    if os.path.isdir(args.input):
        translate_directory(args.input, args.output_dir, args.max_input_tokens)
    else:
        if not args.input.lower().endswith(".txt"):
            print("ERROR: --input must be a .txt file or a directory containing .txt files")
            sys.exit(1)
        in_path, out_path = translate_file(args.input, args.output_dir, args.max_input_tokens)
        print(f"[done] Translated: {in_path}\n[done] Saved: {out_path}")


# if __name__ == "__main__":
#     main()


