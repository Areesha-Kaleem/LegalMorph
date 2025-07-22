import os
from openai import AzureOpenAI
from dotenv import load_dotenv
from transformer.phase1_phase2_func import base_json_gpt, base_issue_resolver, custom_json_gpt, custom_issue_resolver
from transformer.phase3_merge_json import merge_json_gpt, merge_issue_resolver

load_dotenv()
def transform():
    # --- Azure OpenAI GPT-4o client setup ---
    client = AzureOpenAI(
        api_key="Your api key",
        api_version="version",
        azure_endpoint="platform endpoint"
    )

    # Directories
    deployment_name = "name"
    input_dir = "D:/LegalMorph/data"
    output_dir_base = "D:/LegalMorph/base_json"
    summarized_dir = "D:/LegalMorph/summarized_text"
    issues_dir_base = "D:/LegalMorph/issues_base"
    output_dir_custom = "D:/LegalMorph/custom_json"
    issues_dir_custom = "D:/LegalMorph/issues_custom"
    final_json = "D:/LegalMorph/final_json"
    # input_dir = "D:/LegalMorph/test_data"
    # output_dir_base = "D:/LegalMorph/test_base"
    # summarized_dir = "D:/LegalMorph/test_summary"
    # issues_dir_base = "D:/LegalMorph/test_issue_base"
    # output_dir_custom = "D:/LegalMorph/test_custom"
    # issues_dir_custom = "D:/LegalMorph/test_issue_custom"
    # final_json = "D:/LegalMorph/test_final_json"
    os.makedirs(output_dir_base, exist_ok=True)
    os.makedirs(summarized_dir, exist_ok=True)
    os.makedirs(issues_dir_base, exist_ok=True)
    os.makedirs(issues_dir_custom, exist_ok=True)
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir_custom, exist_ok=True)
    os.makedirs(final_json, exist_ok=True)

    # threshold
    match_threshold = 0.6

    # === Prompts ===
    base_prompt = """
    You are a Legal Case Data Transformer and Assistant Data Enhancer AI.
    
    You will be given:
    1. A base schema in JSON format.
    2. A raw legal case text.
    
    Your task is to:
    - Create a JSON object based on the provided base schema.
    - Fill each field using information extracted from the legal case text using NLP.
    - If you find any additional information in the case and it's not part of the base schema, include it in the output JSON as suitable key-value pair.
    
    Guidelines:
    - Limit your JSON fields and content so that your total output does not exceed 8000 tokens.
    - For missing fields, write "N/A" to preserve schema completeness.
    - Avoid vague terms like “others” — list all entities explicitly.
    - Ensure all dates, names, references, and legal provisions are accurate.
    - Write summaries in concise, factual tone — avoid flowery or narrative style and keep it in 250 words.
    - In fields like result, punishment, and legal arguments, use complete and clear values.
    - Do NOT include Markdown formatting, no ```json or extra explanation.
    
    Final Output Format:
    pure JSON content only (no markdown block)
    """

    summarization_prompt = "Summarize this legal case clearly while preserving important names, arguments, judgments, case numbers, and legal reasoning. Remove procedural noise."

    custom_prompt = """
    You are a legal NLP assistant that converts raw legal case text into structured JSON data.
    
    Instructions:
    - Analyze the text carefully using NLP.
    - DO NOT use deeply nested structures or complex JSON arrays.
    - Keep the schema shallow and flat where possible.
    - Represent people, laws, or properties using plain key-value pairs.
    - Do not use deeply recursive structures (e.g., list of objects inside objects unless absolutely needed).
    - Use only double quotes for keys and values.
    
    Output Rules:
    - ONLY return the pure JSON object (no markdown, no code blocks, no comments).
    - Ensure it is a valid and complete JSON.
    - Be concise and avoid overfitting structure to unclear text.
    
    You are allowed to skip unknown or ambiguous details. Simplicity and validity are more important.
    """

    custom_issue_prompt = """
    You are a legal NLP assistant that converts raw legal case text into structured JSON data.
    
    Instructions:
    - Analyze the text carefully using NLP.
    - DO NOT use deeply nested structures or complex JSON arrays.
    - Keep the schema shallow and flat where possible.
    - Represent people, laws, or properties using plain key-value pairs.
    - Do not use deeply recursive structures (e.g., list of objects inside objects unless absolutely needed).
    - Use only double quotes for keys and values.
    _ Try to keep your response in 8000 token, if exceed you are allowed to filter out extreme important information.
    
    Output Rules:
    - ONLY return the pure JSON object (no markdown, no code blocks, no comments).
    - Ensure it is a valid and complete JSON.
    """

    base_issue_prompt = """
    You are a Legal Case Data Transformer AI.
    
    You will be given:
    1. A base schema in JSON format.
    2. A raw legal case text.
    
    Your task is to:
    - Create a JSON object based on the provided base schema.
    - Fill each field using information extracted from the legal case text using NLP.
    
    Guidelines:
    - Limit your JSON fields and content so that your total output does not exceed 8000 tokens.
    - For missing fields, write "N/A" to preserve schema completeness.
    - Avoid vague terms like “others” — list all entities explicitly.
    - Ensure all dates, names, references, and legal provisions are accurate.
    - Write summaries strictly concise and short.
    - In fields like result and punishment, use complete and clear values.
    - Do NOT include Markdown formatting, no ```json or extra explanation.
    
    Final Output Format:
    Your final response must be a pure JSON (no markdown block)
    """

    merge_prompt = """
    You are a smart JSON merger bot.
    
    You will be provided two JSON objects:
    1. A base JSON containing structured legal case data.
    2. A custom JSON containing additional extracted information.
    
    Your job:
    - Intelligently merge the custom JSON into the base JSON.
    - Preserve all keys from the base JSON.
    - For overlapping fields, prefer the more contextually accurate or complete value.
    - Use your NLP understanding to resolve any semantic differences.
    - Keep summaries, arguments, and vector sections under 200 words each.
    - Do NOT remove or alter important legal details.
    - Return only the merged JSON object.
    - Do NOT include any filenames, headers, markdown code blocks, or extra text.
    """

    merge_issue_prompt = """
    You are a legal JSON merging assistant.
    
    You will receive:
    1. Base JSON: structured legal case data.
    2. Custom JSON: additional extracted data.
    
    Merge them intelligently:
    - Preserve all keys from the base JSON.
    - For conflicts, keep the more complete, legally relevant, or contextually accurate value.
    - Add new fields from custom JSON if relevant.
    - Keep summaries, vectors, and key points under 200 words.
    - Flatten or compress overly long content if needed.
    - If final response increase the token limit you may drop some keys that aren't so important.
    - Drop the redundant fields and try to summarize them under one relevant key.
    - Output only valid, complete JSON — no extra text, no markdown, no explanations.
    - End with a closing brace '}' and do not leave any array or object unclosed.
    """

    print("Moving towards Custom json...")
    i_custom = custom_json_gpt(input_dir, output_dir_custom, summarized_dir, issues_dir_custom, deployment_name, client,
                               custom_prompt, summarization_prompt, 8192)
    if i_custom > 0:
        print("About to resolve custom issues")
        custom_issue_resolver(issues_dir_custom, output_dir_custom, summarized_dir, deployment_name, client,
                              custom_issue_prompt, summarization_prompt, 15000)
    print("Moving towards Base json...")
    i_base = base_json_gpt(input_dir, output_dir_base, summarized_dir, issues_dir_base, deployment_name, client,
                           base_prompt, summarization_prompt, 8192)
    if i_base > 0:
        print("About to resolve base issues")
        base_issue_resolver(issues_dir_base, output_dir_base, summarized_dir, deployment_name, client, base_issue_prompt,
                            summarization_prompt, 15000)
    print("Moving towards final json.")
    m_issue = merge_json_gpt(output_dir_base, output_dir_custom, final_json, issues_dir_base, issues_dir_custom,
                             merge_prompt, client, match_threshold)
    if m_issue > 0:
        print("Moving to resolve issues occurred in merging json files")
        merge_issue_resolver(issues_dir_base, issues_dir_custom, final_json, merge_issue_prompt, client, match_threshold)
