import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

def create_and_save_embeddings(tools_file='tools.json', index_file='tools.faiss', mapping_file='index_to_name.json'):
    """
    Reads the tools database, creates vector embeddings for each tool's description,
    and saves them into a Faiss index and a mapping file.
    This script needs to be run only once, or whenever tools.json is updated.
    """
    print("Loading tools from tools.json...")
    try:
        with open(tools_file, 'r', encoding='utf-8') as f:
            tools = json.load(f)
    except FileNotFoundError:
        print(f"Error: {tools_file} not found. Please make sure it's in the same directory.")
        return

    # We will create embeddings based on a combination of important fields.
    # This gives a richer context than just the description.
    print("Preparing text for embedding...")
    texts_to_embed = []
    tool_names = []
    for tool in tools:
        # Combine name, category, and description for a richer embedding
        combined_text = f"שם: {tool.get('name', '')}. קטגוריה: {tool.get('category', '')}. תיאור: {tool.get('description', '')}"
        texts_to_embed.append(combined_text)
        tool_names.append(tool['name'])

    print("Loading sentence-transformer model (all-MiniLM-L6-v2)... This may take a moment.")
    # Using a small but powerful model for creating embeddings.
    model = SentenceTransformer('all-MiniLM-L6-v2')

    print("Creating embeddings for all tools... This may take a few minutes.")
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)

    # Faiss requires the embeddings to be in a specific format (float32)
    embeddings = np.array(embeddings).astype('float32')
    
    # The dimension of our vectors
    d = embeddings.shape[1]

    print(f"Creating a Faiss index with dimension {d}...")
    index = faiss.IndexFlatL2(d)
    index.add(embeddings)

    print(f"Saving Faiss index to {index_file}...")
    faiss.write_index(index, index_file)

    print(f"Creating and saving index-to-name mapping to {mapping_file}...")
    # This mapping helps us know which tool corresponds to which vector in the index
    index_to_name = {i: name for i, name in enumerate(tool_names)}
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(index_to_name, f, ensure_ascii=False, indent=2)

    print("\nPreparation complete!")
    print(f"'{index_file}' and '{mapping_file}' have been created successfully.")
    print("You can now run the main bot script.")

if __name__ == '__main__':
    create_and_save_embeddings()
