# Step 1: Install necessary libraries (Run this in a separate, first cell)
# !pip install sentence-transformers faiss-cpu

# Step 2: Import libraries
import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Step 3: Define file paths
TOOLS_JSON_PATH = 'tools.json'
FAISS_INDEX_PATH = 'tools.faiss'
MAPPING_PATH = 'index_to_name.json'

def create_and_save_embeddings():
    """
    Reads the tools database, creates vector embeddings, and saves them.
    This script is run as a one-off job in Google Colab.
    """
    print("Starting embedding creation process...")
    
    if not os.path.exists(TOOLS_JSON_PATH):
        print(f"Error: {TOOLS_JSON_PATH} not found.")
        print("Please upload your 'tools.json' file to the Colab session using the file browser on the left.")
        return

    try:
        with open(TOOLS_JSON_PATH, 'r', encoding='utf-8') as f:
            tools = json.load(f)
        print(f"Successfully loaded {len(tools)} tools from {TOOLS_JSON_PATH}.")
    except Exception as e:
        print(f"Error reading or parsing {TOOLS_JSON_PATH}: {e}")
        return

    texts_to_embed = [f"שם: {t.get('name', '')}. קטגוריה: {t.get('category', '')}. תיאור: {t.get('description', '')}" for t in tools]
    tool_names = [t['name'] for t in tools]

    print("Loading sentence-transformer model (all-MiniLM-L6-v2)... This may take a moment.")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    print(f"Creating embeddings for {len(texts_to_embed)} tools... This is the longest step.")
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)
    embeddings = np.array(embeddings).astype('float32')
    
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    print(f"Saving Faiss index to {FAISS_INDEX_PATH}...")
    faiss.write_index(index, FAISS_INDEX_PATH)

    print(f"Saving index-to-name mapping to {MAPPING_PATH}...")
    index_to_name = {i: name for i, name in enumerate(tool_names)}
    with open(MAPPING_PATH, 'w', encoding='utf-8') as f:
        json.dump(index_to_name, f, ensure_ascii=False, indent=2)

    print("\n✅ Preparation complete!")
    print(f"'{FAISS_INDEX_PATH}' and '{MAPPING_PATH}' have been created successfully.")
    print("You can now download these two files from the file browser on the left.")

# Step 4: Run the function
create_and_save_embeddings()
