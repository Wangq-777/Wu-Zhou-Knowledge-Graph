import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class AutoEntityMerger:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD"))
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def merge_by_alias_overlap(self):
        """
        核心逻辑：如果 A 的名字出现在 B 的 aliases 列表里，则合并。
        """
        query = """
        MATCH (a:Person), (b:Person)
        WHERE id(a) < id(b) 
          AND (a.name IN b.aliases OR b.name IN a.aliases)
        WITH a, b
        ORDER BY size(a.name) DESC // 保留名字更全的那个
        MATCH (old:Person {name: b.name})
        MATCH (target:Person {name: a.name})
        // 转移关系并删除旧节点
        CALL apoc.refactor.mergeNodes([target, old], {properties: "combine", mergeRels: true})
        YIELD node
        RETURN count(node) as merged_count
        """
        # 注意：这需要 Neo4j 安装 APOC 插件。如果没有 APOC，我们可以用原生 Cypher 替换。
        with self.driver.session() as session:
            result = session.run(query)
            print(f"✅ 基于别名库自动合并了 {result.single()['merged_count']} 组节点")

    def merge_by_royal_titles(self):
        """
        专门针对皇帝的“代词”进行暴力缝合。
        """
        royal_tasks = [
            ("唐高宗", ["李治", "天皇", "上", "皇上"]),
            ("武则天", ["太后", "圣神皇帝", "则天"]),
            ("中宗", ["李显", "庐陵王"])
        ]
        with self.driver.session() as session:
            for target, aliases in royal_tasks:
                session.run("""
                MATCH (t:Person {name: $target})
                MATCH (a:Person) WHERE a.name IN $aliases
                WITH t, a
                CALL apoc.refactor.mergeNodes([t, a], {properties: "combine", mergeRels: true})
                YIELD node RETURN count(node)
                """, target=target, aliases=aliases)
        print("👑 皇权实体专项缝合完成。")