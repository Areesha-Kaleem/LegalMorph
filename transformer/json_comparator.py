import json
from fuzzywuzzy import fuzz

def load_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def flatten_json(y, prefix=''):
    """Flatten nested JSON into key-value pairs with dotted paths"""
    out = {}
    if isinstance(y, dict):
        for k in y:
            out.update(flatten_json(y[k], f"{prefix}{k}."))
    elif isinstance(y, list):
        out[prefix[:-1]] = " | ".join(map(str, y))  # combine list into single string
    else:
        out[prefix[:-1]] = str(y)
    return out

def compare_json(file1, file2):
    json1 = flatten_json(load_json(file1))
    json2 = flatten_json(load_json(file2))

    keys1 = set(json1.keys())
    keys2 = set(json2.keys())

    common_keys = keys1 & keys2
    only_in_1 = keys1 - keys2
    only_in_2 = keys2 - keys1

    print("🔁 Comparing JSON files...\n")
    print(f"✅ Common keys: {len(common_keys)}")
    print(f"➕ Keys only in {file1}: {len(only_in_1)}")
    print(f"➕ Keys only in {file2}: {len(only_in_2)}")

    similarity_scores = []
    for key in common_keys:
        val1 = json1[key]
        val2 = json2[key]
        score = fuzz.token_set_ratio(val1, val2)
        similarity_scores.append(score)
        print(f"🔹 Field: {key}")
        print(f"   → Similarity: {score}%")
        if score < 75:
            print(f"   ⚠️ Values differ noticeably:\n      {val1}\n      {val2}")

    if similarity_scores:
        avg_score = sum(similarity_scores) / len(similarity_scores)
        print(f"\n🎯 Average value similarity: {avg_score:.2f}%")
    else:
        print("\n❗ No common keys to compare values.")

    return {
        "avg_similarity": avg_score if similarity_scores else 0,
        "common_keys": list(common_keys),
        "only_in_file1": list(only_in_1),
        "only_in_file2": list(only_in_2)
    }

# === USAGE ===
file1 = "D:\\LegalMorph\\json_folder\\the_state_vs_imran_ahmad_khan_niazi.json"
file2 = "D:\\LegalMorph\\json_folder\\the_state_vs_imran_ahmad_khan_niazi_reference_19_2023.json"

compare_json(file1, file2)
