import os
import networkx as nx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="武周政局极性推演 API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

neo4j_driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "你的密码")) # 替换为真实密码
)

llm_client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY", "你的Qwen_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

FACTION_NAMES = {0: "帝室", 1: "武氏", 2: "关陇集团", 3: "武氏党羽", 4: "反武势力", 5: "中立/骑墙"}

# 👑 1. 明确血统白名单 (只有这些人及对应姓氏才有资格进入 0 和 1)
BLOOD_LI = ["唐高宗", "唐中宗", "李显", "唐睿宗", "李旦", "唐玄宗", "太平公主", "相王旦", "韦后", "安乐公主", "李重俊", "李轮"]
BLOOD_WU = ["武则天", "武三思", "武承嗣", "武攸暨", "武延秀", "魏王承嗣", "武氏诸王"]

# 👑 2. 政治阵眼 (不看血统，只看政治定性)
SEEDS = {
    # 关陇
    "长孙无忌": 2, "褚遂良": 2, "韩瑗": 2, "柳奭": 2,
    # 明确的武氏党羽核心 (只保留男宠等绝对死忠，把来俊臣等酷吏交还给算法推演)
    "张易之": 3, "张昌宗": 3, "薛怀义": 3,
    # 明确的反武/拥唐核心
    "裴炎": 4, "徐敬业": 4, "骆宾王": 4, "张柬之": 4, "狄仁杰": 4, "桓彦范": 4, "敬晖": 4, "魏元忠": 4
}

# 把血统名单也并入阵眼，用于散发引力
for name in BLOOD_LI: SEEDS[name] = 0
for name in BLOOD_WU: SEEDS[name] = 1

POS_RELS = ['依附', '结盟', '任免', '担任', '举荐', '支持', '辅佐']
NEG_RELS = ['迫害', '政敌', '贬谪', '流放', '诛杀', '罢免']

@app.get("/api/stats")
def get_global_stats():
    with neo4j_driver.session() as session:
        counts = session.run("MATCH (p:Person) OPTIONAL MATCH ()-[r]->() RETURN count(DISTINCT p) AS p_cnt, count(r) AS r_cnt").single()
        top_power = session.run("MATCH (p:Person) RETURN p.name AS name, coalesce(p.power_score, 0.1) AS value ORDER BY value DESC LIMIT 10").data()
        return {"counts": {"persons": counts["p_cnt"], "relations": counts["r_cnt"]}, "top_power": top_power}

@app.get("/api/graph")
def get_graph(start_year: int = 600, end_year: int = 800, min_power: float = 0.0):
    with neo4j_driver.session() as session:
        query = """
        MATCH (s:Person)-[r]->(t:Person)
        WHERE s.name <> t.name
          AND ((r.year_ad >= $start_year AND r.year_ad <= $end_year) OR r.year_ad IS NULL)
          AND coalesce(s.power_score, 0) >= $min_power AND coalesce(t.power_score, 0) >= $min_power
        RETURN s, r, t
        """
        result = session.run(query, start_year=start_year, end_year=end_year, min_power=min_power)
        
        nodes_dict = {}
        links = []
        G_pos = nx.Graph() 

        for record in result:
            s, t, r = record["s"], record["t"], record["r"]
            for node in [s, t]:
                if node["name"] not in nodes_dict:
                    nodes_dict[node["name"]] = {"id": node["name"], "name": node["name"], "value": round(node.get("power_score", 0.1), 3), "category": 5}
            
            links.append({
                "source": s["name"], "target": t["name"], "type": r.type, 
                "evidence": r.get("evidence_list", [r.get("evidence", "暂无依据")])[0],
                "sourceBook": r.get("source_list", [r.get("source", "未知出处")])[0], "year": r.get("year_ad", "未知")
            })
            if r.type in POS_RELS: G_pos.add_edge(s["name"], t["name"])

        # 👑 3. 极性积分推演 + 血统壁垒
        for name, node_data in nodes_dict.items():
            # 规则 A：阵眼与绝对血统优先
            if name in SEEDS:
                node_data["category"] = SEEDS[name]
                continue
            if name.startswith("李"): # 未在阵眼中定义的小李家宗亲
                node_data["category"] = 0
                continue
            if name.startswith("武"): # 未在阵眼中定义的小武家宗亲
                node_data["category"] = 1
                continue

            # 规则 B：打分推演
            scores = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0}
            for link in links:
                s, t, rel = link["source"], link["target"], link["type"]
                if name not in [s, t]: continue
                
                other_node = t if name == s else s
                other_seed = SEEDS.get(other_node)

                if other_seed is not None:
                    if rel in POS_RELS:
                        scores[other_seed] += 3 # 跟着靠山混
                    elif rel in NEG_RELS:
                        if other_seed in [1, 3]: scores[4] += 3 # 被武家迫害 -> 反武
                        elif other_seed in [0, 2, 4]: scores[3] += 3 # 被李唐迫害 -> 武党

            if sum(scores.values()) == 0 and name in G_pos:
                for anchor, f_id in SEEDS.items():
                    if anchor in G_pos and nx.has_path(G_pos, name, anchor):
                        dist = nx.shortest_path_length(G_pos, name, anchor)
                        if dist == 2: scores[f_id] += 1

            best_faction = 5
            max_score = 0
            for f_id, score in scores.items():
                if score > max_score:
                    max_score = score
                    best_faction = f_id

            # 👑 规则 C：血统壁垒降级 (解决宗楚客变武氏、外臣变皇族的问题)
            if best_faction == 0:
                # 赢得了帝室的最高分，但因为前面规则 A 没拦截住，说明他既不在白名单，也不姓李
                best_faction = 4 # 降级为拥唐/反武势力
            elif best_faction == 1:
                # 赢得了武氏最高分，但既不姓武，也不在白名单
                best_faction = 3 # 降级为武氏党羽

            node_data["category"] = best_faction
            
        return {"nodes": list(nodes_dict.values()), "links": links}

@app.get("/api/person/{name}")
def get_person_dossier(name: str):
    with neo4j_driver.session() as session:
        query = """
        MATCH (p:Person {name: $name})
        OPTIONAL MATCH (p)-[r_out]->(t:Person) WITH p, collect({target: t.name, action: type(r_out), year: r_out.year_ad}) AS actions
        OPTIONAL MATCH (s:Person)-[r_in]->(p) WITH p, actions, collect({source: s.name, action: type(r_in), year: r_in.year_ad}) AS encounters
        RETURN p.name AS name, coalesce(p.power_score, 0) AS power, p.aliases AS aliases, actions, encounters
        """
        record = session.run(query, name=name).single()
        if not record: return {"error": "未找到该人物"}
            
        actions = [a for a in record["actions"] if a.get("target")]
        encounters = [e for e in record["encounters"] if e.get("source")]
        
        affinity_counts = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0}
        total_pos = 0
        for rel in actions + encounters:
            if rel["action"] in POS_RELS:
                friend = rel.get("target") or rel.get("source")
                friend_faction = SEEDS.get(friend, 5)
                affinity_counts[friend_faction] += 1
                total_pos += 1
                
        affinity = {}
        if total_pos > 0:
            for fid, count in affinity_counts.items():
                if count > 0: affinity[FACTION_NAMES[fid]] = round((count / total_pos) * 100)
        else:
            affinity["无政治结交"] = 100
            
        return {
            "name": record["name"], "aliases": record["aliases"] or [], "affinity": affinity,
            "resume": {
                "actions": sorted(actions, key=lambda x: str(x.get('year') or '9999')),
                "encounters": sorted(encounters, key=lambda x: str(x.get('year') or '9999'))
            }
        }

class QuestionRequest(BaseModel): question: str

@app.post("/api/ask")
def ask_ai(req: QuestionRequest):
    try:
        with neo4j_driver.session() as session:
            context_query = """
            MATCH (p:Person)-[r]->(t:Person)
            WITH p, r, t,
                 CASE WHEN $question CONTAINS p.name OR any(a in coalesce(p.aliases, []) WHERE $question CONTAINS a) THEN 1 ELSE 0 END AS s_match,
                 CASE WHEN $question CONTAINS t.name OR any(a in coalesce(t.aliases, []) WHERE $question CONTAINS a) THEN 1 ELSE 0 END AS t_match
            WHERE s_match > 0 OR t_match > 0
            WITH p, r, t, (s_match + t_match) AS match_score
            ORDER BY match_score DESC, r.year_ad DESC LIMIT 15
            RETURN p.name AS source, type(r) AS action, t.name AS target, 
                   coalesce(r.evidence_list[0], r.evidence, '暂无') AS evidence, coalesce(r.source_list[0], r.source, '未知') AS source_book
            """
            results = session.run(context_query, question=req.question).data()

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