import json
import os
from typing import List, Dict, Tuple
import re

class LogBlockRetriever:
    def __init__(self):
        # 日志块模式定义，假设日志块以时间戳和方括号开头
        self.block_pattern = re.compile(r'^\[\s*\d+s\]')
        self.id_pattern = re.compile(r'oe-RISCV-worker\d+')
    
    def retrieve_context(self, log_content: list, target_id: str) -> str:
        """检索指定ID的所有日志块及其上下文"""
        blocks = log_content
        all_contexts = []
        for content in blocks:
            meta_info = content.get('meta_info')
            if not meta_info:
                continue
            else:
                block_id = meta_info.get('log_block_id')
                if block_id == target_id:
                    all_contexts.append(content.get('parsed_entries'))

        return all_contexts

# 使用示例
def log_block_retriever(log_content, target_id: str):
    # 使用用户提供的日志内容
    retriever = LogBlockRetriever()
    context = retriever.retrieve_context(log_content, target_id)
    print("检索到的上下文日志:")
    print(context)