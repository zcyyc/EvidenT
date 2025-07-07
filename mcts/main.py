import os
import json
import numpy as np
import itertools
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import requests
from tqdm import tqdm
import time
from openai import OpenAI

from tools.arch_know_search import demo_architecture_knowledge_retriever
from tools.context_log_retrieve import demo_log_block_retriever
from tools.historical_case import demo_historical_case_retriever
from tools.spec_directive import demo_spec_file_parser

def call_llm(prompt: str) -> List[str]:
    """调用LLM API进行内容分析"""
    client = OpenAI(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-d034f0182d804ebb98fcce4bbd848ab0",
    )
    
    try:
        completion = client.chat.completions.create(
            extra_body={},
            model="qwen-turbo-0919",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {
                    "role": "user",
                    "content": f"{prompt}"
                }
            ]
        )
        
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error calling LLM API: {e}")
        return None

class MCTSNode:
    """MCTS树节点定义"""
    def __init__(
        self, 
        state: Dict, 
        parent: Optional['MCTSNode'] = None, 
        action: Optional[str] = None
    ):
        self.state = state  # 节点状态，包含日志、配置等信息
        self.parent = parent  # 父节点
        self.action = action  # 从父节点到当前节点的动作
        self.children = []  # 子节点列表
        self.visits = 0  # 访问次数
        self.value = 0.0  # 节点价值
        self.error_category = None  # 错误类别约束
    
    def add_child(self, child_state: Dict, action: str, error_category: str) -> 'MCTSNode':
        """添加子节点"""
        child = MCTSNode(child_state, self, action)
        child.error_category = error_category
        self.children.append(child)
        return child
    
    def update(self, value: float) -> None:
        """更新节点价值和访问次数"""
        self.visits += 1
        self.value = (self.value * (self.visits - 1) + value) / self.visits

class MCTS_RCA:
    """基于蒙特卡洛树搜索的根因分析框架"""
    def __init__(
        self, 
        knowledge_base: Dict, 
        toolset: Dict, 
        llm_model: str = "gpt-3.5-turbo",
        max_simulations: int = 20,
        exploration_weight: float = 1.41,
        error_categories: List[str] = None
    ):
        self.knowledge_base = knowledge_base  # 领域知识库
        self.toolset = toolset  # 工具集
        self.llm_model = llm_model
        self.max_simulations = max_simulations  # 最大模拟次数
        self.exploration_weight = exploration_weight  # 探索权重
        self.error_categories = error_categories or [
            "Dependency Error", "Configuration Error", "Compilation Error",
            "Test Failure", "Packaging Error", "Network Error"
        ]
    
    def load_knowledge_base(self, kb_path: str) -> None:
        """从文件加载知识库"""
        if os.path.exists(kb_path):
            with open(kb_path, 'r', encoding='utf-8') as f:
                self.knowledge_base = json.load(f)
        else:
            self.knowledge_base = {}
    
    def load_toolset(self, toolset_path: str) -> None:
        """从文件加载工具集"""
        if os.path.exists(toolset_path):
            with open(toolset_path, 'r', encoding='utf-8') as f:
                self.toolset = json.load(f)
        else:
            # 初始化默认工具集
            self.toolset = {
                "SpecFileParser": {
                    "description": "解析spec内容获取依赖信息",
                    "parameters": ["spec_content"],
                    "function": demo_spec_file_parser
                },
                "LogBlockRetriever": {
                    "description": "根据日志ID检索相关日志块",
                    "parameters": ["log_content", "log_block_id"],
                    "function": demo_log_block_retriever
                },
                "ArchitectureKnowledgeRetriever": {
                    "description": "检索RISC-V架构相关知识",
                    "parameters": ["query"],
                    "function": demo_architecture_knowledge_retriever
                },
                "HistoricalCaseRetriever": {
                    "description": "检索相似历史案例",
                    "parameters": ["error_message"],
                    "function": demo_historical_case_retriever
                }
            }
    
    def select_node(self, node: MCTSNode) -> MCTSNode:
        """使用UCT算法选择节点"""
        while node.children:
            best_child = None
            best_score = float('-inf')
            for child in node.children:
                try:
                    score = child.value + self.exploration_weight * \
                        child.error_category_confidence * np.sqrt(np.log(node.visits) / child.visits)
                except ZeroDivisionError:
                    score = float('-inf')
                if score > best_score:
                    best_score = score
                    best_child = child
            node = best_child
        return node

    def expand_node(self, node: MCTSNode, error_categories: List[str]) -> MCTSNode:
        """扩展节点，生成子节点"""
        # 获取当前状态的错误日志和上下文
        error_log = node.state.get("error_log", "")
        current_phase = node.state.get("build_phase", "unknown")
        
        # 生成可能的动作（工具调用或推理步骤）
        possible_actions = self._generate_possible_actions(error_log, current_phase)
        
        # 为每个动作生成子节点
        for action in possible_actions:
            # 确定动作对应的错误类别概率
            category_probs = self._predict_error_category_probs(error_log, action)
            for category, prob in category_probs.items():
                if category in error_categories:
                    child_state = {
                        "error_log": error_log,
                        "build_phase": current_phase,
                        "action_taken": action,
                        "inference_step": node.state.get("inference_step", 0) + 1,
                        "current_hypothesis": node.state.get("current_hypothesis", "") + f"\nAction: {action}"
                    }
                    child = node.add_child(child_state, action, category)
                    child.error_category_confidence = prob
                    return child  # 只扩展一个子节点，实际应用中可扩展多个
        return node
    
    def simulate(self, node: MCTSNode) -> float:
        """模拟从当前节点到终止状态的过程"""
        current_node = node
        for step in range(self.max_simulations):
            # 使用LLM进行推理
            prompt = self._construct_simulation_prompt(current_node.state)
            llm_response = call_llm(prompt)
            
            # 检查是否达到终止条件
            if self._is_termination_condition_met(llm_response):
                # 解析LLM返回的根因可信度
                confidence = self._parse_confidence(llm_response)
                return confidence
            
            # 更新当前节点状态
            current_node.state["llm_response"] = llm_response
            current_node.state["inference_step"] = step + 1
            
            # 生成下一个动作
            next_action = self._generate_next_action(llm_response, current_node.state)
            if not next_action:
                break
                
            # 预测错误类别
            error_category = self._predict_error_category(llm_response, next_action)
            if not error_category:
                error_category = "Unknown"
            
            # 创建新节点
            child_state = {
                "error_log": current_node.state.get("error_log", ""),
                "build_phase": current_node.state.get("build_phase", "unknown"),
                "action_taken": next_action,
                "inference_step": step + 1,
                "current_hypothesis": current_node.state.get("current_hypothesis", "") + f"\nAction: {next_action}\nLLM: {llm_response}"
            }
            current_node = current_node.add_child(child_state, next_action, error_category)
            current_node.error_category_confidence = 0.5  # 模拟初始置信度
        
        # 未达到终止条件时的默认返回
        return 0.3  # 较低的置信度表示未找到明确根因
    
    def backpropagate(self, node: MCTSNode, value: float) -> None:
        """反向传播更新节点价值"""
        while node:
            node.update(value)
            node = node.parent
    
    def search(self, initial_state: Dict) -> Tuple[str, float, Dict]:
        """执行MCTS搜索"""
        root = MCTSNode(initial_state)
        
        for i in tqdm(range(self.max_simulations), desc="MCTS Simulation"):
            # 选择节点
            selected_node = self.select_node(root)
            
            # 扩展节点
            expanded_node = self.expand_node(selected_node, self.error_categories)
            
            # 模拟
            simulation_result = self.simulate(expanded_node)
            
            # 反向传播
            self.backpropagate(expanded_node, simulation_result)
        
        # 选择最佳子节点作为结果
        best_child = max(
            root.children,
            key=lambda child: child.value * child.visits  # 结合价值和访问次数
        )
        
        # 解析最佳路径
        root_cause, confidence = self._parse_root_cause(best_child.state)
        reasoning_path = self._extract_reasoning_path(best_child)
        
        return root_cause, confidence, reasoning_path
    
    def _generate_possible_actions(self, error_log: str, build_phase: str) -> List[str]:
        """生成可能的动作（工具调用或推理步骤）"""
        # 实际应用中，这里会根据日志内容和构建阶段生成合理的动作
        # 示例动作生成
        actions = []
        
        # 检查是否有明显的依赖错误关键词
        if "missing" in error_log or "dependency" in error_log:
            actions.append("Check Spec File Dependencies")
        
        # 检查是否有编译错误关键词
        if "compile" in error_log or "error" in error_log:
            actions.append("Retrieve Compilation Logs")
        
        # 通用工具调用
        actions.extend([
            "Search Historical Cases",
            "Query Architecture Knowledge",
            "Check Environment Configuration"
        ])
        
        return list(set(actions))  # 去重
    
    def _construct_simulation_prompt(self, state: Dict) -> str:
        """构建模拟推理的LLM提示词"""
        error_log = state.get("error_log", "")
        action_taken = state.get("action_taken", "No action yet")
        hypothesis = state.get("current_hypothesis", "No hypothesis yet")
        phase = state.get("build_phase", "unknown phase")
        
        prompt = f"""
        你是RISC-V软件构建根因分析专家。
        构建阶段: {phase}
        错误日志: {error_log}
        已采取动作: {action_taken}
        当前假设: {hypothesis}
        
        请分析可能的根因，并决定下一步动作（从工具集中选择或提出推理步骤）。
        请以JSON格式返回，包含:
        {{
            "root_cause_hypothesis": "根因假设",
            "confidence": 0.0-1.0,
            "next_action": "下一步动作"
        }}
        """
        return prompt
    
    def _is_termination_condition_met(self, response: str) -> bool:
        """检查是否满足终止条件"""
        # 检查响应中是否包含明确的根因表述
        termination_keywords = ["root cause is", "the problem is", "reason is", "solution is"]
        return any(keyword in response.lower() for keyword in termination_keywords)
    
    def _parse_confidence(self, response: str) -> float:
        """从LLM响应中解析置信度"""
        # 简单示例：根据关键词估计置信度
        if "certain" in response.lower() or "definitely" in response.lower():
            return 0.9
        elif "likely" in response.lower() or "probable" in response.lower():
            return 0.7
        elif "possible" in response.lower() or "maybe" in response.lower():
            return 0.5
        else:
            return 0.3
    
    def _generate_next_action(self, response: str, state: Dict) -> Optional[str]:
        """从LLM响应中生成下一步动作"""
        # 简单示例：根据响应内容生成动作
        if "dependency" in response.lower() or "missing" in response.lower():
            return "Check Spec File BuildRequires"
        elif "compile" in response.lower() or "error" in response.lower():
            return "Retrieve Detailed Compilation Logs"
        elif "configuration" in response.lower() or "env" in response.lower():
            return "Check Build Environment Variables"
        else:
            return "Search Historical Similar Cases"
    
    def _predict_error_category(self, response: str, action: str) -> Optional[str]:
        """预测错误类别"""
        # 如果 response 是 list，则拼接为字符串
        if isinstance(response, list):
            response = "\n".join(str(item) for item in response)
        # 如果 action 是 list，也拼接为字符串
        if isinstance(action, list):
            action = "\n".join(str(item) for item in action)
        
        category_keywords = {
            "Dependency Error": ["dependency", "missing", "version", "conflict"],
            "Configuration Error": ["config", "spec", "env", "variable"],
            "Compilation Error": ["compile", "code", "syntax", "header"],
            "Test Failure": ["test", "fail", "assert", "integration"],
            "Packaging Error": ["package", "resource", "memory", "timeout"],
            "Network Error": ["network", "download", "connection", "fetch"]
        }
        
        response_lower = response.lower()
        action_lower = action.lower()
        
        for category, keywords in category_keywords.items():
            if any(keyword in response_lower or keyword in action_lower for keyword in keywords):
                return category
        
        return None

    def _predict_error_category_probs(self, error_log: str, action: str) -> Dict[str, float]:
        """
        预测错误类别概率分布。
        简单实现：只返回单一类别，概率为1.0。
        """
        # 如果 error_log 是 list，则拼接为字符串
        if isinstance(error_log, list):
            error_log = "\n".join(str(item) for item in error_log)
        # 如果 action 是 list，也拼接为字符串
        if isinstance(action, list):
            action = "\n".join(str(item) for item in action)
        category = self._predict_error_category(error_log, action)
        if category:
            return {category: 1.0}
        else:
            return {"Unknown": 1.0}
    
    def _parse_root_cause(self, state: Dict) -> Tuple[str, float]:
        """从最终状态解析根因和置信度"""
        hypothesis = state.get("current_hypothesis", "")
        response = state.get("llm_response", "")
        
        # 简单示例：从响应中提取根因
        root_cause = "Unknown root cause"
        confidence = 0.3
        
        # 模拟从响应中提取根因
        if "root cause is" in response.lower():
            root_cause = response.split("root cause is")[-1].split(".")[0].strip()
            confidence = 0.8
        elif "the problem is" in response.lower():
            root_cause = response.split("the problem is")[-1].split(".")[0].strip()
            confidence = 0.7
        elif "missing dependency" in response.lower():
            root_cause = "Missing dependency in spec file"
            confidence = 0.6
        
        return root_cause, confidence
    
    def _extract_reasoning_path(self, node: MCTSNode) -> List[Dict]:
        """提取推理路径"""
        path = []
        current = node
        
        while current.parent:
            path.append({
                "action": current.action,
                "error_category": current.error_category,
                "confidence": current.value,
                "visits": current.visits
            })
            current = current.parent
        
        path.reverse()
        return path

# 示例使用
def main():
    # 初始化MCTS-RCA
    mcts = MCTS_RCA(
        knowledge_base={},
        toolset={},
        max_simulations=10,  # 实际应用中可设置为20或更高
        exploration_weight=1.41
    )
    
    # 加载知识库和工具集（示例中使用空数据，实际需加载真实数据）
    mcts.load_knowledge_base("riscv_knowledge_base.json")
    mcts.load_toolset("riscv_toolset.json")
    
    # 示例初始状态（包含错误日志和构建阶段）
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_content = json.load(open(f'{base_dir}/Build_error_logs_data-master/aalto-xml.json', 'r', encoding='utf-8'))
    
    def filter_anomaly_context(log_content: list) -> list:
        """提取所有异常日志块的所有日志内容（log_content 字段）"""
        all_logs = []
        for block in log_content:
            if block.get('anomalous') is True:
                for entry in block.get('parsed_entries', []):
                    log_line = entry.get('log_content')
                    if log_line:
                        all_logs.append(log_line)
        return all_logs


    initial_state = {
        "error_log": filter_anomaly_context(log_content),
        "build_phase": "configure",
        "current_hypothesis": "Initial hypothesis: Possible dependency issue",
        "inference_step": 0
    }
    
    # 执行MCTS搜索
    root_cause, confidence, reasoning_path = mcts.search(initial_state)
    
    # 输出结果
    print("\n===== MCTS-RCA 根因分析结果 =====")
    print(f"根因: {root_cause}")
    print(f"置信度: {confidence:.2f}")
    print("\n推理路径:")
    for i, step in enumerate(reasoning_path):
        print(f"步骤 {i+1}:")
        print(f"  动作: {step['action']}")
        print(f"  错误类别: {step['error_category']}")
        print(f"  置信度: {step['confidence']:.2f}")
        print(f"  访问次数: {step['visits']}")
        print("-" * 40)

if __name__ == "__main__":
    main()