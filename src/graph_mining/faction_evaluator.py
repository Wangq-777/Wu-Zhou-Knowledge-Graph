import os
import networkx as nx
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class TrueGraphFactionEvaluator:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def generate_factions(self):
        # 👑 1. 极简“阵眼”定义 (Seed Nodes)
        # 绝对不穷举，只定义图谱的 5 个引力中心，剩下的全靠图算法自己算！
        anchors = {
            "武则天": 0, "太平公主": 0,  # 0: 皇权核心
            "唐中宗": 1, "李显": 1, "唐睿宗": 1, "李旦": 1, "唐玄宗": 1, # 1: 李唐宗室核心
            "武三思": 2, "武承嗣": 2,      # 2: 武周新贵核心
            "狄仁杰": 3, "张柬之": 3,      # 3: 朝堂重臣核心
            "来俊臣": 4, "张易之": 4       # 4: 酷吏近臣核心
        }

        with self.driver.session() as session:
            # 获取全库人物用于兜底
            all_nodes = [r["name"] for r in session.run("MATCH (n:Person) RETURN n.name AS name")]

            print("📥 正在剥离负面关系，提取纯粹的【政治盟友子图】...")
            # 👑 2. 图算法关键修正：只用正面关系建图，隔离仇敌！
            query = """
            MATCH (s:Person)-[r]->(t:Person)
            WHERE s.name <> t.name 
              // 坚决排除 '迫害', '政敌', '贬谪' 等负面关系
              AND type(r) IN ['依附', '结盟', '任免', '担任', '举荐', '支持', '辅佐']
            RETURN s.name AS source, t.name AS target
            """
            edges = session.run(query).data()
            
            G = nx.Graph()
            for edge in edges: 
                G.add_edge(edge['source'], edge['target'])

            print("🧮 正在运行纯粹的图拓扑社区发现 (Louvain)...")
            # 3. 运行基于模块度优化的社区发现算法
            communities = nx.community.louvain_communities(G)
            
            updates = []
            processed_nodes = set()

# 4. 基于图拓扑的阵营定性 (Label Propagation via Communities)
            for i, comm in enumerate(communities):
                comm_faction = 4 # 默认中立势力
                
                # 统计该社区内各个阵眼的权重
                faction_votes = {0:0, 1:0, 2:0, 3:0, 4:0}
                for node in comm:
                    if node in anchors:
                        faction_votes[anchors[node]] += 1
                
                best_faction = max(faction_votes, key=faction_votes.get)
                if faction_votes[best_faction] > 0:
                    comm_faction = best_faction

                # 👑 核心修复：将整个社区染色，但【绝对保护阵眼】！
                for node in comm:
                    if node in anchors:
                        # 阵眼的属性是绝对真理，雷打不动！
                        final_faction = anchors[node]
                    else:
                        # 只有非阵眼的普通小弟，才跟着社区大流走
                        final_faction = comm_faction
                        
                    updates.append({"name": node, "faction_id": final_faction})
                    processed_nodes.add(node)

            # 5. 处理孤立节点 (没有任何正面政治盟友的人)
            for node in all_nodes:
                if node not in processed_nodes:
                    # 如果他本身是阵眼（虽然概率极低），保留其身份，否则归为中立
                    faction_id = anchors.get(node, 4) 
                    updates.append({"name": node, "faction_id": faction_id})

            print(f"💾 正在将算法涌现出的 {len(updates)} 个人物派系写入 Neo4j 数据库...")
            session.run("UNWIND $batch AS record MATCH (n:Person {name: record.name}) SET n.faction_id = record.faction_id", batch=updates)
            
            print("🎉 纯图算法推演完成！拓扑网络已自动划清界限。")

if __name__ == "__main__":
    evaluator = TrueGraphFactionEvaluator()
    evaluator.generate_factions()
    evaluator.driver.close()