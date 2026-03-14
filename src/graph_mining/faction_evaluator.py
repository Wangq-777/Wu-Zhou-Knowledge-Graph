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
        # 👑 1. 阵眼定义完全对齐 V2.0 (Seed Nodes)
        # 0: 李唐帝室, 1: 武氏宗亲, 2: 关陇集团, 3: 武周党羽, 4: 反武势力, 5: 中立/未明
        BLOOD_LI = ["唐高宗", "唐中宗", "李显", "唐睿宗", "李旦", "唐玄宗", "太平公主", "相王旦", "韦后", "安乐公主", "李重俊", "李轮"]
        BLOOD_WU = ["武则天", "武三思", "武承嗣", "武攸暨", "武延秀", "魏王承嗣", "武氏诸王"]

        anchors = {
            "长孙无忌": 2, "褚遂良": 2, "韩瑗": 2, "柳奭": 2,
            "张易之": 3, "张昌宗": 3, "薛怀义": 3,
            "裴炎": 4, "徐敬业": 4, "骆宾王": 4, "张柬之": 4, "狄仁杰": 4, "桓彦范": 4, "敬晖": 4, "魏元忠": 4
        }
        for name in BLOOD_LI: anchors[name] = 0
        for name in BLOOD_WU: anchors[name] = 1

        with self.driver.session() as session:
            # 获取全库人物用于兜底
            all_nodes = [r["name"] for r in session.run("MATCH (n:Person) RETURN n.name AS name")]

            print("📥 正在剥离负面关系，提取纯粹的【政治盟友子图】...")
            # 👑 2. 图算法关键修正：剔除了数据库不存在的动词，仅保留核心极性
            query = """
            MATCH (s:Person)-[r]->(t:Person)
            WHERE s.name <> t.name 
              // 坚决排除 '迫害', '政敌' 等负面关系，只留客观存在的正面连线
              AND type(r) IN ['依附', '结盟']
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
                comm_faction = 5 # 👑 修正：默认中立势力改为 5
                
                # 统计该社区内各个阵眼的权重 (包含0-5)
                faction_votes = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0}
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
                    # 如果他本身是阵眼，保留其身份，否则归为中立(5)
                    faction_id = anchors.get(node, 5) 
                    updates.append({"name": node, "faction_id": faction_id})

            print(f"💾 正在将算法涌现出的 {len(updates)} 个人物派系写入 Neo4j 数据库...")
            session.run("UNWIND $batch AS record MATCH (n:Person {name: record.name}) SET n.faction_id = record.faction_id", batch=updates)
            
            print("🎉 V2.0 纯图算法推演完成！拓扑网络已自动划清界限。")

if __name__ == "__main__":
    evaluator = TrueGraphFactionEvaluator()
    evaluator.generate_factions()
    evaluator.driver.close()