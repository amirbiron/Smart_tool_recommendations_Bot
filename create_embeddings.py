#!/usr/bin/env python3
# create_embeddings.py
# Builds vector embeddings from tools.json and saves them to a shared disk.

import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Directory where the bot (web service) expects the index files.
# Override with INDEX_DIR env var if needed.
INDEX_DIR = os.getenv("INDEX_DIR", "/var/data")

TOOLS_FILE   = "tools.json"
INDEX_FILE   = os.path.join(INDEX_DIR, "tools.faiss")
MAPPING_FILE = os.path.join(INDEX_DIR, "index_to_name.json")


def create_and_save_embeddings(
    tools_file: str = TOOLS_FILE,
    index_file: str = INDEX_FILE,
    mapping_file: str = MAPPING_FILE,
) -> None:
    """Create sentence-transformer embeddings for each tool and store them in Faiss."""
    print("Loading tools database…")
    try:
        with open(tools_file, "r", encoding="utf-8") as f:
            tools = json.load(f)
    except FileNotFoundError:
        print(f"❌ {tools_file} not found. Place it next to this script.")
        return

    print("Preparing texts for embedding…")
    texts, names = [], []
    for tool in tools:
        combined = (
            f"שם: {tool.get('name', '')}. "
            f"קטגוריה: {tool.get('category', '')}. "
            f"תיאור: {tool.get('description', '')}"
        )
        texts.append(combined)
        names.append(tool["name"])

    print("Loading model all-MiniLM-L6-v2…")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("Encoding embeddings (this can take a while)…")
    embeddings = model.encode(texts, show_progress_bar=True).astype("float32")

    d = embeddings.shape[1]
    print(f"Creating Faiss index (dimension={d})…")
    index = faiss.IndexFlatL2(d)
    index.add(embeddings)

    os.makedirs(INDEX_DIR, exist_ok=True)
    print(f"Saving Faiss index → {index_file}")
    faiss.write_index(index, index_file)

    print(f"Saving mapping → {mapping_file}")
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump({i: n for i, n in enumerate(names)}, f, ensure_ascii=False, indent=2)

    print("\n✅ Embedding build complete!")
    print(f"Files written to {INDEX_DIR}")


if __name__ == "__main__":
    create_and_save_embeddings()
