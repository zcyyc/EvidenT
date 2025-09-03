import pandas as pd
import os
import yaml
from typing import Dict, List, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


class ArchitectureKnowledgeRetriever:
    """RISC-V architecture knowledge semantic retrieval tool"""

    def __init__(self, csv_path: str = None):
        """Initialize the retriever, optionally loading knowledge from a CSV file"""
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=10000,
        )
        self.knowledge_base = []
        self.embeddings = None
        self.index = None

        if csv_path:
            self.load_from_csv(csv_path)

    def load_from_csv(self, csv_path: str, id_col: str = None, content_col: str = "content"):
        """
        load knowledge from csv file
        """
        df = pd.read_csv(csv_path)

        # auto-detect ID column if not specified
        if not id_col:
            potential_id_cols = ["id", "ID", "title", "name"]
            id_col = next((col for col in potential_id_cols if col in df.columns), None)

        for idx, row in df.iterrows():
            knowledge_id = str(row[id_col]) if id_col else f"entry_{idx}"
            content = str(row[content_col])

            # extract meta data
            metadata = {
                col: row[col] for col in df.columns if col not in [id_col, content_col]
            }

            self.add_knowledge(knowledge_id, content, metadata)

    def add_knowledge(self, knowledge_id: str, content: str, metadata: Dict = None):
        """
        Add a single piece of knowledge to the knowledge base
        :param knowledge_id: knowledge id
        :param content: knowledge content
        :param metadata: meta data
        """
        self.knowledge_base.append(
            {"id": knowledge_id, "content": content, "metadata": metadata or {}}
        )

    def build_index(self):
        """
        build index for knowledge base
        """
        if not self.knowledge_base:
            raise ValueError("The knowledge base is empty. Please add knowledge first or load it from CSV.")

        # extract content from knowledge base
        texts = [kb["content"] for kb in self.knowledge_base]

        # generate TF-IDF vectors
        self.embeddings = self.vectorizer.fit_transform(texts).toarray()

        # build nearest neighbors index (using cosine similarity)
        self.index = NearestNeighbors(
            n_neighbors=min(50, len(self.knowledge_base)),
            metric="cosine",
            algorithm="brute",
        )
        self.index.fit(self.embeddings)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        search knowledge base with query
        :param query: query
        :param top_k: top k
        :return: search results
        """
        if self.index is None:
            raise ValueError("The index is not built. Please call build_index first.")
        # transform query to vector
        query_vector = self.vectorizer.transform([query]).toarray()

        # search similar vectors
        distances, indices = self.index.kneighbors(query_vector, n_neighbors=top_k)
        distances = distances[0]
        indices = indices[0]

        # organize results
        results = []
        for i, idx in enumerate(indices):
            kb = self.knowledge_base[idx]
            results.append(
                {
                    "id": kb["id"],
                    "content": kb["content"],
                    "metadata": kb["metadata"],
                    "similarity": 1.0 - distances[i],
                    "rank": i + 1,
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
    csv_path = os.path.join(base_dir, config["paths"]["arch_knowledge_base"])

    df1 = pd.read_csv(csv_path)
    retriever = ArchitectureKnowledgeRetriever()

    for index, row in df1.iterrows():
        retriever.add_knowledge(
            knowledge_id=str(index),
            content=row["content"],
            metadata={"title": row["title"]} if "title" in row else {},
        )

    # build an index
    retriever.build_index()
    print(f"Index built, knowledge base size: {len(retriever.knowledge_base)} entries")

    print(f"\n\n===== Query: {query} =====")
    results = retriever.search(query, top_k=1)
    return results
