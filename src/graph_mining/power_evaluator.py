import os
import networkx as nx
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class PowerEvaluator:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def fetch_graph_topology(self):
        """从 Neo4j 拉取核心网络拓扑，不包含任何多余属性，速度极快"""
        query = """
        MATCH (s:Person)-[r]->(t:Person)
        // 过滤掉自环（自己连自己）
        WHERE s.name <> t.name 
        RETURN s.name AS source, t.name AS target, type(r) AS rel_type
        """
        with self.driver.session() as session:
            result = session.run(query).data()
        return result

    def calculate_and_review(self):
        print("📥 正在从 Neo4j 提取网络拓扑...")
        edges = self.fetch_graph_topology()
        print(f"✅ 提取成功，共发现 {len(edges)} 条政治交互关系。\n")

        # 1. 构建有向图
        G = nx.DiGraph()
        
        for edge in edges:
            source = edge['source']
            target = edge['target']
            rel_type = edge['rel_type']
            
            # 💡 进阶逻辑预留：如果你想让“依附”带来的权力权重大于“政敌”，可以在这里设置 weight
            # 目前我们采用无差别权重 (weight=1.0) 进行基础演算
            G.add_edge(source, target, weight=1.0)

        print("🧮 正在运行 PageRank 权力推演算法...\n")
        # 2. 计算 PageRank 
        # alpha=0.85 是 Google 经典的阻尼系数
        pagerank_scores = nx.pagerank(G, alpha=0.85, weight='weight')

        # 3. 排序并格式化输出（只看不写）
        sorted_scores = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)

        print("="*40)
        print("👑 纯算法推演：武周核心权力排行榜 (Top 30)")
        print("="*40)
        print(f"{'排名':<5} | {'历史人物':<10} | {'权力指数 (PR)':<15}")
        print("-" * 40)
        
        for i, (name, score) in enumerate(sorted_scores[:100], 1):
            # 将分数放大 100 倍以便于阅读
            readable_score = round(score * 100, 4)
            print(f"Top {i:<3} | {name:<10} | {readable_score}")
            
        print("="*40)
        print("\n💡 审查指南：")
        print("1. 武则天是否断崖式领先？")
        print("2. 狄仁杰、裴炎、张柬之等名相是否位列前茅？")
        print("3. 来俊臣等酷吏的分数是否异常偏高（因为他们撕咬了太多朝臣）？")
        print("⚠️ 确认结果符合史实后，我们再进行落盘操作。")

if __name__ == "__main__":
    evaluator = PowerEvaluator()
    evaluator.calculate_and_review()
    evaluator.close()