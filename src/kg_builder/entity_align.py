import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class EntityResolver:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

        # 👑 终极消歧字典：基于审计报告的实锤对齐
        self.synonym_dict = {
            # --- 武则天核心 (审计发现 22 个共同邻居) ---
            "武昭仪": "武则天",
            "武后": "武则天",
            "天后": "武则天",
            "太后": "武则天",
            "武曌": "武则天",
            "则天": "武则天",
            "武媚娘": "武则天",
            "大圣皇帝": "武则天",

            # --- 唐高宗核心 (审计发现 40 个共同邻居) ---
            "李治": "唐高宗",
            "高宗": "唐高宗",
            "天皇": "唐高宗",
            "天皇大帝": "唐高宗",
            "晋王": "唐高宗",

            # --- 韦后核心 (审计发现 58 个共同邻居) ---
            "韦氏": "韦后",
            "韦庶人": "韦后",
            "韦皇后": "韦后",

            # --- 李唐宗室系列 (审计发现 30+ 共同邻居) ---
            "中宗": "李显",
            "唐中宗": "李显",
            "中宗李显": "李显",
            "庐陵王": "李显",
            "庐陵王哲": "李显",
            "睿宗": "李旦",
            "唐睿宗": "李旦",
            "相王": "李旦",
            "豫王": "李旦",
            "皇嗣": "李旦",
            "皇嗣李旦": "李旦",
            "章怀太子": "李贤",
            "李贤": "李贤", # 占位确保规范
            "章怀太子李贤": "李贤",
            "太子贤": "李贤",
            "李隆基": "唐玄宗", # 此时期多称其本名或临淄王

            # --- 功臣、外戚与酷吏 ---
            "魏王": "武承嗣",
            "梁王": "武三思",
            "懿宗": "武懿宗",
            "裴中书": "裴炎",
            "裴子隆": "裴炎",
            "狄国老": "狄仁杰",
            "冯小宝": "薛怀义",
            "张六郎": "张昌宗",
            "五郎": "张易之",
            "李敬业": "徐敬业",
            "瑯邪王李冲": "李冲",
            "成王李千里": "李千里",
            "孝逸": "李孝逸"
        }

    def close(self):
        self.driver.close()

    def resolve_graph(self):
        print("🧬 正在启动 V2.0 政治网络重构引擎...")
        with self.driver.session() as session:
            for alias, standard in self.synonym_dict.items():
                if alias == standard: continue # 避免自循环
                session.execute_write(self._merge_nodes, alias, standard)
        print("\n🎉 全局实体对齐完成！武周政治骨架已加固。")

    @staticmethod
    def _merge_nodes(tx, alias_name, standard_name):
        # 1. 检查别名节点
        check_query = "MATCH (a:Person {name: $alias}) RETURN a"
        if not tx.run(check_query, alias=alias_name).single():
            return

        print(f"\n🔍 探测到分身: [{alias_name}] -> 归并至规范名 [{standard_name}]")

        # 2. 确保标准主节点存在并合并别名
        merge_std_query = """
        MERGE (main:Person {name: $standard})
        ON MATCH SET main.aliases = CASE
            WHEN NOT $alias IN coalesce(main.aliases, [])
            THEN coalesce(main.aliases, []) + [$alias]
            ELSE main.aliases END
        """
        tx.run(merge_std_query, standard=standard_name, alias=alias_name)

        # 3. 迁移【出边】
        out_edges = tx.run("""
            MATCH (a:Person {name: $alias})-[r]->(t) 
            RETURN type(r) AS rel_type, labels(t)[0] AS t_label, t.name AS target, properties(r) AS props
        """, alias=alias_name).data()
        
        for edge in out_edges:
            if edge['target'] == standard_name: continue
            create_out = f"""
            MATCH (main:Person {{name: $standard}})
            MATCH (t:`{edge['t_label']}` {{name: $target}})
            MERGE (main)-[r:`{edge['rel_type']}`]->(t)
            SET r += $props
            """
            tx.run(create_out, standard=standard_name, target=edge['target'], props=edge['props'])

        # 4. 迁移【入边】
        in_edges = tx.run("""
            MATCH (s)-[r]->(a:Person {name: $alias}) 
            RETURN type(r) AS rel_type, labels(s)[0] AS s_label, s.name AS source, properties(r) AS props
        """, alias=alias_name).data()
        
        for edge in in_edges:
            if edge['source'] == standard_name: continue
            create_in = f"""
            MATCH (main:Person {{name: $standard}})
            MATCH (s:`{edge['s_label']}` {{name: $source}})
            MERGE (s)-[r:`{edge['rel_type']}`]->(main)
            SET r += $props
            """
            tx.run(create_in, standard=standard_name, source=edge['source'], props=edge['props'])

        # 5. 彻底删除旧节点
        tx.run("MATCH (a:Person {name: $alias}) DETACH DELETE a", alias=alias_name)

if __name__ == "__main__":
    resolver = EntityResolver()
    resolver.resolve_graph()
    resolver.close()