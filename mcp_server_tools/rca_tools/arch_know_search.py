import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
import os
import yaml

class ArchitectureKnowledgeRetriever:
    """A simple retriever that indexes knowledge entries and supports semantic search."""

    def __init__(self, max_features: int = 20000):
        # Initialize vectorizer and empty KB
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=max_features,
            min_df=1,
        )
        self.knowledge_base = []
        self.embeddings = None
        self.index = None

    def add_knowledge(self, knowledge_id: str, content: str, metadata: dict = None):
        """Add a single entry to the knowledge base."""
        self.knowledge_base.append(
            {"id": knowledge_id, "content": content, "metadata": metadata or {}}
        )

    def build_index(self):
        """Build a TF-IDF index on the knowledge base."""
        if not self.knowledge_base:
            raise ValueError("Knowledge base is empty.")
        texts = [kb["content"] for kb in self.knowledge_base]
        self.embeddings = self.vectorizer.fit_transform(texts)
        self.index = NearestNeighbors(
            n_neighbors=min(50, len(self.knowledge_base)),
            metric="cosine",
            algorithm="brute",
        )
        self.index.fit(self.embeddings)

    def search(self, query: str, top_k: int = 5):
        """Search the knowledge base for the most relevant entries."""
        if self.index is None:
            raise ValueError("Index not built.")
        if not query.strip():
            return []

        query_vec = self.vectorizer.transform([query])
        distances, indices = self.index.kneighbors(query_vec, n_neighbors=top_k)
        distances, indices = distances[0], indices[0]

        results = []
        for rank, idx in enumerate(indices, start=1):
            kb = self.knowledge_base[idx]
            sim = 1.0 - float(distances[rank - 1])  # cosine distance -> similarity
            results.append(
                {
                    "id": kb["id"],
                    "title": kb["metadata"].get("title", ""),
                    "content": kb["content"],
                    "metadata": kb["metadata"],
                    "similarity": sim,
                    "rank": rank,
                }
            )
        return results


def architecture_knowledge_retriever(query: str):
    """
    architecture knowledge retriever
    :param query: query
    :return: search results
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base_dir, "config/paths.yaml"), "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    csv_path = os.path.join(base_dir, config["paths"]["arch_knowledge"])

    df1 = pd.read_csv(csv_path)
    retriever = ArchitectureKnowledgeRetriever()

    # Add entries from DataFrame
    for index, row in df1.iterrows():
        metadata = {}
        if "title" in row and pd.notna(row["title"]):
            metadata["title"] = str(row["title"]).strip()
        if "source" in row:
            metadata["source"] = row["source"]
        if "page_start" in row and "page_end" in row:
            metadata["pages"] = f"{row['page_start']}-{row['page_end']}"
        if "section" in row and pd.notna(row["section"]):
            metadata["section"] = row["section"]

        retriever.add_knowledge(
            knowledge_id=str(index),
            content=row["content"],
            metadata=metadata,
        )

    # Build index
    retriever.build_index()

    # Execute query
    results = retriever.search(query, top_k=1)

    # Pretty print top result
    for r in results:
        print(f"[{r['rank']}] {r['title']} (similarity={r['similarity']:.4f})")
        if r["metadata"].get("source"):
            print(f"Source: {r['metadata']['source']}, Pages: {r['metadata'].get('pages','')}")
        snippet = r["content"].strip().replace("\n", " ")
        if len(snippet) > 400:
            snippet = snippet[:400] + " ..."
        print(snippet)

    return results
