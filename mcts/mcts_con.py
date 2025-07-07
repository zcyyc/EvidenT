class RCAState:
    """根因分析状态，表示MCTS中的一个节点状态"""
    
    def __init__(self, 
                 x: str,          # 原始输入（如错误日志片段）
                 t: str,          # LLM的思考过程
                 a: str,          # 下一步行动序列
                 o: str,          # 行动反馈
                 error_category: str = None,  # 错误类别
                 parent=None,     # 父节点
                 is_terminal: bool = False):  # 是否为终止状态
        self.x = x
        self.t = t
        self.a = a
        self.o = o
        self.error_category = error_category
        self.parent = parent
        self.children = []
        self.visits = 0
        self.value = 0.0  # 节点价值估计
        self.is_terminal = is_terminal
        
    def __repr__(self):
        return f"RCAState(a={self.a[:20]}..., visits={self.visits}, value={self.value:.3f})"



class MCTSRCA:
    """基于蒙特卡洛树搜索的根因定位算法"""
    
    def __init__(self, 
                 llm_model,       # LLM模型接口
                 spec_parser: SpecFileParser,
                 log_retriever: ContextLogRetriever,
                 knowledge_retriever: ArchitectureKnowledgeRetriever,
                 case_retriever: HistoricalCaseRetriever,
                 exploration_weight: float = 1.0,
                 max_simulations: int = 20,
                 termination_token: str = "[success]"):
        self.llm_model = llm_model
        self.spec_parser = spec_parser
        self.log_retriever = log_retriever
        self.knowledge_retriever = knowledge_retriever
        self.case_retriever = case_retriever
        self.exploration_weight = exploration_weight
        self.max_simulations = max_simulations
        self.termination_token = termination_token
        self.root = None
        
    def initialize(self, error_log: str, software_info: Dict[str, str]) -> None:
        """初始化MCTS树，创建根节点"""
        # 提取日志ID
        log_id_match = re.search(r'LogID: (\w+)', error_log)
        log_id = log_id_match.group(1) if log_id_match else None
        
        # 检索上下文日志
        contextual_logs = []
        if log_id:
            contextual_logs = self.log_retriever.retrieve_contextual_logs(log_id)
        
        # 检索相关知识
        related_knowledge = self.knowledge_retriever.retrieve(error_log, top_k=3)
        
        # 检索相似案例
        related_cases = self.case_retriever.retrieve(error_log, top_k=3)
        
        # 解析spec文件
        spec_info = {}
        if 'spec_content' in software_info:
            spec_info = self.spec_parser.parse(software_info['spec_content'])
        
        # 构建初始查询
        initial_query = self._build_initial_query(
            error_log, contextual_logs, related_knowledge, related_cases, spec_info
        )
        
        # 获取LLM的初始响应
        response = self.llm_model.generate_response(initial_query)
        
        # 解析响应
        thinking, action, feedback, error_category = self._parse_llm_response(response)
        
        # 创建根节点
        self.root = RCAState(
            x=error_log,
            t=thinking,
            a=action,
            o=feedback,
            error_category=error_category,
            parent=None,
            is_terminal=self._check_termination(feedback)
        )
        
    def search(self) -> RCAState:
        """执行MCTS搜索，返回最佳根因分析结果"""
        if self.root is None:
            raise ValueError("MCTS树尚未初始化，请先调用initialize方法")
        
        for _ in range(self.max_simulations):
            leaf_node = self._select(self.root)
            
            if not leaf_node.is_terminal:
                leaf_node = self._expand(leaf_node)
            
            simulation_result = self._simulate(leaf_node)
            self._backpropagate(leaf_node, simulation_result)
            
            if leaf_node.is_terminal:
                break
                
        return self._get_best_node(self.root)
    
    def _select(self, node: RCAState) -> RCAState:
        """选择阶段：使用CC-UCT公式选择最优子节点"""
        while node.children:
            if not all(child.visits > 0 for child in node.children):
                unvisited = [child for child in node.children if child.visits == 0]
                return random.choice(unvisited)
            
            node = max(node.children, key=lambda child: self._cc_uct(child))
            
        return node
    
    def _expand(self, node: RCAState) -> RCAState:
        """扩展阶段：根据当前节点生成子节点"""
        # 检索相关知识和案例
        related_knowledge = self.knowledge_retriever.retrieve(node.a, top_k=3)
        related_cases = self.case_retriever.retrieve(node.a, top_k=3)
        
        # 构建查询
        query = f"基于以下思考和行动：思考[{node.t}]，行动[{node.a}]，"
        query += f"知识[{[k.get('title', '') for k in related_knowledge]}]，"
        query += f"案例[{[c.get('title', '') for c in related_cases]}]，"
        query += "请提供下一步分析和可能的原因"
        
        # 获取LLM响应
        new_response = self.llm_model.generate_response(query)
        
        # 解析响应
        thinking, action, feedback, error_category = self._parse_llm_response(new_response)
        
        # 创建新节点
        new_node = RCAState(
            x=node.x,
            t=thinking,
            a=action,
            o=feedback,
            error_category=error_category,
            parent=node,
            is_terminal=self._check_termination(feedback)
        )
        
        node.children.append(new_node)
        return new_node
    
    def _simulate(self, node: RCAState) -> float:
        """模拟阶段：从给定节点随机模拟直到终止状态"""
        current_node = node
        steps = 0
        
        while not current_node.is_terminal and steps < 10:
            # 检索相关知识和案例
            related_knowledge = self.knowledge_retriever.retrieve(current_node.a, top_k=3)
            related_cases = self.case_retriever.retrieve(current_node.a, top_k=3)
            
            # 构建模拟查询
            query = f"基于以下思考和行动：思考[{current_node.t}]，行动[{current_node.a}]，"
            query += f"知识[{[k.get('title', '') for k in related_knowledge]}]，"
            query += f"案例[{[c.get('title', '') for c in related_cases]}]，"
            query += "请提供下一步分析和可能的原因，给出简短回答"
            
            # 获取模拟响应
            mock_response = self.llm_model.generate_response(query)
            
            # 解析响应
            thinking, action, feedback, error_category = self._parse_llm_response(mock_response)
            
            # 创建模拟节点
            current_node = RCAState(
                x=current_node.x,
                t=thinking,
                a=action,
                o=feedback,
                error_category=error_category,
                parent=current_node,
                is_terminal=self._check_termination(feedback)
            )
            
            steps += 1
        
        return 1.0 if current_node.is_terminal else 0.5
    
    def _backpropagate(self, node: RCAState, result: float) -> None:
        """回溯阶段：更新从当前节点到根节点的路径上的所有节点值"""
        while node is not None:
            node.visits += 1
            node.value += (result - node.value) / node.visits
            node = node.parent
    
    def _cc_uct(self, node: RCAState) -> float:
        """分类约束的UCT公式计算节点价值"""
        if node.visits == 0:
            return float('inf')
        
        p_s = self._calculate_confidence_weight(node)
        exploration = math.sqrt(math.log(node.parent.visits) / node.visits)
        
        return node.value + p_s * self.exploration_weight * exploration
    
    def _calculate_confidence_weight(self, node: RCAState) -> float:
        """计算基于错误类别的置信权重P(s)"""
        error_weights = {
            "dependency": 1.2,
            "configuration": 1.0,
            "runtime": 0.8,
            None: 0.5
        }
        
        return error_weights.get(node.error_category, 0.5)
    
    def _build_initial_query(self, error_log: str, contextual_logs: List[Dict], 
                            knowledge_items: List[Dict], cases: List[Dict], 
                            spec_info: Dict) -> str:
        """构建初始查询"""
        query = f"错误日志: {error_log}\n\n"
        
        if contextual_logs:
            query += "上下文日志:\n"
            for log in contextual_logs:
                query += f"- [{log['timestamp']}] {log['message']}\n"
            query += "\n"
        
        if knowledge_items:
            query += "相关架构知识:\n"
            for i, item in enumerate(knowledge_items, 1):
                query += f"{i}. {item['title']}: {item['content'][:100]}...\n"
            query += "\n"
        
        if cases:
            query += "相似历史案例:\n"
            for i, case in enumerate(cases, 1):
                query += f"{i}. {case['title']}: {case['description'][:100]}...\n"
                query += f"   根本原因: {case['root_cause']}\n"
            query += "\n"
        
        if spec_info:
            query += "软件配置信息:\n"
            query += f"名称: {spec_info.get('name')}\n"
            query += f"版本: {spec_info.get('version')}\n"
            query += f"依赖: {', '.join(spec_info.get('requires_all', []))}\n\n"
        
        query += "请分析可能的根本原因，并提供下一步排查建议。"
        return query
    
    def _parse_llm_response(self, response: str) -> Tuple[str, str, str, str]:
        """解析LLM的响应，提取思考、行动、反馈和错误类别"""
        thinking = response.split("行动建议:")[0].strip()
        
        if "行动建议:" in response and "预期反馈:" in response:
            action_part = response.split("行动建议:")[1].split("预期反馈:")[0].strip()
            feedback_part = response.split("预期反馈:")[1].strip()
        else:
            action_part = response
            feedback_part = "执行中..."
        
        error_category = None
        if "依赖" in response or "版本不兼容" in response:
            error_category = "dependency"
        elif "配置" in response or "设置" in response:
            error_category = "configuration"
        elif "运行时" in response or "崩溃" in response:
            error_category = "runtime"
            
        return thinking, action_part, feedback_part, error_category
    
    def _check_termination(self, feedback: str) -> bool:
        """检查是否满足终止条件"""
        return self.termination_token in feedback
    
    def _get_best_node(self, node: RCAState) -> RCAState:
        """获取价值最高的叶子节点"""
        if not node.children:
            return node
        
        return max(node.children, key=lambda child: child.value)

