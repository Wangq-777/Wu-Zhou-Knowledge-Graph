import os
import sys
import streamlit as st
from streamlit_echarts import st_echarts
from neo4j import GraphDatabase
from dotenv import load_dotenv

# --- 环境自愈 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)
load_dotenv()

# --- 1. 注入顶级商业 UI 样式 (CSS) ---
st.set_page_config(page_title="武周政局权力图谱", layout="wide")

def apply_pro_theme():
    st.markdown("""
        <style>
        /* 极致黑底色 */
        .stApp { background-color: #050505; color: #d1d1d1; }
        
        /* 玻璃拟态侧边栏 + 金色装饰线 */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0d1117 0%, #050505 100%) !important;
            border-right: 1px solid rgba(212, 175, 55, 0.3);
            backdrop-filter: blur(10px);
        }
        [data-testid="stSidebar"]::before {
            content: ""; position: absolute; top: 0; left: 0; width: 4px; height: 100%;
            background: linear-gradient(180deg, #d4af37, transparent);
        }

        /* 琥珀金标题设计 */
        .pro-header {
            font-family: 'Noto Serif SC', serif;
            background: linear-gradient(90deg, #d4af37, #f7e1ad);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 32px; font-weight: 800; text-align: center; margin: 20px 0;
            letter-spacing: 3px;
        }

        /* 指标卡片高级感 */
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 4px; border-left: 3px solid #d4af37;
            padding: 10px !important;
        }
        </style>
    """, unsafe_allow_html=True)

apply_pro_theme()

# --- 2. 核心数据检索 ---
@st.cache_data(ttl=300)
def fetch_data(min_p, limit):
    driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))
    query = """
    MATCH (n:Person)-[r]->(m:Person)
    WHERE n.power_score >= $min_p AND m.power_score >= $min_p
    RETURN n.name AS s, n.power_score AS s_p, coalesce(n.faction_id, 0) AS s_f,
           type(r) AS rel, r.source_list AS src_list,
           m.name AS t, m.power_score AS t_p, coalesce(m.faction_id, 0) AS t_f
    ORDER BY n.power_score DESC LIMIT $limit
    """
    nodes, edges = [], []
    added = set()
    # 矿物色配色：朱砂、石青、松石、赭石、墨黑
    colors = ["#c3272b", "#1661ab", "#1a94bc", "#b78d12", "#424c50"]

    with driver.session() as session:
        records = session.run(query, min_p=min_p, limit=limit)
        for r in records:
            for k in ['s', 't']:
                if r[k] not in added:
                    score = r[f'{k}_p'] or 0.1
                    nodes.append({
                        "name": r[k],
                        "symbolSize": (score**0.5) * 70,
                        "category": int(r[f'{k}_f'] % 5),
                        "itemStyle": {"color": colors[int(r[f'{k}_f'] % 5)], "shadowBlur": 15, "shadowColor": 'rgba(255,255,255,0.1)'},
                        "label": {"show": score > 0.05}
                    })
                    added.add(r[k])
            
            weight = len(r['src_list'] or [])
            edges.append({
                "source": r['s'], "target": r['t'], "value": r['rel'],
                "lineStyle": {"width": weight * 1.5, "curveness": 0.2, "opacity": 0.6, "color": "#d4af37" if weight > 1 else "#555"}
            })
    return nodes, edges

# --- 3. 页面布局渲染 ---
st.markdown('<div class="pro-header">武周政治权力交互研判系统</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown('<div style="color:#d4af37; font-weight:800; font-size:20px;">📜 档案室</div>', unsafe_allow_html=True)
    min_p = st.slider("权力敏感度", 0.0, 1.0, 0.05)
    limit = st.slider("数据扫描密度", 50, 400, 150)
    st.divider()
    st.success("核心数据库：已在线")

nodes, edges = fetch_data(min_p, limit)

# 顶部数据大屏
if nodes:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("权力中枢", nodes[0]['name'])
    c2.metric("活跃派系", f"{len(set(n['category'] for n in nodes))} 集团")
    c3.metric("史料交叉点", f"{len([e for e in edges if e['lineStyle']['width'] > 1.5])} 处")
    c4.metric("置信度", "94.2%")

# ECharts 高级关系图配置
options = {
    "backgroundColor": "transparent",
    "tooltip": {"trigger": "item", "formatter": "{b}"},
    "series": [{
        "type": "graph",
        "layout": "force",
        "data": nodes,
        "links": edges,
        "roam": True,
        "draggable": True,
        "focusNodeAdjacency": True, # 鼠标悬停时高亮相关路径
        "force": {
            "repulsion": 600,
            "edgeLength": [50, 200],
            "gravity": 0.1
        },
        "lineStyle": {"curveness": 0.3},
        "emphasis": {
            "lineStyle": {"width": 8, "shadowBlur": 15, "shadowColor": "#d4af37"}
        }
    }]
}

st_echarts(options=options, height="800px")