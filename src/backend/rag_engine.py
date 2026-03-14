# import os
# from openai import OpenAI
# from neo4j import GraphDatabase
# from dotenv import load_dotenv

# load_dotenv()

# class WuZhouGraphRAG:
#     def __init__(self):
#         """初始化 Qwen 与 Neo4j"""
#         api_key = os.getenv("QWEN_API_KEY")
#         self.client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
#         self.model_name = "qwen-plus"
        
#         uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
#         user = os.getenv("NEO4J_USER", "neo4j")
#         password = os.getenv("NEO4J_PASSWORD")
#         self.driver = GraphDatabase.driver(uri, auth=(user, password))

#     def _text_to_cypher(self, user_query):
#         """核心步骤 1：强化限定关系枚举值，消除幻觉关系"""
#         schema_prompt = """
#         你是一个精通 Neo4j 的图数据库专家。请将问题转化为 Cypher。
        
#         【允许使用的关系类型 (必须从中选择，严禁自造)】:
#         - 依附, 结盟, 政敌, 迫害, 任免, 担任, 参与
        
#         【Schema 属性】:
#         - 节点: Person (name)
#         - 关系属性: r.source_list, r.evidence_list
        
#         【转换逻辑参考】:
#         - 如果用户问“杀了”、“除掉”、“处死”，请使用关系类型：[:迫害]
#         - 如果用户问“提拔”、“降职”，请使用关系类型：[:任免]
#         - 如果用户问“反对”、“不合”，请使用关系类型：[:政敌]
        
#         【少样本示例】:
#         问题: 武则天在垂拱年间清除了哪些人？
#         答案: MATCH (p1:Person {name: '武则天'})-[r:迫害]->(p2:Person) RETURN p1.name AS source, type(r) AS relation, r.source_list AS sources, r.evidence_list AS evidences, p2.name AS target LIMIT 30
        
#         只输出纯粹的 Cypher 代码，不要包含 Markdown 标记或多余解释。
#         """
        
#         try:
#             response = self.client.chat.completions.create(
#                 model=self.model_name,
#                 messages=[
#                     {"role": "system", "content": schema_prompt},
#                     {"role": "user", "content": user_query}
#                 ],
#                 temperature=0.1
#             )
#             cypher = response.choices[0].message.content.strip()
#             # 清洗
#             cypher = cypher.replace("```cypher", "").replace("```", "").replace(";", "").strip()
            
#             # 如果 AI 还是写了 UNION 或者奇怪的组合，做简单的正则或字符串替换（可选）
#             # 这里我们信任 Prompt 的约束力
#             return cypher
#         except Exception as e:
#             print(f"❌ Text2Cypher 转换失败: {e}")
#             return ""

#     def _execute_cypher(self, cypher_query):
#         """核心步骤 2：执行 Cypher 并获取子图上下文"""
#         try:
#             with self.driver.session() as session:
#                 result = session.run(cypher_query)
#                 records = [record.data() for record in result]
#                 return records
#         except Exception as e:
#             print(f"Cypher 执行失败: {e}")
#             return None

#     def ask(self, user_query):
#         """核心步骤 3：基于召回的图谱上下文进行史学研判"""
#         # 1. 尝试实体对齐
#         aligned_info = self._pre_process_query(user_query)
        
#         # 2. 翻译为 Cypher (将对齐信息传给 Prompt)
#         # 如果对齐成功，强迫 AI 使用数据库里真实存在的名字
#         context_for_prompt = ""
#         if aligned_info:
#             context_for_prompt = f"\n【数据库对齐建议】: 已在数据库发现匹配实体 {aligned_info['label']}('{aligned_info['name']}')，请务必使用此名称查询。"

#         cypher = self._text_to_cypher(user_query, alignment_context=context_for_prompt)
#         if not cypher.upper().startswith("MATCH"):
#             return "❌ 系统未能成功解析该问题，请尝试换一种更具体的提问方式（如包含具体的历史人物或事件）。", cypher, None
            
#         # 3. 检索图谱数据
#         graph_context = self._execute_cypher(cypher)
#         if not graph_context:
#             return "⚠️ 图谱中未能检索到与该问题直接相关的历史事实。", cypher, None

#         # 4. 结合上下文让 Qwen 生成研判报告
#         # 此处保留了你原汁原味的细致 Prompt 要求
#         rag_prompt = f"""
#         你是一位严谨的唐代历史学家。请基于以下从《资治通鉴》及两唐书中提取的知识图谱数据，回答用户的问题。
        
#         【检索到的图谱事实】：
#         {graph_context}
        
#         【回答要求】：
#         1. 必须严格基于上述【检索到的图谱事实】进行回答，不要编造数据。
#         2. 关注边属性中的 `source_list`。如果某件事被多部史书同时记载（如 ["资治通鉴", "旧唐书"]），请指出这是“多源互证”的可靠史实；如果记载存在偏差，请客观呈现“史料冲突”。
#         3. 尽可能在回答中引用具体的 `evidence_list` (原文证据) 增加学术严谨性。
#         4. 使用流畅、专业的文史研判口吻。
#         """
        
#         response = self.client.chat.completions.create(
#             model=self.model_name,
#             messages=[
#                 {"role": "system", "content": rag_prompt},
#                 {"role": "user", "content": f"问题：{user_query}"}
#             ],
#             temperature=0.3
#         )
        
#         return response.choices[0].message.content, cypher, graph_context
    
#     def _align_entity(self, keyword):
#         """
#         实体对齐辅助函数：通过模糊匹配寻找数据库中最接近的实体名。
#         """
#         # 排除掉太短或无意义的词
#         if len(keyword) < 2:
#             return None
            
#         # 查询是否存在包含该关键词的节点 (优先找 Event，再找 Person)
#         query = """
#         MATCH (n) 
#         WHERE (n:Person OR n:Event OR n:Office) AND n.name CONTAINS $kw
#         RETURN n.name AS name, labels(n)[0] AS label
#         ORDER BY size(n.name) ASC  // 优先选名称长度接近的，防止误配
#         LIMIT 1
#         """
#         try:
#             with self.driver.session() as session:
#                 result = session.run(query, kw=keyword)
#                 record = result.single()
#                 if record:
#                     return {"name": record["name"], "label": record["label"]}
#         except Exception as e:
#             print(f"实体对齐检索失败: {e}")
#         return None

#     def _pre_process_query(self, user_query):
#         """
#         在生成 Cypher 前，提取关键词并尝试对齐。
#         """
#         # 简单提取用户问题中的专有名词（这里建议结合常用历史词汇，或直接交给 Qwen 提取）
#         # 我们这里先用一种“重写”策略：让 Qwen 帮我们把非标问题转为“对齐后的实体”
        
#         alignment_prompt = f"""
#         你是一个实体提取助手。请从用户问题中提取出最核心的一个历史人物、事件或官职名称。
#         用户问题："{user_query}"
#         只输出这一个名字，不要任何解释。
#         """
        
#         try:
#             res = self.client.chat.completions.create(
#                 model=self.model_name,
#                 messages=[{"role": "user", "content": alignment_prompt}],
#                 temperature=0
#             )
#             keyword = res.choices[0].message.content.strip()
            
#             # 尝试与数据库对齐
#             aligned = self._align_entity(keyword)
#             if aligned:
#                 print(f"🎯 实体对齐成功：'{keyword}' -> {aligned['label']}:'{aligned['name']}'")
#                 return aligned
#         except:
#             pass
#         return None
# import os
# import json
# from openai import OpenAI
# from neo4j import GraphDatabase
# from dotenv import load_dotenv

# load_dotenv()

# class WuZhouGraphRAG:
#     def __init__(self):
#         """初始化 Qwen 与 Neo4j"""
#         api_key = os.getenv("QWEN_API_KEY")
#         self.client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
#         self.model_name = "qwen-plus"
        
#         uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
#         user = os.getenv("NEO4J_USER", "neo4j")
#         password = os.getenv("NEO4J_PASSWORD")
#         self.driver = GraphDatabase.driver(uri, auth=(user, password))

#     def _align_entity(self, keyword):
#         """实体对齐：通过模糊匹配寻找数据库中最接近的实体名"""
#         if len(keyword) < 2: return None
#         query = """
#         MATCH (n) 
#         WHERE (n:Person OR n:Event OR n:Office) AND n.name CONTAINS $kw
#         RETURN n.name AS name, labels(n)[0] AS label
#         ORDER BY size(n.name) ASC LIMIT 1
#         """
#         try:
#             with self.driver.session() as session:
#                 result = session.run(query, kw=keyword)
#                 record = result.single()
#                 if record: return {"name": record["name"], "label": record["label"]}
#         except: pass
#         return None

#     def _pre_process_query(self, user_query):
#         """提取关键词并尝试对齐"""
#         prompt = f"请从问题中提取最核心的一个历史人物、事件或官职（如：废王立武、裴炎）。问题：{user_query}\n只输出名字。"
#         try:
#             res = self.client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": prompt}], temperature=0)
#             keyword = res.choices[0].message.content.strip()
#             return self._align_entity(keyword)
#         except: return None

#     def _text_to_cypher(self, user_query, alignment_context=""):
#         """将自然语言转为 Cypher，并注入对齐上下文"""
#         schema_prompt = f"""
#         你是一个精通 Neo4j 的历史学家。请将问题转化为 Cypher。
        
#         【Schema 规则】:
#         - 人物参与事件: (p:Person)-[r:参与]->(e:Event)
#         - 关系属性: r.source_list, r.evidence_list
        
#         【绝对禁止】: 严禁将 LIMIT 放在 RETURN 之前！{alignment_context}
        
#         【正确模版】:
#         MATCH (p1:Person {{name: '人物'环境}})-[r:关系]->(p2:Person) 
#         RETURN p1.name, type(r), r.source_list, r.evidence_list, p2.name LIMIT 30
#         """
        
#         try:
#             response = self.client.chat.completions.create(
#                 model=self.model_name,
#                 messages=[{"role": "system", "content": schema_prompt}, {"role": "user", "content": user_query}],
#                 temperature=0.1
#             )
#             cypher = response.choices[0].message.content.strip()
#             return cypher.replace("```cypher", "").replace("```", "").replace(";", "").strip()
#         except: return ""

#     def _execute_cypher(self, cypher_query):
#         """执行查询，增加对旧数据格式的兼容处理"""
#         try:
#             with self.driver.session() as session:
#                 result = session.run(cypher_query)
#                 # 兼容旧数据格式，如果 source_list 为空，尝试读取 sources
#                 records = []
#                 for record in result:
#                     data = record.data()
#                     # 这里的逻辑是为了防止之前提到的 JSON 报错，在 Python 端做一层缓冲
#                     records.append(data)
#                 return records
#         except Exception as e:
#             print(f"Cypher 执行失败: {e}")
#             return None

#     def ask(self, user_query):
#         # 1. 实体对齐预处理
#         aligned = self._pre_process_query(user_query)
#         context_for_prompt = ""
#         if aligned:
#             context_for_prompt = f"\n【重要对齐建议】: 库中匹配到实体 {aligned['label']}('{aligned['name']}')，请务必以此为准。"

#         # 2. 翻译 Cypher
#         cypher = self._text_to_cypher(user_query, alignment_context=context_for_prompt)
#         if not cypher.upper().startswith("MATCH"):
#             return "❌ 无法解析问题，请明确人物或事件。", cypher, None

#         # 3. 检索
#         graph_context = self._execute_cypher(cypher)
#         if not graph_context:
#             return "⚠️ 未能检索到相关史实。可能是该事件未被抽取或实体名称不匹配。", cypher, None

#         # 4. 研判
#         rag_prompt = f"你是一位严谨的历史学家。请基于事实研判并指出史料冲突：\n{graph_context}"
#         response = self.client.chat.completions.create(
#             model=self.model_name,
#             messages=[{"role": "system", "content": rag_prompt}, {"role": "user", "content": user_query}],
#             temperature=0.3
#         )
#         return response.choices[0].message.content, cypher, graph_context

import os
from openai import OpenAI
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class WuZhouGraphRAG:
    def __init__(self):
        """初始化 Qwen 与 Neo4j"""
        api_key = os.getenv("QWEN_API_KEY")
        self.client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model_name = "qwen-plus"
        
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def _text_to_cypher(self, user_query, alignment_context=""):
        """核心步骤 1：强化限定关系枚举值，并注入实体对齐上下文"""
        schema_prompt = f"""
        你是一个精通 Neo4j 的图数据库专家。请将问题转化为 Cypher。
        
        【允许使用的关系类型 (必须从中选择)】:
        - 依附, 结盟, 政敌, 迫害, 任免, 担任, 参与
        
        【Schema 属性】:
        - 节点标签: Person, Event, Office (均有 name 属性)
        - 关系属性: r.source_list, r.evidence_list
        
        【重要查询逻辑】:
        - 人物参与事件请使用: (p:Person)-[r:参与]->(e:Event)
        - 语法顺序必须为: MATCH -> WHERE -> RETURN -> LIMIT 30
        - 严禁将 LIMIT 放在 RETURN 之前。
        {alignment_context}

        【转换逻辑参考】:
        - “杀了/处死” -> [:迫害] | “提拔/降职” -> [:任免] | “反对/冲突” -> [:政敌]
        
        【少样本示例】:
        问题: 武则天在垂拱年间清除了哪些人？
        答案: MATCH (p1:Person {{name: '武则天'}})-[r:迫害]->(p2:Person) RETURN p1.name AS source, type(r) AS relation, r.source_list AS sources, r.evidence_list AS evidences, p2.name AS target LIMIT 30
        
        只输出纯粹的 Cypher 代码，不要包含 Markdown 标记或多余解释。
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": schema_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.1
            )
            cypher = response.choices[0].message.content.strip()
            # 基础清洗
            cypher = cypher.replace("```cypher", "").replace("```", "").replace(";", "").strip()
            return cypher
        except Exception as e:
            print(f"❌ Text2Cypher 转换失败: {e}")
            return ""

    def _execute_cypher(self, cypher_query):
        """核心步骤 2：执行 Cypher 并获取子图上下文"""
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query)
                records = [record.data() for record in result]
                return records
        except Exception as e:
            print(f"Cypher 执行失败: {e}")
            return None

    def ask(self, user_query):
        """核心步骤 3：基于召回的图谱上下文进行史学研判"""
        # 1. 尝试实体对齐
        aligned_info = self._pre_process_query(user_query)
        
        # 2. 准备对齐上下文
        context_for_prompt = ""
        if aligned_info:
            context_for_prompt = f"\n【数据库对齐建议】: 已在数据库发现匹配实体 {aligned_info['label']}('{aligned_info['name']}')，请务必使用此名称查询。"

        # 3. 翻译为 Cypher (传入对齐信息)
        cypher = self._text_to_cypher(user_query, alignment_context=context_for_prompt)
        if not cypher.upper().startswith("MATCH"):
            return "❌ 系统未能成功解析该问题，请尝试换一种更具体的提问方式。", cypher, None
            
        # 4. 检索图谱数据
        graph_context = self._execute_cypher(cypher)
        if not graph_context:
            return "⚠️ 图谱中未能检索到与该问题直接相关的历史事实。", cypher, None

        # 5. 生成研判报告
        rag_prompt = f"""
        你是一位严谨的唐代历史学家。请基于以下从《资治通鉴》及两唐书中提取的知识图谱数据，回答用户的问题。
        
        【检索到的图谱事实】：
        {graph_context}
        
        【回答要求】：
        1. 必须严格基于上述【检索到的图谱事实】进行回答，不要编造。
        2. 关注边属性中的 `source_list`，指出“多源互证”或“史料冲突”。
        3. 尽可能引用具体的 `evidence_list` (原文证据)。
        4. 使用流畅、专业的文史研判口吻。
        """
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": rag_prompt},
                {"role": "user", "content": f"问题：{user_query}"}
            ],
            temperature=0.3
        )
        
        return response.choices[0].message.content, cypher, graph_context
    
    def _align_entity(self, keyword):
        """实体对齐辅助函数：通过模糊匹配寻找数据库中最接近的实体名。"""
        if len(keyword) < 2:
            return None
        query = """
        MATCH (n) 
        WHERE (n:Person OR n:Event OR n:Office) AND n.name CONTAINS $kw
        RETURN n.name AS name, labels(n)[0] AS label
        ORDER BY size(n.name) ASC 
        LIMIT 1
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, kw=keyword)
                record = result.single()
                if record:
                    return {"name": record["name"], "label": record["label"]}
        except Exception as e:
            print(f"实体对齐检索失败: {e}")
        return None

    def _pre_process_query(self, user_query):
        """在生成 Cypher 前，提取关键词并尝试对齐。"""
        alignment_prompt = f"""
        你是一个实体提取助手。请从用户问题中提取出最核心的一个历史人物、事件或官职名称。
        用户问题："{user_query}"
        只输出这一个名字，不要任何解释。
        """
        try:
            res = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": alignment_prompt}],
                temperature=0
            )
            keyword = res.choices[0].message.content.strip()
            return self._align_entity(keyword)
        except:
            pass
        return None