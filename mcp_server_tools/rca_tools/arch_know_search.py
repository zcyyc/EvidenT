import pandas as pd
import numpy as np
from typing import Dict, List, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


class ArchitectureKnowledgeRetriever:
    """RISC-V架构知识语义检索工具"""

    def __init__(self, csv_path: str = None):
        """初始化检索器，可选择从CSV文件加载知识"""
        self.vectorizer = TfidfVectorizer(
            stop_words="english",  # 过滤英文停用词
            ngram_range=(1, 2),  # 同时考虑1-gram和2-gram
            max_features=10000,  # 限制特征数量，提高性能
        )
        self.knowledge_base = []
        self.embeddings = None
        self.index = None

        if csv_path:
            self.load_from_csv(csv_path)

    def load_from_csv(
        self, csv_path: str, id_col: str = None, content_col: str = "content"
    ):
        """从CSV文件加载知识条目"""
        df = pd.read_csv(csv_path)

        # 自动检测ID列（如果未指定）
        if not id_col:
            potential_id_cols = ["id", "ID", "title", "name"]
            id_col = next((col for col in potential_id_cols if col in df.columns), None)

        for idx, row in df.iterrows():
            knowledge_id = str(row[id_col]) if id_col else f"entry_{idx}"
            content = str(row[content_col])

            # 提取元数据（如果有）
            metadata = {
                col: row[col] for col in df.columns if col not in [id_col, content_col]
            }

            self.add_knowledge(knowledge_id, content, metadata)

    def add_knowledge(self, knowledge_id: str, content: str, metadata: Dict = None):
        """添加单条知识到知识库"""
        self.knowledge_base.append(
            {"id": knowledge_id, "content": content, "metadata": metadata or {}}
        )

    def build_index(self):
        """构建向量索引"""
        if not self.knowledge_base:
            raise ValueError("知识库为空，请先添加知识或从CSV加载")

        # 提取文本内容
        texts = [kb["content"] for kb in self.knowledge_base]

        # 生成TF-IDF向量
        self.embeddings = self.vectorizer.fit_transform(texts).toarray()

        # 构建近邻索引（使用余弦相似度）
        self.index = NearestNeighbors(
            n_neighbors=min(50, len(self.knowledge_base)),
            metric="cosine",
            algorithm="brute",
        )
        self.index.fit(self.embeddings)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索与查询语义匹配的架构知识"""
        if self.index is None:
            raise ValueError("索引未构建，请先调用build_index方法")

        # 将查询转换为向量
        query_vector = self.vectorizer.transform([query]).toarray()

        # 搜索相似向量
        distances, indices = self.index.kneighbors(query_vector, n_neighbors=top_k)
        distances = distances[0]
        indices = indices[0]

        # 整理结果
        results = []
        for i, idx in enumerate(indices):
            kb = self.knowledge_base[idx]
            results.append(
                {
                    "id": kb["id"],
                    "content": kb["content"],
                    "metadata": kb["metadata"],
                    "similarity": 1.0 - distances[i],  # 将余弦距离转换为相似度
                    "rank": i + 1,
                }
            )

        return results


# 测试代码
def architecture_knowledge_retriever(query: str):
    """演示RISC-V架构知识检索器的使用"""
    df1 = pd.read_csv(
        "/Users/zcy/Codes/PythonCodes/aiops_mcp/knowledge_base/risc_v_knowledge_base.csv"
    )
    retriever = ArchitectureKnowledgeRetriever()

    # 从DataFrame添加知识（替代直接从CSV加载）
    for index, row in df1.iterrows():
        retriever.add_knowledge(
            knowledge_id=str(index),
            content=row["content"],
            metadata={"title": row["title"]} if "title" in row else {},
        )

    # 构建索引
    retriever.build_index()
    print(f"已构建索引，知识库大小: {len(retriever.knowledge_base)} 条目")

    # 执行查询并显示结果
    print(f"\n\n===== 查询: {query} =====")
    results = retriever.search(query, top_k=1)

    return results
