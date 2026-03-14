import os
import re
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from opencc import OpenCC

# 请确保路径与你的项目结构一致
from src.kg_builder.llm_extractor import QwenExtractor
from src.kg_builder.neo4j_writer import Neo4jGraphWriter

# 初始化全局简繁转换器
cc = OpenCC('t2s')

class WuZhouFullPipeline:
    def __init__(self, data_dir="data/raw", max_workers=5):
        self.data_dir = Path(data_dir)
        self.max_workers = max_workers
        self.extractor = QwenExtractor()
        self.writer = Neo4jGraphWriter()
        
        # 创建一个错误日志目录，用于保存写库失败的 JSON（防数据丢失）
        self.error_log_dir = Path("data/error_logs")
        self.error_log_dir.mkdir(parents=True, exist_ok=True)
        
    def normalize_text(self, text):
        """实体缝合预处理：强制简繁转换与去空格"""
        return cc.convert(text).strip()

    def split_text(self, text, chunk_size=450):
        """语义切块"""
        text = self.normalize_text(text)
        sentences = re.split(r'(。|！|？|\n)', text)
        chunks, current = [], ""
        for i in range(0, len(sentences)-1, 2):
            part = sentences[i] + sentences[i+1]
            if len(current) + len(part) <= chunk_size:
                current += part
            else:
                if current: chunks.append(current)
                current = part
        if current: chunks.append(current)
        return chunks

    def run_task(self, chunk, source_book, volume_name):
        """执行单个块的抽取与注入"""
        try:
            # 👑 核心修改：分离传入 source_book 和 volume，让 extractor 内部拼接 full_source
            result = self.extractor.extract(text_chunk=chunk, source_book=source_book, volume=volume_name)
            
            if result and (result.get("entities") or result.get("triplets")):
                try:
                    # 尝试写入图数据库
                    self.writer.write_graph_data(result)
                    return True
                except Exception as write_err:
                    # 如果写库失败，将 API 抽取出来的珍贵数据存在本地
                    error_file = self.error_log_dir / f"fail_{source_book}_{volume_name}_{hash(chunk)}.json"
                    with open(error_file, 'w', encoding='utf-8') as f:
                        json.dump(result, f, ensure_ascii=False)
                    print(f"\n⚠️ 写库失败，数据已抢救至: {error_file}")
                    return False
        except Exception as e:
            print(f"\n❌ API 抽取严重异常 [{volume_name}]: {e}")
        return False

    def start(self):
        print("🚀 开启全量武周图谱构建 (时空演变 & 冲突存证模式)...")
        
        all_tasks = []
        # 注意文件夹名称必须与这里的一致
        book_map = {"zztj": "资治通鉴", "jts": "旧唐书", "xts": "新唐书"}

        # 1. 扫描所有全量爬取的卷册
        for folder in self.data_dir.iterdir():
            if not folder.is_dir() or folder.name not in book_map:
                continue
            
            source_name = book_map[folder.name]
            for file_path in folder.glob("*.txt"):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    chunks = self.split_text(content)
                    for c in chunks:
                        if len(c.strip()) > 10: # 过滤掉太短的无意义分块
                            all_tasks.append({
                                "chunk": c,
                                "source": source_name,
                                "volume": file_path.stem # 例如 "卷二百零三"
                            })

        print(f"📊 待处理文本块总数: {len(all_tasks)}")
        if len(all_tasks) == 0:
            print("⚠️ 未找到任何文本数据，请检查 data/raw 目录结构。")
            return

        # 2. 多线程并行处理
        success = 0
        # 使用 tqdm 渲染进度条
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self.run_task, t['chunk'], t['source'], t['volume']) 
                for t in all_tasks
            ]
            for f in tqdm(as_completed(futures), total=len(all_tasks), desc="图谱构建进度"):
                if f.result(): success += 1

        self.writer.close()
        print(f"\n✅ 抽取完成！成功处理 {success}/{len(all_tasks)} 个区块。")
        print("💡 下一步：可以启动后端服务器，在前端大屏观察带有时间轴的历史图谱了！")

if __name__ == "__main__":
    pipeline = WuZhouFullPipeline(max_workers=5) # 建议先设置为 3-5 观察 API 限流情况
    pipeline.start()