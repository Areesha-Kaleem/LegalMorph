import os
from collections import defaultdict
from pathlib import Path
from send2trash import send2trash
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def deduper():
    # Set the directory containing .txt files
    directory = Path("D:\LegalMorph\data")

    # Thresholds
    NAME_SIMILARITY_THRESHOLD = 0.85
    CONTENT_SIMILARITY_THRESHOLD = 0.75

    # Helper function to read file content
    def read_file_content(filepath):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    # Helper to get modification time
    def get_mod_time(filepath):
        return os.path.getmtime(filepath)

    # Group files by similar names (>=85% match)
    filepaths = list(directory.glob("*.txt"))
    groups = defaultdict(list)
    grouped = set()

    for i, file1 in enumerate(filepaths):
        name1 = file1.stem
        if file1 in grouped:
            continue
        groups[file1].append(file1)
        for file2 in filepaths[i+1:]:
            name2 = file2.stem
            ratio = SequenceMatcher(None, name1, name2).ratio()
            if ratio >= NAME_SIMILARITY_THRESHOLD:
                groups[file1].append(file2)
                grouped.add(file2)

    # Process each group for content similarity
    for group, files in groups.items():
        if len(files) < 2:
            continue

        print(f"\n🔍 Checking files with similar names: {[f.name for f in files]}")

        contents = [read_file_content(f) for f in files]
        mod_times = [get_mod_time(f) for f in files]

        # Compute pairwise content similarities using TF-IDF
        vectorizer = TfidfVectorizer().fit_transform(contents)
        similarity_matrix = cosine_similarity(vectorizer)

        to_keep = set()
        to_delete = set()

        for i in range(len(files)):
            for j in range(i+1, len(files)):
                sim = similarity_matrix[i][j]
                print(f"📄 Comparing: {files[i].name} ↔ {files[j].name} | Similarity: {sim:.2f}")

                if sim >= CONTENT_SIMILARITY_THRESHOLD:
                    if mod_times[i] <= mod_times[j]:
                        to_keep.add(files[i])
                        to_delete.add(files[j])
                    else:
                        to_keep.add(files[j])
                        to_delete.add(files[i])
                else:
                    to_keep.add(files[i])
                    to_keep.add(files[j])

        for f in to_delete:
            if f not in to_keep:
                print(f"🗑️ Sending to trash: {f.name}")
                send2trash(str(f))

        print(f"✅ Keeping files: {[f.name for f in to_keep]}")
