import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class StaticGraphInjector:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def inject_static_knowledge(self):
        """👑 核心字典：将绝对客观的历史事实焊死在图谱中"""
        
        persons = [
            # 李唐皇室 (自带正统 Buff)
            {"name": "唐高宗", "aliases": ["李治", "天皇"], "bloodline": "李唐皇室"},
            {"name": "李显", "aliases": ["唐中宗", "庐陵王"], "bloodline": "李唐皇室"},
            {"name": "李旦", "aliases": ["唐睿宗", "相王"], "bloodline": "李唐皇室"},
            {"name": "太平公主", "aliases": ["镇国太平公主"], "bloodline": "李唐皇室"},
            {"name": "李贤", "aliases": ["章怀太子"], "bloodline": "李唐皇室"},
            
            # 武氏宗亲 (外戚集团)
            {"name": "武则天", "aliases": ["武曌", "太后", "则天大圣皇帝", "武昭仪"], "bloodline": "武氏宗亲"},
            {"name": "武承嗣", "aliases": ["魏王"], "bloodline": "武氏宗亲"},
            {"name": "武三思", "aliases": ["梁王"], "bloodline": "武氏宗亲"},
            
            # 核心外朝大臣 (初始设定)
            {"name": "长孙无忌", "aliases": ["赵国公", "太尉"], "bloodline": "关陇贵族"},
            {"name": "狄仁杰", "aliases": ["狄国老", "梁国公"], "bloodline": "外朝大臣"},
            {"name": "裴炎", "aliases": ["中书令", "字子隆"], "bloodline": "外朝大臣"}
        ]

        kinship_relations = [
            {"head": "唐高宗", "relation": "联姻", "tail": "武则天", "desc": "帝后"},
            {"head": "唐高宗", "relation": "血亲", "tail": "李显", "desc": "父子"},
            {"head": "武则天", "relation": "血亲", "tail": "李显", "desc": "母子"},
            {"head": "武则天", "relation": "血亲", "tail": "太平公主", "desc": "母女"},
            {"head": "武则天", "relation": "血亲", "tail": "武承嗣", "desc": "姑侄"}
        ]

        core_events = [
            {"name": "废王立武", "year": 655, "desc": "高宗废王皇后，立武则天为后，关陇集团受挫。"},
            {"name": "徐敬业起兵", "year": 684, "desc": "李敬业等人在扬州起兵反对武则天临朝称制。"},
            {"name": "神龙政变", "year": 705, "desc": "张柬之等人发动兵变，逼迫武则天退位，李唐复辟。"}
        ]

        with self.driver.session() as session:
            print("🏗️ 1. 正在浇筑人物血脉节点...")
            for p in persons:
                session.run("""
                    MERGE (n:Person {name: $name})
                    SET n.aliases = $aliases,
                        n.bloodline = $bloodline,
                        n.is_core_royalty = true
                """, name=p["name"], aliases=p["aliases"], bloodline=p["bloodline"])

            print("🧬 2. 正在绑定客观血亲与联姻拓扑...")
            for r in kinship_relations:
                session.run(f"""
                    MATCH (h:Person {{name: $head}})
                    MATCH (t:Person {{name: $tail}})
                    MERGE (h)-[rel:`{r['relation']}`]->(t)
                    SET rel.description = $desc, rel.is_static = true
                """, head=r["head"], tail=r["tail"], desc=r["desc"])

            print("🏛️ 3. 正在预埋历史超级事件枢纽...")
            for e in core_events:
                session.run("""
                    MERGE (ev:Event {name: $name})
                    SET ev.year_ad = $year,
                        ev.description = $desc,
                        ev.is_anchor_event = true
                """, name=e["name"], year=e["year"], desc=e["desc"])

        print("✅ 静态基建完成！V2.0 图谱的钢筋骨架已就绪。")

if __name__ == "__main__":
    injector = StaticGraphInjector()
    injector.inject_static_knowledge()
    injector.close()