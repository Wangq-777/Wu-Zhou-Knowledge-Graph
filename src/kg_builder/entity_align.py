import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 加载环境变量 (确保 .env 中有 NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
load_dotenv()

class EntityResolver:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

        # 👑 核心消歧字典：将 左侧的“分身/别名” 合并入 右侧的“标准主节点”
        self.synonym_dict = {
            # --- 本次通过结构排查发现的实锤别名 ---
            "李隆基": "唐玄宗",
            "武昭仪": "武则天",
            "懿宗": "武懿宗",          # 修复大模型漏字错误
            "上官昭容": "上官婉儿",
            "韦庶人": "韦后",
            "中宗": "唐中宗",
            "中宗李显": "唐中宗",
            "李显": "唐中宗",
            "睿宗": "李旦",
            "相王": "李旦",
            "豫王": "李旦",
            "天皇": "唐高宗",
            "李治": "唐高宗",
            
            # --- 常见尊号与官职代称 ---
            "天皇": "唐高宗",
            "大帝": "唐高宗", # 有时史书简称天皇大帝为大帝
            "天皇大帝": "唐高宗",
            "晋王": "唐高宗", # 登基前、立太子前的封号
            "李治": "唐高宗",
            "高宗": "唐高宗",
            "高宗大帝": "唐高宗",
            "武后": "武则天",
            "天后": "武则天",
            "太后": "武则天",
            "则天": "武则天",
            "武媚娘": "武则天",
            "魏王": "武承嗣",
            "梁王": "武三思",
            "裴中书": "裴炎",
            "裴子隆": "裴炎",
            "狄国老": "狄仁杰",
            "冯小宝": "薛怀义",
            "张六郎": "张昌宗",
            "五郎": "张易之"
        }

    def close(self):
        self.driver.close()

    def resolve_graph(self):
        print("🧬 开始进行图谱实体对齐与网络重构...")
        with self.driver.session() as session:
            for alias, standard in self.synonym_dict.items():
                # 遍历字典，执行合并逻辑
                session.execute_write(self._merge_nodes, alias, standard)
        print("\n🎉 全局实体对齐完成！权力网络已净化，冗余节点已销毁。")

    @staticmethod
    def _merge_nodes(tx, alias_name, standard_name):
        """核心重构逻辑：迁移出边、迁移入边、合并属性、销毁分身"""
        
        # 1. 检查别名节点是否存在 (不存在则跳过，节省资源)
        check_query = "MATCH (a:Person {name: $alias}) RETURN a"
        if not tx.run(check_query, alias=alias_name).single():
            return

        print(f"\n🔍 发现待合并实体: [{alias_name}] -> 准备接入主节点 [{standard_name}]")

        # 2. 确保标准主节点存在，并将别名记录到主节点的 aliases 列表中
        merge_std_query = """
        MERGE (main:Person {name: $standard})
        ON CREATE SET main.aliases = [$alias], main.power_score = 0.1
        ON MATCH SET main.aliases = CASE
            WHEN NOT $alias IN coalesce(main.aliases, [])
            THEN coalesce(main.aliases, []) + [$alias]
            ELSE main.aliases END
        """
        tx.run(merge_std_query, standard=standard_name, alias=alias_name)

        # 3. 迁移【出边】 (Alias 发出的关系 -> Target)
        out_edges = tx.run("""
            MATCH (a:Person {name: $alias})-[r]->(t) 
            RETURN type(r) AS rel_type, t.name AS target, properties(r) AS props
        """, alias=alias_name).data()
        
        out_count = 0
        for edge in out_edges:
            if edge['target'] == standard_name:
                continue # 防止自己连自己的闭环错误
                
            # 使用 Python 字符串格式化注入关系类型 (因为 Cypher 不支持参数化关系类型)
            create_out = f"""
            MATCH (main:Person {{name: $standard}})
            MATCH (t:Person {{name: $target}})
            MERGE (main)-[r:`{edge['rel_type']}`]->(t)
            SET r += $props
            """
            tx.run(create_out, standard=standard_name, target=edge['target'], props=edge['props'])
            out_count += 1

        # 4. 迁移【入边】 (Source 发出的关系 -> Alias)
        in_edges = tx.run("""
            MATCH (s)-[r]->(a:Person {name: $alias}) 
            RETURN type(r) AS rel_type, s.name AS source, properties(r) AS props
        """, alias=alias_name).data()
        
        in_count = 0
        for edge in in_edges:
            if edge['source'] == standard_name:
                continue # 防止自己连自己的闭环错误
                
            create_in = f"""
            MATCH (main:Person {{name: $standard}})
            MATCH (s:Person {{name: $source}})
            MERGE (s)-[r:`{edge['rel_type']}`]->(main)
            SET r += $props
            """
            tx.run(create_in, standard=standard_name, source=edge['source'], props=edge['props'])
            in_count += 1

        # 5. 卸磨杀驴：断开并彻底删除旧的别名节点
        delete_query = "MATCH (a:Person {name: $alias}) DETACH DELETE a"
        tx.run(delete_query, alias=alias_name)
        
        print(f"   ✅ 转移完毕: 迁出 {out_count} 条关系，迁入 {in_count} 条关系。冗余节点 [{alias_name}] 已销毁。")

if __name__ == "__main__":
    resolver = EntityResolver()
    resolver.resolve_graph()
    resolver.close()