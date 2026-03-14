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
        return f"""
ROLE: 唐代政治网络与图数据工程专家
TASK: 从《{full_source}》中提取历史人物、重大事件，以及它们之间的【极性政治拓扑网络】。
FORMAT: 严格输出纯 JSON 对象，不要包含 markdown 标记和额外解释。

ENTITY DEFINITIONS
- Person: 历史人物 (提取 standard_name 和 aliases。注意：官职/爵位不要作为独立实体，直接归入该人物的 aliases 中)
- Event: 具有政治影响的重大历史事件 (如 "废王立武", "神龙政变", "徐敬业起兵")

RELATIONSHIP CATEGORIES
(要求：必须包含 evidence, source, ad_year。如果有具体动作细节，填入 method 属性)

A. 人际极性网络 (Person to Person，严格仅限以下 4 种)
- [:依附] (Person -> Person): 下级对上级的投靠、攀附与效忠。
- [:结盟] (Person <-> Person): 势均力敌者的平级合作、互相引援。
- [:政敌] (Person <-> Person): 朝堂上的政见不合、常规派系斗争与互相弹劾。
- [:迫害] (Person -> Person): 突破底线的单方面构陷、流放、肉体消灭 (需含 method 属性)。

B. 事件星型网络 (Person to Event) 
- [:参与] (Person -> Event): 必须在 properties 中包含以下两个核心字段：
  1. role: 具体的自然语言角色描述 (如 "首倡支持", "被斩首", "统帅")
  2. stance: 极性立场，【严格限制】只能从这两个词中二选一："支持" 或 "反对"。

OUTPUT JSON FORMAT EXACTLY AS BELOW:
{{
  "entities": [
    {{"type": "Person", "standard_name": "裴炎", "aliases": ["中书令", "字子隆"]}},
    {{"type": "Event", "standard_name": "诛杀裴炎", "aliases": []}}
  ],
  "triplets": [
    {{
      "head": "武则天",
      "relation": "迫害",
      "tail": "裴炎",
      "properties": {{
        "method": "斩首",
        "evidence": "时中书令裴炎与太后理有异同，太后怒，斩炎于洛阳。",
        "source": "{full_source}",
        "ad_year": 684
      }}
    }},
    {{
      "head": "裴炎",
      "relation": "参与",
      "tail": "诛杀裴炎",
      "properties": {{
        "role": "被害者",
        "stance": "反对",
        "evidence": "斩炎于洛阳。",
        "source": "{full_source}",
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
    sample_text = "冬十月，丁卯，诏废王皇后、萧淑妃为庶人，皆囚之。己巳，诏立武昭仪为皇后。初，帝将立昭仪，长孙无忌、褚遂良固谏，李义府叩阁上表请立之。"
    
    print("🤖 正在呼叫 Qwen 进行 V2.0 极性知识抽取...\n")
    result = extractor.extract(sample_text, source_book="资治通鉴")
    print(json.dumps(result, ensure_ascii=False, indent=2))