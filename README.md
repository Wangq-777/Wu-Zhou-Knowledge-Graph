Markdown


# 📜 武周政局动态演化指挥中心 (V2.0)

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Neo4j](https://img.shields.io/badge/Neo4j-5.x-018bff.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688.svg)
![ECharts](https://img.shields.io/badge/ECharts-5.4-E43961.svg)
![LLM](https://img.shields.io/badge/LLM-Qwen_Plus-6151CC.svg)

本项目是一个基于**极性政治拓扑网络**的历史政局研判与图谱推演系统。通过集成大语言模型（LLM）自动化抽取、图算法分析与 Hybrid GraphRAG 向量检索，系统实现了对《资治通鉴》及《两唐书》中武周时期复杂权力关系的数字化还原、动态推演与智能问答。

---

## ✨ 核心特性与技术指标

### 1. 严格的语义化 Ontology 设计
图谱摒弃了发散的实体抽取，通过 Schema 强制约束了极简的政治模型：
* **节点类型**: 
  * `Person` (历史人物) 
  * `Event` (具有政治影响的历史大案，绑定 1024 维 `embedding` 向量)
* **人际极性网 (Person-to-Person)**: 严格限制为正向盟友（`依附`、`结盟`）与负向对抗（`政敌`、`迫害`）两类。负向关系强制提取具体打击手段（`method`）。
* **事件星型网 (Person-to-Event)**: 人物仅通过 `参与` 边连接事件，强制绑定自然语言角色（`role`）与极性立场（`stance`：支持/反对）。

### 2. 洗刷“虚假权力”的纯净版 PageRank
传统的中心度算法会将“被迫害”、“被流放”等负面高频互动误算为影响力。系统在 `power_injector.py` 中进行了核心修正：
* **极性过滤**：仅提取绝对正向的政治盟友关系（`type(r) IN ['依附', '结盟']`）构建有向图（DiGraph），彻底隔绝仇敌网络带来的虚假权力加成。
* **量化映射**：运行 `alpha=0.85` 的 PageRank 算法，模拟权力网络中 85% 的裙带继承与 15% 的突发变数。得分被放大 100 倍写入 `power_score` 属性，供前端 ECharts 直接渲染为节点半径（`symbolSize`）。

### 3. 图拓扑涌现的 Louvain 派系发现
系统在 `faction_evaluator.py` 中拒绝手动穷举所有人，而是基于网络拓扑自动定性：
* **设定阵眼 (Seed Nodes)**：硬编码 5 大核心引力中心：
  * `0`: 李唐帝室 (唐高宗、李显等)
  * `1`: 武氏宗亲 (武则天、武三思等)
  * `2`: 关陇集团 (长孙无忌、褚遂良等)
  * `3`: 武周党羽 (张易之、薛怀义等)
  * `4`: 反武势力 (裴炎、狄仁杰等)
* **社区发现与染色**：在 `['依附', '结盟']` 构成的纯正面子图上运行 **Louvain 算法**。社区内普通节点通过计票机制跟随阵眼大流完成染色。没有任何正面盟友的孤立节点，则被统一兜底划入 `5 (中立/未明)` 阵营。

### 4. 自动化实体对齐机制 (Entity Alignment)
* **前端清洗**: `text_cleaner.py` 结合 `OpenCC`，在爬取数据时强制进行繁转简，统一底层字符。
* **后端归并**: `entity_align.py` 挂载了基于邻居审计的实锤字典，自动将“武曌”、“天后”等分身节点物理归并至标准主节点（武则天），并完整迁移所有出入度关系脉络。

### 5. Hybrid GraphRAG 混合检索问答
`server.py` 实现了双路检索与无幻觉答复：
* **向量检索 (`event_embedding_idx`)**: 基于余弦相似度捕获用户提问中的历史大案。
* **拓扑穿透**: 对问题进行人物别名正则识别，提取 Neo4j 中的图结构关系。
* **事实注入**: 最终回复强制回溯边属性中的原文（`evidence`）与出处（`source_book`），并渲染为醒目的凭证卡片。

---

## 📂 项目模块架构

```text
├── data/
│   ├── raw/                 # 存放清洗后的《资治通鉴》与《两唐书》纯文本
│   ├── processed/           # 预处理中间产物
│   └── error_logs/          # LLM 抽取失败的抢救性 JSON 备份
├── src/
│   ├── scraper/             # 🕷️ 数据采集模块 (API获取与简繁清洗)
│   ├── kg_builder/          # 🏗️ 图谱构建模块 (LLM抽取、Neo4j写入、实体对齐)
│   ├── graph_mining/        # 🧮 图算法挖掘模块 (PageRank 权力计算、Louvain 派系发现)
│   ├── backend/             # ⚙️ 后端服务模块 (FastAPI + GraphRAG)
│   └── frontend/            # 🖥️ 前端可视化大屏 (index.html)
├── prompts/                 # Schema 与系统设定
├── lib/                     # 前端本地依赖库
├── main_pipeline.py         # 🚀 多线程知识抽取核心总线
└── requirements.txt         # 项目依赖清单


🚀 快速启动指南
1. 环境与配置
确保已安装 Python 3.9+ 及 Neo4j 数据库（推荐 5.x 版本）。
克隆代码并安装依赖：

Bash


pip install -r requirements.txt


在根目录创建 .env 环境变量文件：

Code snippet


NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
QWEN_API_KEY=your_dashscope_api_key
NO_PROXY=127.0.0.1,localhost


2. 运行构建流水线 (Pipeline)
⚠️ 注意: 所有 Python 命令请务必在项目根目录下执行。
Step 1: 史料采集与预处理

Bash


python src/scraper/text_cleaner.py


Step 2: 预埋静态基建

Bash


python src/kg_builder/static_injector.py


Step 3: 启动 LLM 抽取与图谱写入

Bash


python main_pipeline.py


Step 4: 运行图算法挖掘

Bash


python src/kg_builder/entity_align.py      # 实体消歧
python src/graph_mining/power_injector.py  # 权力指数量化
python src/graph_mining/faction_evaluator.py # 派系自动染色


3. 启动指挥中心大屏
启动 FastAPI 后端服务：

Bash


python src/backend/server.py


服务就绪后，在浏览器中双击打开 src/frontend/index.html，即可进入武周政局全息指挥沙盘。
📝 许可证 (License)
本项目采用 MIT License 开源协议。
