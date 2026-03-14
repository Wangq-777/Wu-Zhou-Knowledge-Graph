import os
import json
from openai import OpenAI
import json_repair
from dotenv import load_dotenv

load_dotenv()

class QwenExtractor:
    def __init__(self):
        """初始化 Qwen 客户端"""
        api_key = os.getenv("QWEN_API_KEY")
        if not api_key:
            raise ValueError("❌ 找不到 QWEN_API_KEY，请在 .env 文件中配置！")
            
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model_name = "qwen-plus"

    def _get_system_prompt(self, full_source):
        # 👑 核心修改：在 RELATIONSHIP CATEGORIES 和 OUTPUT 示例中加入了时间属性要求
        return f"""
ROLE: 唐代历史与政治网络研究专家
TASK: 从《{full_source}》的文本中提取历史人物、机构、事件实体，以及它们之间的深层政治关系。
FORMAT: 严格输出纯 JSON 对象，不要包含任何 markdown 标记 (如 ```json) 和额外解释。

ENTITY DEFINITIONS
- Person: 历史人物 (需提取 standard_name 和 aliases，如 ["裴炎", "字子隆"])
- Office: 官职、爵位或机构 (如 "中书令", "宰相", "豫州刺史")
- Event: 具有政治影响的历史事件 (如 "徐敬业起兵")

RELATIONSHIP CATEGORIES
(要求：每条关系必须包含 properties，且 properties 中必须包含以下字段：
 1. evidence: 原文证据
 2. source: 固定设为 "{full_source}"
 3. raw_time: 原文中的时间描述 (如 "光宅元年", "秋七月")，若无明确时间请填 "null"
 4. ad_year: 根据历史知识推算的公元纪年 (必须是整数，如 684)，若无法推算请填 null
)

A. Political Dynamics (政治博弈)
- [:依附] (Person A -> Person B): 下级投靠上级，结党营私
- [:结盟] (Person A <-> Person B): 平级政治合作
- [:政敌] (Person A <-> Person B): 制度内政见不合，互相弹劾
- [:迫害] (Person A -> Person B): 构陷、流放、诛杀 (需含 method 属性)

B. Power & Institutions (皇权与制度)
- [:任免] (Ruler -> Person): 权力授予或剥夺 (需含 action, position)
- [:担任] (Person -> Office): 实际上任某职
- [:参与] (Person -> Event): 参与重大事件 (需含 role 属性，如"主谋"或"平叛")

OUTPUT JSON FORMAT EXACTLY AS BELOW:
{{
  "entities": [
    {{"type": "Person", "standard_name": "武则天", "aliases": ["太后", "则天"]}}
  ],
  "triplets": [
    {{
      "head": "武则天",
      "relation": "迫害",
      "tail": "裴炎",
      "properties": {{
        "method": "斩首",
        "evidence": "光宅元年...时中书令裴炎与太后理有异同，太后怒，斩炎于洛阳。",
        "source": "{full_source}",
        "raw_time": "光宅元年",
        "ad_year": 684
      }}
    }}
  ]
}}
"""

    def extract(self, text_chunk, source_book="资治通鉴", volume="未知卷册"):
        full_source = f"{source_book}({volume})"
        sys_prompt = self._get_system_prompt(full_source)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"请提取以下《{full_source}》文本中的图谱信息：\n\n{text_chunk}"}
                ],
                temperature=0.1, 
                top_p=0.8
            )
            
            raw_content = response.choices[0].message.content
            parsed_json = json_repair.loads(raw_content)
            
            if not isinstance(parsed_json, dict) or "entities" not in parsed_json or "triplets" not in parsed_json:
                print(f"⚠️ 格式非法，跳过 [{full_source}] 的一段文本")
                return {"entities": [], "triplets": []}
                
            return parsed_json

        except Exception as e:
            print(f"❌ 抽取异常: {e}")
            return {"entities": [], "triplets": []}

if __name__ == "__main__":
    extractor = QwenExtractor()
    sample_text = "光宅元年，废皇帝为庐陵王。时中书令裴炎与太后理有异同，太后怒，斩炎于洛阳。"
    print("🤖 正在呼叫 Qwen 进行知识抽取...\n")
    result = extractor.extract(sample_text, source_book="旧唐书")
    print("✅ 抽取结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))