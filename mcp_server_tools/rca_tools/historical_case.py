import pandas as pd
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import yaml

class HistoricalCaseRetriever:
    def __init__(self):
        self.vectorizer = TfidfVectorizer()
        self.cases = []
        self.case_vectors = None

    def add_case(
        self,
        case_id: str,
        log_description: str,
        root_cause: str,
        solution: str,
        metadata: Dict = None,
    ):
        """Add historical cases to the case library"""
        self.cases.append(
            {
                "id": case_id,
                "log_description": log_description,
                "root_cause": root_cause,
                "solution": solution,
                "metadata": metadata or {},
            }
        )

    def load_from_csv(self, csv_path: str):
        """Load case library from CSV file"""
        df = pd.read_csv(csv_path)

        # filter blank lines
        df = df.dropna(how="all")

        for idx, row in df.iterrows():
            # build case ID using package name and error phase
            case_id = f"{row['software_package_name']}_{row['error_stage']}_{idx}"

            # build log description (combined package name, error phase, and error log content)
            log_description = f"Package: {row['software_package_name']}, Stage: {row['error_stage']}, Error: {row['error_log_content']}"

            # use predefined error categories as root causes
            root_cause = row["predefined_error_categories"]
            solution = "Analyze the error log, determine the root cause, and take appropriate measures",

            # add metadata
            metadata = {
                "software_package_name": row["software_package_name"],
                "error_stage": row["error_stage"],
                "predefined_error_categories": root_cause,
            }

            self.add_case(case_id, log_description, root_cause, solution, metadata)

    def build_index(self):
        """Building a TF-IDF index for historical cases"""
        if not self.cases:
            raise ValueError("Case library is empty, cannot build index")

        # extract log descriptions
        log_descriptions = [case["log_description"] for case in self.cases]

        # generate TF-IDF vectors
        self.case_vectors = self.vectorizer.fit_transform(log_descriptions)

    def search(
        self, query_log: str, top_k: int = 5, category_filter: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar historical cases and filter by error category"""
        if self.case_vectors is None:
            raise ValueError("Index is not built, please call build_index method first")

        # convert query log to vector
        query_vector = self.vectorizer.transform([query_log])

        # calculate cosine similarity
        similarities = cosine_similarity(query_vector, self.case_vectors)[0]

        # organize results
        results = []
        for i, sim in enumerate(similarities):
            if i < len(self.cases):
                case = self.cases[i]

                # If category filtering is set, check whether the case meets the conditions
                if category_filter and case["root_cause"] not in category_filter:
                    continue

                results.append(
                    {
                        "id": case["id"],
                        "log_description": case["log_description"],
                        "root_cause": case["root_cause"],
                        "solution": case["solution"],
                        "similarity": sim,
                        "metadata": case["metadata"],
                    }
                )

        # sort by similarity
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]


def historical_case_retriever(query_log: str):
    """
    Historical case retriever
    :param query_log: query log
    :return: historical cases
    """
    retriever = HistoricalCaseRetriever()
    with open("config/paths.yaml", "r") as file:
        config = yaml.safe_load(file)
    history_soluction = config["paths"]["history_soluction"]

    # load cases from CSV
    retriever.load_from_csv(history_soluction)

    # build index
    retriever.build_index()

    # search for similar historical cases
    results = retriever.search(query_log, top_k=3)

    return results
