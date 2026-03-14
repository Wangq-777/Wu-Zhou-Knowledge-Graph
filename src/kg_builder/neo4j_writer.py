import os
import time
from neo4j import GraphDatabase
from opencc import OpenCC
from dotenv import load_dotenv
from openai import OpenAI

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
        
        # 初始化 Qwen 客户端用于生成 Embedding 向量
        api_key = os.getenv("QWEN_API_KEY")
        if not api_key:
            raise ValueError("❌ 找不到 QWEN_API_KEY，无法生成向量！")
        self.llm_client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        self.setup_constraints()

    def close(self):
        self.driver.close()

    def setup_constraints(self):
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.name IS UNIQUE",
            """
            CREATE VECTOR INDEX event_embedding_idx IF NOT EXISTS
            FOR (e:Event)
            ON (e.embedding)
            OPTIONS {indexConfig: {
             `vector.dimensions`: 1024,
             `vector.similarity_function`: 'cosine'
            }}
            """
        ]
        with self.driver.session() as session:
            for q in queries:
                try: session.run(q)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"⚠️ 建立索引/约束时出现提示: {e}")
        print("🛡️ Neo4j V2.0 唯一性约束与【向量索引】初始化完成。")

    def _normalize(self, text):
        if not text: return text
        return self.cc.convert(str(text)).strip().replace("\u200b", "")

    def _get_embedding(self, text):
        try:
            response = self.llm_client.embeddings.create(
                model="text-embedding-v3",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"⚠️ 向量生成失败 (跳过): {e}")
            return None

    def _merge_entity(self, tx, entity):
        e_type = entity.get("type", "Person")
        raw_name = entity.get("standard_name") or entity.get("name")
        name = self._normalize(raw_name)
        
        if not name: return

        raw_aliases = entity.get("aliases", [])
        aliases = [self._normalize(a) for a in raw_aliases if a]

        # 👑 Event 自动生成向量
        embedding = None
        if e_type == "Event":
            desc_text = f"{name} " + " ".join(aliases)
            embedding = self._get_embedding(desc_text)
            time.sleep(0.1)

        query = f"""
        MERGE (n:{e_type} {{name: $name}})
        WITH n
        UNWIND coalesce(n.aliases, []) + $aliases AS alias
        WITH n, collect(DISTINCT alias) AS unique_aliases
        SET n.aliases = unique_aliases
        """
        
        if embedding:
            query += ", n.embedding = $embedding"

        tx.run(query, name=name, aliases=aliases, embedding=embedding)

    def _merge_relationship(self, tx, triplet):
        head = self._normalize(triplet.get("head"))
        tail = self._normalize(triplet.get("tail"))
        relation = triplet.get("relation")
        props = triplet.get("properties", {})
        
        if not (head and tail and relation): return

        safe_rel = ''.join(filter(str.isalnum, relation))
        evidence = props.get("evidence", "暂无证据")
        source = props.get("source", "未知来源")
        raw_time = props.get("raw_time", "时间不明")
        ad_year = props.get("ad_year")
        
        role = props.get("role")
        stance = props.get("stance")
        method = props.get("method")

        query = f"""
        MATCH (h {{name: $head}})
        MATCH (t {{name: $tail}})
        MERGE (h)-[r:`{safe_rel}`]->(t)
        ON CREATE SET 
            r.evidence_list = [$evidence],
            r.source_list = [$source],
            r.raw_time = $raw_time,
            r.year_ad = $ad_year,
            r.role = $role,
            r.stance = $stance,
            r.method = $method,
            r.created_at = timestamp()
        ON MATCH SET 
            r.evidence_list = CASE 
                WHEN NOT $evidence IN r.evidence_list THEN r.evidence_list + [$evidence] 
                ELSE r.evidence_list END,
            r.source_list = CASE 
                WHEN NOT $source IN r.source_list THEN r.source_list + [$source] 
                ELSE r.source_list END,
            r.year_ad = coalesce(r.year_ad, $ad_year),
            r.raw_time = CASE WHEN $raw_time <> '时间不明' AND $raw_time <> 'null' THEN $raw_time ELSE r.raw_time END,
            r.role = coalesce(r.role, $role),
            r.stance = coalesce(r.stance, $stance),
            r.method = coalesce(r.method, $method),
            r.updated_at = timestamp()
        """
        tx.run(query, head=head, tail=tail, evidence=evidence, source=source, 
               raw_time=raw_time, ad_year=ad_year, role=role, stance=stance, method=method)

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
                    print(f"❌ 写入放弃: {e}")

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
    test_data = {
      "entities": [
        {"type": "Person", "standard_name": "武则天", "aliases": ["太后"]},
        {"type": "Person", "standard_name": "李义府", "aliases": []},
        {"type": "Event", "standard_name": "废王立武", "aliases": []}
      ],
      "triplets": [
        {
          "head": "李义府",
          "relation": "参与",
          "tail": "废王立武",
          "properties": {"role": "叩阁上表", "stance": "支持", "evidence": "李义府叩阁上表请立之", "source": "资治通鉴", "ad_year": 655}
        }
      ]
    }
    
    writer = Neo4jGraphWriter()
    print("🕸️ 正在执行 V2.0 融合测试写入...")
    writer.write_graph_data(test_data)
    writer.close()
    print("🎉 测试完成！")