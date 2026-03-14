import os
import time
from neo4j import GraphDatabase
from opencc import OpenCC
from dotenv import load_dotenv

load_dotenv()

class Neo4jGraphWriter:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        
        if not password:
            raise ValueError("❌ 找不到 NEO4J_PASSWORD，请在 .env 文件中配置！")
            
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.cc = OpenCC('t2s')
        self.setup_constraints()

    def close(self):
        self.driver.close()

    def setup_constraints(self):
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Office) REQUIRE o.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.name IS UNIQUE"
        ]
        with self.driver.session() as session:
            for q in queries:
                try: session.run(q)
                except Exception: pass
        print("🛡️ Neo4j 唯一性约束与索引初始化完成。")

    def _normalize(self, text):
        if not text: return text
        return self.cc.convert(str(text)).strip().replace("\u200b", "")

    def _merge_entity(self, tx, entity):
        e_type = entity.get("type", "Person")
        raw_name = entity.get("standard_name") or entity.get("name")
        name = self._normalize(raw_name)
        
        if not name: return

        raw_aliases = entity.get("aliases", [])
        aliases = [self._normalize(a) for a in raw_aliases if a]

        query = f"""
        MERGE (n:{e_type} {{name: $name}})
        WITH n
        UNWIND coalesce(n.aliases, []) + $aliases AS alias
        WITH n, collect(DISTINCT alias) AS unique_aliases
        SET n.aliases = unique_aliases
        """
        tx.run(query, name=name, aliases=aliases)

    def _merge_relationship(self, tx, triplet):
        head = self._normalize(triplet.get("head"))
        tail = self._normalize(triplet.get("tail"))
        relation = triplet.get("relation")
        props = triplet.get("properties", {})
        
        if not (head and tail and relation): return

        safe_rel = ''.join(filter(str.isalnum, relation))
        evidence = props.get("evidence", "暂无证据")
        source = props.get("source", "未知来源")
        
        # 👑 核心修改：读取新提取的年代属性
        raw_time = props.get("raw_time", "时间不明")
        ad_year = props.get("ad_year")  # 可能是数字，也可能是 None

        query = f"""
        MATCH (h {{name: $head}})
        MATCH (t {{name: $tail}})
        MERGE (h)-[r:`{safe_rel}`]->(t)
        ON CREATE SET 
            r.evidence_list = [$evidence],
            r.source_list = [$source],
            r.raw_time = $raw_time,
            r.year_ad = $ad_year,
            r.created_at = timestamp()
        ON MATCH SET 
            r.evidence_list = CASE 
                WHEN NOT $evidence IN r.evidence_list THEN r.evidence_list + [$evidence] 
                ELSE r.evidence_list END,
            r.source_list = CASE 
                WHEN NOT $source IN r.source_list THEN r.source_list + [$source] 
                ELSE r.source_list END,
            // 如果原有记录没有年份，则补充新提取的年份
            r.year_ad = coalesce(r.year_ad, $ad_year),
            r.raw_time = CASE WHEN $raw_time <> '时间不明' AND $raw_time <> 'null' THEN $raw_time ELSE r.raw_time END,
            r.updated_at = timestamp()
        """
        tx.run(query, head=head, tail=tail, evidence=evidence, source=source, raw_time=raw_time, ad_year=ad_year)

    def _execute_with_retry(self, session, write_func, item, max_retries=3):
        for attempt in range(max_retries):
            try:
                session.execute_write(write_func, item)
                break
            except Exception as e:
                error_msg = str(e).lower()
                if "deadlock" in error_msg or "transient" in error_msg or attempt < max_retries - 1:
                    print(f"⚠️ 触发数据库锁，等待 1 秒后重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(1)
                else:
                    print(f"❌ 达到最大重试次数，数据写入放弃: {e}\n   放弃的数据: {item}")

    def write_graph_data(self, data):
        if not data: return
            
        entities = data.get("entities", [])
        triplets = data.get("triplets", [])
        
        with self.driver.session() as session:
            for entity in entities:
                self._execute_with_retry(session, self._merge_entity, entity)
            for triplet in triplets:
                self._execute_with_retry(session, self._merge_relationship, triplet)

if __name__ == "__main__":
    # 👑 更新后的测试数据：包含了提取出的年份
    test_data = {
      "entities": [
        {"type": "Person", "name": "武則天", "aliases": ["太后"]},
        {"type": "Person", "name": "裴炎", "aliases": ["中书令"]}
      ],
      "triplets": [
        {
          "head": "武则天",
          "relation": "迫害",
          "tail": "裴炎",
          "properties": {"evidence": "斩炎于洛阳", "source": "旧唐书", "raw_time": "光宅元年", "ad_year": 684}
        }
      ]
    }
    
    writer = Neo4jGraphWriter()
    print("🕸️ 正在执行全量缝合模式写入...")
    writer.write_graph_data(test_data)
    writer.close()
    print("🎉 测试完成，您可以前往 Neo4j 查看关系上的 year_ad 属性。")