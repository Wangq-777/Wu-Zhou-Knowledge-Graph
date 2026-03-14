# import os
# import networkx as nx
# from neo4j import GraphDatabase
# from dotenv import load_dotenv

# load_dotenv()

# class PowerInjector:
#     def __init__(self):
#         uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
#         user = os.getenv("NEO4J_USER", "neo4j")
#         password = os.getenv("NEO4J_PASSWORD")
#         self.driver = GraphDatabase.driver(uri, auth=(user, password))

#     def close(self):
#         self.driver.close()

#     def fetch_graph_topology(self):
#         """提取拓扑结构用于计算"""
#         query = """
#         MATCH (s:Person)-[r]->(t:Person)
#         WHERE s.name <> t.name 
#         RETURN s.name AS source, t.name AS target
#         """
#         with self.driver.session() as session:
#             return session.run(query).data()

#     def inject_scores(self):
#         print("📥 1. 正在提取网络拓扑...")
#         edges = self.fetch_graph_topology()
        
#         G = nx.DiGraph()
#         for edge in edges:
#             G.add_edge(edge['source'], edge['target'])

#         print("🧮 2. 正在进行 PageRank 权力推演...")
#         pagerank_scores = nx.pagerank(G, alpha=0.85)
        
#         # 将分数放大 100 倍（例如 0.038 变成 3.8），方便前端 ECharts 直接作为节点半径 (symbolSize) 使用
#         score_data = [
#             {"name": name, "score": round(score * 100, 4)} 
#             for name, score in pagerank_scores.items()
#         ]

#         print(f"🚀 3. 正在将 {len(score_data)} 个权力分数批量注入 Neo4j...")
#         # 使用 UNWIND 极其高效地进行批量 UPDATE
#         write_query = """
#         UNWIND $score_data AS row
#         MATCH (n:Person {name: row.name})
#         SET n.power_score = row.score
#         """
#         with self.driver.session() as session:
#             session.run(write_query, score_data=score_data)
            
#         print("\n🎉 注入完成！数据库中的所有 Person 节点现在都拥有了 `power_score` 属性。")

# if __name__ == "__main__":
#     injector = PowerInjector()
#     injector.inject_scores()
#     injector.close()

import os
import networkx as nx
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class PowerInjector:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def fetch_graph_topology(self):
        """提取拓扑结构用于计算（👑 已升级：极性过滤版）"""
        # 👑 核心修改：只提取“正面关系”构建权力网络，彻底隔绝“迫害/政敌”带来的虚假权力加成
        query = """
        MATCH (s:Person)-[r]->(t:Person)
        WHERE s.name <> t.name 
          AND type(r) IN ['依附', '结盟', '任免', '担任', '举荐', '支持', '辅佐']
        RETURN s.name AS source, t.name AS target
        """
        with self.driver.session() as session:
            return session.run(query).data()

    def inject_scores(self):
        print("📥 1. 正在提取【正面政治盟友】网络拓扑...")
        edges = self.fetch_graph_topology()
        
        G = nx.DiGraph()
        for edge in edges:
            G.add_edge(edge['source'], edge['target'])

        print("🧮 2. 正在进行 PageRank 核心权力推演...")
        # alpha=0.85 模拟了权力网络中 15% 的突发变数和 85% 的裙带关系继承
        pagerank_scores = nx.pagerank(G, alpha=0.85)
        
        # 将分数放大 100 倍，方便前端 ECharts 直接作为节点半径 (symbolSize) 使用
        score_data = [
            {"name": name, "score": round(score * 100, 4)} 
            for name, score in pagerank_scores.items()
        ]

        print(f"🚀 3. 正在将 {len(score_data)} 个精准权力分数批量注入 Neo4j...")
        # 使用 UNWIND 极其高效地进行批量 UPDATE
        write_query = """
        UNWIND $score_data AS row
        MATCH (n:Person {name: row.name})
        SET n.power_score = row.score
        """
        with self.driver.session() as session:
            session.run(write_query, score_data=score_data)
            
        print("\n🎉 注入完成！洗刷了虚假权力的【纯净版权力指数】已更新完毕。")

if __name__ == "__main__":
    injector = PowerInjector()
    injector.inject_scores()
    injector.close()