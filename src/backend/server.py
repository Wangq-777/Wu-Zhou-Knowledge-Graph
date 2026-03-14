import os
import networkx as nx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase
from openai import OpenAI
from dotenv import load_dotenv
os.environ['NO_PROXY'] = '127.0.0.1,localhost'

load_dotenv()

app = FastAPI(title="武周政局极性推演 API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

neo4j_driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD"))
)

llm_client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 👑 与前端字典字字对齐
FACTION_NAMES = {
    0: "李唐帝室", 1: "武氏宗亲", 2: "关陇集团", 
    3: "武周党羽", 4: "反武势力", 5: "中立/未明", 6: "重大事件"
}

BLOOD_LI = ["唐高宗", "唐中宗", "李显", "唐睿宗", "李旦", "唐玄宗", "太平公主", "相王旦", "韦后", "安乐公主", "李重俊", "李轮"]
BLOOD_WU = ["武则天", "武三思", "武承嗣", "武攸暨", "武延秀", "魏王承嗣", "武氏诸王"]

SEEDS = {
    "长孙无忌": 2, "褚遂良": 2, "韩瑗": 2, "柳奭": 2,
    "张易之": 3, "张昌宗": 3, "薛怀义": 3,
    "裴炎": 4, "徐敬业": 4, "骆宾王": 4, "张柬之": 4, "狄仁杰": 4, "桓彦范": 4, "敬晖": 4, "魏元忠": 4
}

for name in BLOOD_LI: SEEDS[name] = 0
for name in BLOOD_WU: SEEDS[name] = 1

# 👑 升级：兼容大模型的多元动词提取
POS_RELS = ['依附', '结盟', '任免', '担任', '举荐', '支持', '辅佐', '参与', '平反', '拥立']
NEG_RELS = ['迫害', '政敌', '贬谪', '流放', '诛杀', '罢免', '反对', '废黜']

@app.get("/api/stats")
def get_global_stats():
    with neo4j_driver.session() as session:
        # 👑 修复：增加对 Event (历史事件) 节点的统计查询
        counts = session.run("""
            MATCH (p:Person) WITH count(DISTINCT p) AS p_cnt
            OPTIONAL MATCH (e:Event) WITH p_cnt, count(DISTINCT e) AS e_cnt
            OPTIONAL MATCH ()-[r]->() RETURN p_cnt, e_cnt, count(r) AS r_cnt
        """).single()
        
        top_power = session.run("""
            MATCH (p:Person) 
            RETURN p.name AS name, coalesce(p.power_score, 0.1) AS value 
            ORDER BY value DESC LIMIT 10
        """).data()
        
        return {
            "counts": {
                "persons": counts["p_cnt"], 
                "events": counts["e_cnt"],   # 👈 补充了 events 的返回
                "relations": counts["r_cnt"]
            }, 
            "top_power": top_power
        }

@app.get("/api/graph")
def get_graph(start_year: int = 600, end_year: int = 800, min_power: float = 0.0):
    with neo4j_driver.session() as session:
        # 👑 终极沙盘推演：人物比权力 (PageRank)，事件比引力 (参与人数)
        query = """
        MATCH (s:Person)-[r]->(t)
        WHERE (t:Person OR t:Event) AND s.name <> t.name
          AND ((r.year_ad >= $start_year AND r.year_ad <= $end_year) OR r.year_ad IS NULL)
          // 起点的人物必须达到权力阈值
          AND coalesce(s.power_score, 0.0) >= $min_power 
        WITH s, r, t, labels(t)[0] AS t_type
        WITH s, r, t, t_type,
             CASE WHEN t_type = 'Event' THEN COUNT { (t)--() } ELSE 0 END AS event_impact
             
        // 🛡️ 核心防线：
        // 1. 如果是人，权力分数必须达标
        // 2. 如果是事件，必须 >= 3 人参与（保底清理历史碎屑）
        // 3. 事件的参与人数，必须随前端的权力滑块动态提升 (假设满级事件约30人参与)
        WHERE (t_type = 'Person' AND coalesce(t.power_score, 0.0) >= $min_power)
           OR (t_type = 'Event' AND event_impact >= 3 AND event_impact >= ($min_power * 30))
        RETURN s, r, t, t_type, event_impact
        """
        result = session.run(query, start_year=start_year, end_year=end_year, min_power=min_power)
        
        nodes_dict = {}
        links = []
        G_pos = nx.Graph() 

        for record in result:
            s, t, r = record["s"], record["t"], record["r"]
            t_type, event_impact = record["t_type"], record["event_impact"]
            
            if s["name"] not in nodes_dict:
                nodes_dict[s["name"]] = {
                    "id": s["name"], "name": s["name"], 
                    "value": s.get("power_score", 0.1), 
                    "category": 5, "type": "Person"
                }
            
            if t["name"] not in nodes_dict:
                if t_type == "Event":
                    cat = 6
                    # 将事件的参与人数转化为 0~1 的 value，便于前端统一渲染大小
                    # 假设 30 人参与的政变就是满级事件 (1.0)
                    val = min(event_impact / 30.0, 1.0) 
                else:
                    cat = 5
                    val = t.get("power_score", 0.1)
                    
                nodes_dict[t["name"]] = {
                    "id": t["name"], "name": t["name"], 
                    "value": val, "category": cat, "type": t_type
                }
            
            evidence = r.get("evidence_list", [r.get("evidence", "暂无依据")])[0]
            source = r.get("source_list", [r.get("source", "未知出处")])[0]
            links.append({
                "source": s["name"], "target": t["name"], "type": r.type, 
                "evidence": evidence, "sourceBook": source, "year": r.get("year_ad", "未知")
            })
            
            if r.type in POS_RELS and t_type == "Person": 
                G_pos.add_edge(s["name"], t["name"])

        # ====== 下方是你原有的 Louvain 派系染色逻辑，完全保持不变 ======
        for name, node_data in nodes_dict.items():
            if node_data.get("type") == "Event": continue # 事件不染色
            
            if name in SEEDS:
                node_data["category"] = SEEDS[name]; continue
            if name.startswith("李"):
                node_data["category"] = 0; continue
            if name.startswith("武"):
                node_data["category"] = 1; continue

            scores = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0}
            for link in links:
                s_name, t_name, rel = link["source"], link["target"], link["type"]
                if name not in [s_name, t_name]: continue
                
                other_node = t_name if name == s_name else s_name
                other_seed = SEEDS.get(other_node)

                if other_seed is not None:
                    if rel in POS_RELS:
                        scores[other_seed] += 3 
                    elif rel in NEG_RELS:
                        if other_seed in [1, 3]: scores[4] += 3 
                        elif other_seed in [0, 2, 4]: scores[3] += 3 

            if sum(scores.values()) == 0 and name in G_pos:
                for anchor, f_id in SEEDS.items():
                    if anchor in G_pos and nx.has_path(G_pos, name, anchor):
                        dist = nx.shortest_path_length(G_pos, name, anchor)
                        if dist == 2: scores[f_id] += 1

            best_faction = 5
            max_score = 0
            for f_id, score in scores.items():
                if score > max_score:
                    max_score = score; best_faction = f_id

            if best_faction == 0: best_faction = 4 
            elif best_faction == 1: best_faction = 3 

            node_data["category"] = best_faction
            
        return {"nodes": list(nodes_dict.values()), "links": links}

@app.get("/api/person/{name}")
def get_person_dossier(name: str):
    with neo4j_driver.session() as session:
        # 👑 升级：直接拉取由 faction_evaluator.py 算出的真实 faction_id
        query = """
        MATCH (n {name: $name})
        OPTIONAL MATCH (n)-[r_out]->(t) WITH n, collect({target: t.name, action: type(r_out), year: r_out.year_ad, type: labels(t)[0], faction: t.faction_id}) AS actions
        OPTIONAL MATCH (s)-[r_in]->(n) WITH n, actions, collect({source: s.name, action: type(r_in), year: r_in.year_ad, type: labels(s)[0], faction: s.faction_id}) AS encounters
        RETURN n.name AS name, labels(n)[0] AS node_type, coalesce(n.faction_id, 5) AS own_faction, coalesce(n.aliases, []) AS aliases, actions, encounters
        """
        record = session.run(query, name=name).single()
        if not record: return {"error": "未找到该档案实体"}
            
        actions = [a for a in record["actions"] if a.get("target")]
        encounters = [e for e in record["encounters"] if e.get("source")]
        
        affinity_counts = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0}
        total_pos = 0
        
        if record["node_type"] == "Person":
            for rel in actions + encounters:
                if rel.get("type") == "Event": continue # 屏蔽事件
                    
                if rel["action"] in POS_RELS:
                    friend_name = rel.get("target") or rel.get("source")
                    
                    # 👑 核心修复：直接使用图算法涌现出的确切派系！
                    friend_faction = rel.get("faction")
                    
                    # 兜底：如果数据库里没跑派系算法，再用规则推断
                    if friend_faction is None:
                        if friend_name in SEEDS: friend_faction = SEEDS[friend_name]
                        elif friend_name.startswith("李"): friend_faction = 0
                        elif friend_name.startswith("武"): friend_faction = 1
                        else: friend_faction = 5
                        
                    affinity_counts[friend_faction] += 1
                    total_pos += 1
                
        affinity = {}
        if total_pos > 0:
            for fid, count in affinity_counts.items():
                if count > 0: affinity[FACTION_NAMES[fid]] = round((count / total_pos) * 100)
        else:
            affinity["无政治结交"] = 100
            
        return {
            "name": record["name"], 
            "node_type": record["node_type"], 
            "own_faction": FACTION_NAMES.get(record["own_faction"], "未知"), # 提取本体阵营
            "aliases": record["aliases"], 
            "affinity": affinity,
            "resume": {
                "actions": sorted(actions, key=lambda x: str(x.get('year') or '9999')),
                "encounters": sorted(encounters, key=lambda x: str(x.get('year') or '9999'))
            }
        }

class QuestionRequest(BaseModel): question: str

# 辅助函数：调用大模型获取查询向量
def get_embedding(text):
    try:
        resp = llm_client.embeddings.create(model="text-embedding-v3", input=text)
        return resp.data[0].embedding
    except:
        return None

@app.post("/api/ask")
def ask_ai(req: QuestionRequest):
    try:
        q_vec = get_embedding(req.question)
        with neo4j_driver.session() as session:
            # 👑 升级：Hybrid RAG。融合图谱拓扑模糊搜索与向量相似度检索
            hybrid_query = """
            CALL {
                WITH $vec AS v WHERE v IS NOT NULL
                CALL db.index.vector.queryNodes('event_embedding_idx', 3, v) YIELD node AS e, score
                MATCH (p:Person)-[r]->(e)
                RETURN p.name AS source, type(r) AS action, e.name AS target, 
                       coalesce(r.evidence_list[0], r.evidence, '暂无') AS evidence,
                       coalesce(r.source_list[0], r.source, '未知') AS source_book, score AS weight
            }
            UNION
            CALL {
                MATCH (s:Person)-[r]->(t)
                WHERE ($question CONTAINS s.name OR any(a IN coalesce(s.aliases, []) WHERE $question CONTAINS a))
                   OR ($question CONTAINS t.name OR any(a IN coalesce(t.aliases, []) WHERE $question CONTAINS a))
                RETURN s.name AS source, type(r) AS action, t.name AS target, 
                       coalesce(r.evidence_list[0], r.evidence, '暂无') AS evidence,
                       coalesce(r.source_list[0], r.source, '未知') AS source_book, 1.0 AS weight
                ORDER BY r.year_ad DESC LIMIT 15
            }
            RETURN source, action, target, evidence, source_book ORDER BY weight DESC LIMIT 20
            """
            try:
                results = session.run(hybrid_query, vec=q_vec, question=req.question).data()
            except Exception as neo_err:
                # 优雅降级：如果向量索引未就绪，使用纯粹的拓扑正则匹配
                fallback_query = """
                MATCH (s:Person)-[r]->(t)
                WHERE ($question CONTAINS s.name OR any(a IN coalesce(s.aliases, []) WHERE $question CONTAINS a))
                   OR ($question CONTAINS t.name OR any(a IN coalesce(t.aliases, []) WHERE $question CONTAINS a))
                RETURN s.name AS source, type(r) AS action, t.name AS target, 
                       coalesce(r.evidence_list[0], r.evidence, '暂无') AS evidence,
                       coalesce(r.source_list[0], r.source, '未知') AS source_book
                ORDER BY r.year_ad DESC LIMIT 20
                """
                results = session.run(fallback_query, question=req.question).data()

        if results:
            ctx = "【图谱检索结果】\n" + "\n".join([f"- {r['source']} {r['action']} {r['target']}。(原文: {r['evidence']}, 出处: {r['source_book']})" for r in results])
            system_prompt = f"你是武周情报研判系统。请依据检索结果回答。规则：陈述事实后紧跟依据，格式必须为【依据：原文 - 《出处》】。\n{ctx}"
        else:
            system_prompt = "你是情报研判系统。当前图谱未匹配到连线。请用自身知识回答，开头必须加警告：'⚠️ 当前指令未触发直接关系网，基于通用知识研判：'"

        response = llm_client.chat.completions.create(
            model="qwen-plus", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": req.question}], temperature=0.3
        )
        return {"answer": response.choices[0].message.content}
    except Exception as e:
        return {"answer": f"【依据：GraphRAG异常】 错误：{str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)