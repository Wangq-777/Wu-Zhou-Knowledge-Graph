import re
import time
import requests
from pathlib import Path
from opencc import OpenCC  # 引入简繁转换

class HistoricalTextScraper:
    def __init__(self, base_dir="data/raw"):
        self.base_dir = Path(base_dir)
        self.sources = ["zztj", "jts", "xts"]
        # 初始化转换器：t2s 代表 Traditional to Simplified
        self.cc = OpenCC('t2s')
        
        for source in self.sources:
            (self.base_dir / source).mkdir(parents=True, exist_ok=True)

    def fetch_via_api(self, title):
        """调用维基官方 API (保持不变，确保 User-Agent 正确)"""
        print(f"📡 正在通过 API 请求纯文本: {title}")
        url = "https://zh.wikisource.org/w/api.php"
        headers = {
            'User-Agent': 'WuZhou-Power-GraphRAG/1.0 (Academic Research Project)'
        }
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": "true",
            "titles": title,
            "format": "json",
            "redirects": 1
        }
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_info in pages.items():
                if page_id == "-1": return ""
                return page_info.get("extract", "")
        except Exception as e:
            print(f"❌ API 请求失败: {e}")
            return ""

    def clean_text(self, text):
        """核心清洗逻辑：加入简繁转换"""
        if not text:
            return ""
            
        # 1. 整体进行繁转简处理，解决“武則天”问题
        text = self.cc.convert(text)
        
        cleaned_lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('=') and line.endswith('='): continue
            
            # 2. 剔除注疏、括号、校勘记
            line = re.sub(r'（.*?）', '', line) 
            line = re.sub(r'\(.*?\)', '', line)
            line = re.sub(r'〔.*?〕', '', line)
            
            # 3. 规范标点与空白
            line = line.replace(',', '，').replace('.', '。').replace(':', '：')
            line = re.sub(r'\s+', '', line)
            
            if len(line) > 5:
                cleaned_lines.append(line)
                
        return "\n".join(cleaned_lines)

    def scrape_and_save(self, book_type, volume_name, title):
        raw_text = self.fetch_via_api(title)
        clean_text = self.clean_text(raw_text)
        
        file_path = self.base_dir / book_type / f"{volume_name}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(clean_text)
            
        print(f"✅ 成功保存(已转简体): {file_path} (共 {len(clean_text)} 字)\n")
        time.sleep(1)

# ================= 🚀 执行测试 =================
if __name__ == "__main__":
    scraper = HistoricalTextScraper()

    # 注意：这里不再传入 URL，而是直接传入维基内部的“标准词条名”
    # 1. 批量生成《资治通鉴》卷199至210（核心武周时期）
    zztj_tasks = [
        {"book": "zztj", "volume": f"ZZTJ_{v}", "title": f"資治通鑑/卷{v}"}
        for v in range(199, 211)
    ]
    
    # 2. 定向抓取《两唐书》中的本纪与关键列传
    biography_tasks = [
        # 旧唐书
        {"book": "jts", "volume": "JTS_006_ZZT", "title": "舊唐書/卷6"},      # 则天皇后本纪
        {"book": "jts", "volume": "JTS_183_WQS", "title": "舊唐書/卷183"},    # 外戚传（武氏家族）
        {"book": "jts", "volume": "JTS_186_KL",  "title": "舊唐書/卷186"},    # 酷吏传（来俊臣等）
        
        # 新唐书
        {"book": "xts", "volume": "XTS_004_ZZT", "title": "新唐書/卷004"},    # 则天皇后本纪
        {"book": "xts", "volume": "XTS_076_HH",  "title": "新唐書/卷076"},    # 皇后传（武后列传）
        {"book": "xts", "volume": "XTS_209_KL",  "title": "新唐書/卷209"}     # 酷吏传
    ]

    all_tasks = zztj_tasks + biography_tasks

    print(f"🚀 开始全量采集武周史料，共计 {len(all_tasks)} 个卷册...")
    for item in all_tasks:
        try:
            scraper.scrape_and_save(item["book"], item["volume"], item["title"])
        except Exception as e:
            print(f"⚠️ 卷册 {item['title']} 采集跳过: {e}")
            
    print("🎉 武周全量语料库（简体归一化）构建完毕！")