import json

base_schema = {
    "case_title": "",
    "reference_no_or_id": "",
    "judgment_date": "",
    "first_hearing_date": "",
    "court": "",
    "bench_type": "",
    "judges": [],
    "appellant": [],
    "respondant": [],
    "accussed_details": [
        {
            "name": "",
            "age": "",
            "gender": "",
            "designation": "",
            "allegation": []
        }
    ],
    "lawyers": {
        "prosecution": [],
        "defense": []
    },
    "complaint_summary": "",
    "investigation_summary": "",
    "judgment_summary": "",
    "punishment": "",
    "Decision_or_verdict": "",
    "arguments": {},
    "assets": [],
    "statutes": [],
    "sections": [],
    "citations": [],
    "witnesses": [],
    "witness_statement": {},
    "appeal_number": "",
    "legal_categories": [],
    "key_issues": [],
    "maxims": {},
    "legal_terms": {},
    "words_and_phrases": {},
    "metadata": {},
    "source": "",
    "summary_vector_notes": ""
}

# Save to JSON file
with open("base_schema_template.json", "w", encoding="utf-8") as f:
    json.dump(base_schema, f, indent=4)

print("✅ Schema file 'base_schema_template.json' created successfully.")
