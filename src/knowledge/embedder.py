# ==========================================
# 1. LOCAL SENTENCE EMBEDDINGS
# ==========================================

# Small English model (384 numbers per text); runs on CPU, no API key.
# The first run downloads it (~90 MB) from Hugging Face and caches it.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None


def embed_texts(texts):
    """
    Turn each text into a normalized embedding (a list of floats), so the
    dot product of two embeddings is their cosine similarity.
    """

    global _model
    if _model is None:
        # Imported here so the rest of the pipeline and tests load without torch
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)

    return _model.encode(list(texts), normalize_embeddings=True).tolist()
