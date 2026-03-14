import os
import networkx as nx
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class WuZhouGraphMiner:
    def __init__(self):
        """初始化数据库连接与算法引擎"""
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
        # 使用有向图保留权力流动方向，但在社区发现时会转换为无向图
        self.G = nx.DiGraph()

    def close(self):
        self.driver.close()

    def fetch_graph_from_neo4j(self):
        """从数据库拉取拓扑结构建立内存子图"""
        print("📥 正在从 Neo4j 提取权力网络拓扑...")
        # 提取人物之间具有实质政治意义的连线
        query = """
        MATCH (h:Person)-[r]->(t:Person)
        WHERE type(r) IN ['依附', '结盟', '政敌', '迫害', '举荐']
        RETURN h.name AS source, t.name AS target, type(r) AS relation
        """
        with self.driver.session() as session:
            result = session.run(query)
            for record in result:
                src = record["source"]
                tgt = record["target"]
                rel = record["relation"]
                
                # 针对不同性质的关系赋予权重（启发式规则）
                # 结盟、依附增加派系凝聚力，迫害/政敌属于排斥力（在某些复杂算法中可设为负权重，此处暂作正向连通性处理）
                weight = 2.0 if rel in ['结盟', '依附', '举荐'] else 1.0
                
                self.G.add_edge(src, tgt, weight=weight, type=rel)
                
        print(f"✅ 成功构建内存图：{self.G.number_of_nodes()} 个节点，{self.G.number_of_edges()} 条边。")

    def compute_power_centrality(self):
        """计算权力中心度 (特征向量中心性 + 介数中心性)"""
        print("🧮 正在计算历史人物权力得分 (Eigenvector & Betweenness)...")
        if len(self.G) == 0:
            return {}

        # 1. 特征向量中心性 (衡量处于权力核心圈的程度)
        try:
            eigen_centrality = nx.eigenvector_centrality_numpy(self.G, weight='weight')
        except Exception:
            # Fallback 方案
            eigen_centrality = nx.degree_centrality(self.G)

        # 2. 介数中心性 (衡量作为不同派系“政治掮客”的能力)
        betweenness = nx.betweenness_centrality(self.G, weight='weight')

        metrics = {}
        for node in self.G.nodes():
            metrics[node] = {
                "power_score": float(eigen_centrality.get(node, 0.0)),
                "broker_score": float(betweenness.get(node, 0.0))
            }
        return metrics

    def compute_factions(self):
        """执行 Louvain 算法进行政治派系自动聚类"""
        print("🔍 正在运行 Louvain 算法识别政治阵营...")
        if len(self.G) == 0:
            return {}
            
        # 社区发现通常在无向图上效果最好
        undirected_G = self.G.to_undirected()
        
        # 使用 networkx 内置的 Louvain 社区发现算法
        communities = nx.community.louvain_communities(undirected_G, weight='weight', seed=42)
        
        faction_map = {}
        for faction_id, community in enumerate(communities):
            for node in community:
                faction_map[node] = faction_id
                
        print(f"✅ 共识别出 {len(communities)} 个主要政治派系。")
        return faction_map

    def write_metrics_to_neo4j(self, metrics, faction_map):
        """将计算出的算法特征写回 Neo4j 节点属性"""
        print("💾 正在将算法特征写回数据库...")
        
        query = """
        UNWIND $data AS row
        MATCH (p:Person {name: row.name})
        SET p.power_score = row.power_score,
            p.broker_score = row.broker_score,
            p.faction_id = row.faction_id
        """
        
        # 构建批处理数据
        batch_data = []
        for node in self.G.nodes():
            batch_data.append({
                "name": node,
                "power_score": metrics.get(node, {}).get("power_score", 0.0),
                "broker_score": metrics.get(node, {}).get("broker_score", 0.0),
                "faction_id": faction_map.get(node, -1)
            })
            
        with self.driver.session() as session:
            session.run(query, data=batch_data)
            
        print("🎉 特征注入完成！现在节点具备了算法维度的数值属性。")

    def run_pipeline(self):
        self.fetch_graph_from_neo4j()
        metrics = self.compute_power_centrality()
        factions = self.compute_factions()
        
        if metrics and factions:
            self.write_metrics_to_neo4j(metrics, factions)
        else:
            print("⚠️ 图数据为空，请确认数据库中已完成知识抽取。")

# ================= 🚀 执行测试 =================
if __name__ == "__main__":
    miner = WuZhouGraphMiner()
    miner.run_pipeline()
    miner.close()