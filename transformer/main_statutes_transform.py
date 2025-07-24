from openai import AzureOpenAI
from dotenv import load_dotenv
from transformer.statutes_transformation import base_statute_json_gpt, base_statute_issue_resolver, custom_statutes_json_gpt, custom_statute_issue_resolver, merge_statutes_from_db

load_dotenv()


def transform_statute():
    # --- Azure OpenAI GPT-4o client setup ---
    client = AzureOpenAI(
        api_key="your api key",
        api_version="version",
        azure_endpoint="platform endpoint"
    )

    deployment_name = "name"

    base_statute_prompt = """
    You are a Legal Statutes Data Transformer AI.

    You will be given:
    1. A base schema in JSON format.
    2. A raw statute text.

    Your task is to:
    - Create a JSON object based on the provided base schema.
    - Fill each field using information extracted from the raw statute text using NLP.

    Guidelines:
    - Limit your JSON fields and content so that your total output does not exceed 8000 tokens.
    - For missing fields, write "N/A" to preserve schema completeness.
    - Avoid vague terms, list all entities explicitly.
    - Ensure all dates, names, references, and legal provisions are accurate.
    - Do NOT include Markdown formatting, no ```json or extra explanation.

    Final Output Format:
    pure JSON content only (no markdown block)
    """

    summarization_statute_prompt = "Summarize this statute clearly while preserving important names, enactment details, citations, and legal reasoning. Remove repetitive or procedural content."

    custom_statute_prompt = """
    You are a legal NLP assistant that converts raw statute text into structured JSON data.

    Instructions:
    - Analyze the text carefully using NLP.
    - DO NOT use deeply nested structures or complex JSON arrays.
    - Keep the schema shallow and flat where possible.
    - Represent sections, citations, and metadata using plain key-value pairs.
    - Do not use deeply recursive structures (e.g., list of objects inside objects unless absolutely needed).
    - Use only double quotes for keys and values.

    Output Rules:
    - ONLY return the pure JSON object (no markdown, no code blocks, no comments).
    - Ensure it is a valid and complete JSON.
    - Be concise and avoid overfitting structure to unclear text.

    You are allowed to skip unknown or ambiguous details. Simplicity and validity are more important.
    """

    custom_issue_prompt = """
    You are a legal NLP assistant that converts raw statute text into structured JSON data.

    Instructions:
    - Analyze the text carefully using NLP.
    - DO NOT use deeply nested structures or complex JSON arrays.
    - Keep the schema shallow and flat where possible.
    - Represent sections, citations, and metadata using plain key-value pairs.
    - Do not use deeply recursive structures (e.g., list of objects inside objects unless absolutely needed).
    - Use only double quotes for keys and values.
    - Try to keep your response within 8000 tokens. If it exceeds, filter only the most important and relevant information.

    Output Rules:
    - ONLY return the pure JSON object (no markdown, no code blocks, no comments).
    - Ensure it is a valid and complete JSON.
    """

    base_issue_prompt = """
    You are a Legal Statute Data Transformer AI.

    You will be given:
    1. A base schema in JSON format.
    2. A raw statute text.

    Your task is to:
    - Create a JSON object based on the provided base schema.
    - Fill each field using information extracted from the statute text using NLP.

    Guidelines:
    - Limit your JSON fields and content so that your total output does not exceed 8000 tokens.
    - For missing fields, write "N/A" to preserve schema completeness.
    - Avoid vague terms like “others” — list all entities explicitly.
    - Ensure all dates, names, references, and legal provisions are accurate.
    - Write summaries strictly concise and short.
    - In fields like statute type or citation, use complete and clear values.
    - Do NOT include Markdown formatting, no ```json or extra explanation.

    Final Output Format:
    Your final response must be a pure JSON (no markdown block)
    """

    merge_statute_prompt = """
    You are a smart JSON merger bot.

    You will be provided two JSON objects:
    1. A base JSON containing structured statute data.
    2. A custom JSON containing additional extracted information.

    Your job:
    - Intelligently merge the custom JSON into the base JSON.
    - Add the key, value pairs from custom json into base json which are not already part of base json by doing nlp on both json files. 
    - For overlapping fields, prefer the more contextually accurate or complete value.
    - Use your NLP understanding to resolve any semantic differences.
    - Do NOT remove or alter important legal details.
    - Make sure the final json has robust information.
    - Return only the merged JSON object.
    - Do NOT include any filenames, headers, markdown code blocks, or extra text.
    """

    print("Moving towards Custom json...")
    i_custom = custom_statutes_json_gpt(deployment_name, client,
                               custom_statute_prompt, summarization_statute_prompt, 8192)
    if i_custom > 0:
        print("About to resolve custom issues")
        custom_statute_issue_resolver(deployment_name, client,
                              custom_issue_prompt, summarization_statute_prompt, 15000)
    print("Moving towards Base json...")
    i_base = base_statute_json_gpt(deployment_name, client, base_statute_prompt, summarization_statute_prompt, 8192)
    if i_base > 0:
        print("About to resolve base issues")
        base_statute_issue_resolver(deployment_name, client, base_issue_prompt, summarization_statute_prompt, 15000)
    print("Moving towards final json.")
    m_issue = merge_statutes_from_db(merge_statute_prompt, client)


# transform_statute()
