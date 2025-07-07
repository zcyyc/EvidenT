import pandas as pd
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class HistoricalCaseRetriever:
    def __init__(self):
        self.vectorizer = TfidfVectorizer()
        self.cases = []
        self.case_vectors = None
    
    def add_case(self, case_id: str, log_description: str, 
                 root_cause: str, solution: str, metadata: Dict = None):
        """添加历史案例到案例库"""
        self.cases.append({
            'id': case_id,
            'log_description': log_description,
            'root_cause': root_cause,
            'solution': solution,
            'metadata': metadata or {}
        })
    
    def load_from_csv(self, csv_path: str):
        """从CSV文件加载案例库"""
        df = pd.read_csv(csv_path)
        
        # 过滤空行
        df = df.dropna(how='all')
        
        for idx, row in df.iterrows():
            # 使用软件包名和错误阶段构建案例ID
            case_id = f"{row['software_package_name']}_{row['error_stage']}_{idx}"
            
            # 构建日志描述（合并软件包名、错误阶段和错误日志内容）
            log_description = f"Package: {row['software_package_name']}, Stage: {row['error_stage']}, Error: {row['error_log_content']}"
            
            # 使用预定义的错误类别作为根本原因
            root_cause = row['predefined_error_categories']
            
            # 为不同错误类别设置默认解决方案
            solution_map = {
                'missing_dependencies': '检查并安装缺失的依赖项，更新包索引后重试',
                'Bug': '检查代码逻辑，修复空指针引用或未定义方法调用',
                'refactoring_failure': '评估重构方案，考虑分阶段实施或保留兼容代码',
                'UI Bug': '检查UI组件渲染逻辑，确保资源正确加载'
            }
            
            # 根据错误类别获取解决方案，未知类别使用通用解决方案
            solution = solution_map.get(root_cause, '分析错误日志，确定根本原因后采取相应措施')
            
            # 添加元数据
            metadata = {
                'software_package_name': row['software_package_name'],
                'error_stage': row['error_stage'],
                'predefined_error_categories': root_cause
            }
            
            self.add_case(case_id, log_description, root_cause, solution, metadata)
    
    def build_index(self):
        """构建TF-IDF索引"""
        if not self.cases:
            raise ValueError("案例库为空，无法构建索引")
            
        # 提取日志描述
        log_descriptions = [case['log_description'] for case in self.cases]
        
        # 生成TF-IDF向量
        self.case_vectors = self.vectorizer.fit_transform(log_descriptions)
    
    def search(self, query_log: str, top_k: int = 5, category_filter: List[str] = None) -> List[Dict[str, Any]]:
        """搜索相似的历史案例，支持按错误类别筛选"""
        if self.case_vectors is None:
            raise ValueError("索引未构建，请先调用build_index方法")
            
        # 将查询日志转换为向量
        query_vector = self.vectorizer.transform([query_log])
        
        # 计算余弦相似度
        similarities = cosine_similarity(query_vector, self.case_vectors)[0]
        
        # 整理结果
        results = []
        for i, sim in enumerate(similarities):
            if i < len(self.cases):
                case = self.cases[i]
                
                # 如果设置了类别过滤，检查案例是否符合条件
                if category_filter and case['root_cause'] not in category_filter:
                    continue
                    
                results.append({
                    'id': case['id'],
                    'log_description': case['log_description'],
                    'root_cause': case['root_cause'],
                    'solution': case['solution'],
                    'similarity': sim,
                    'metadata': case['metadata']
                })
        
        # 按相似度排序
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]

# 使用示例
def demo_historical_case_retriever(query_log):
    retriever = HistoricalCaseRetriever()
    
    # 从CSV加载案例
    retriever.load_from_csv('D:/PythonCodes/aiops_mcp/knowledge_base/github_issues_res.csv')

    # 构建索引
    retriever.build_index()
       
    # 搜索所有类别的案例
    results = retriever.search(query_log, top_k=3)

    return results