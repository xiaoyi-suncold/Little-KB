"""关键词抽取：不依赖分词词典，用字级 n-gram + 左右熵判断「像不像一个词」。

思路：
  1. 统计 2~4 字组合的出现次数；
  2. 一个真正的词，左右邻字通常很多样（左右熵高）；
     跨词边界的碎片（"件夹"、"识库"、"使用指"）往往一侧邻字固定，熵接近 0；
  3. 按频次排序，去掉互为子串的候选。

足够轻，也足够把每篇文档的主题词挑出来，喂给知识图谱。
"""

from __future__ import annotations

import math
import re
from collections import Counter

# 强停用字：出现在组合里就丢弃（"上/下/中" 不在其中，否则会误杀"上传""中文"）
CJK_STOP = set("的了是在和有这那就都也还又很与及或而不没把被让给从到对为以之其"
               "我你他她它们吗呢吧啊哦嗯么个些着过地得所而且并但却更最太")

# 组合尾字黑名单：以这些字结尾的二元组基本是跨词边界的碎片
TAIL_STOP = set("的了和与及或在是为以等中时后前内外上下们者")

# 常见虚词组合
CJK_STOP_WORDS = {
    "无法", "可以", "我们", "他们", "一个", "这个", "那个", "所以", "但是", "如果",
    "因为", "以及", "并且", "或者", "不是", "没有", "就是", "还是", "这样", "那样",
    "需要", "可能", "应该", "已经", "正在", "通过", "进行", "其中", "其他", "任何",
    "所有", "一些", "什么", "怎么", "如何", "以上", "以下", "同时", "然后", "目前",
    "由于", "因此", "事情", "东西", "时候", "地方", "方面", "问题", "情况", "公司",
    "大家", "自己", "这种", "那种", "之后", "之前", "以后", "以前", "一下", "必须",
    "主要", "直接", "自动", "默认", "一般", "基本", "相关", "区别", "支持",
}

EN_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "are", "was", "were",
    "you", "not", "but", "have", "has", "had", "can", "will", "all", "our",
    "its", "use", "using", "used", "into", "then", "than", "there", "their",
    "what", "when", "which", "who", "how", "why", "also", "such", "each",
    "more", "most", "some", "any", "may", "one", "two", "out", "own", "per",
    "http", "https", "www", "com", "json", "true", "false", "none", "null",
    "class", "return", "import", "def", "self", "const", "let", "var", "string",
    "number", "object", "array", "value", "values", "name", "node", "text",
}

CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
EN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#-]{3,}")
HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$", re.M)
BOUNDARY = "\u0000"

MIN_ENTROPY = 0.45
MAX_HEADING_LEN = 24


def _entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if not total:
        return 0.0
    total = float(total)
    return -sum((c / total) * math.log(c / total) for c in counter.values())


def _collect(text: str) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for run in CJK_RUN.findall(text):
        length = len(run)
        for n in (2, 3, 4):
            for i in range(length - n + 1):
                gram = run[i : i + n]
                if gram in CJK_STOP_WORDS:
                    continue
                if any(ch in CJK_STOP for ch in gram):
                    continue
                record = stats.get(gram)
                if record is None:
                    record = stats[gram] = {"freq": 0, "left": Counter(), "right": Counter()}
                record["freq"] += 1
                if i > 0:
                    record["left"][run[i - 1]] += 1
                if i + n < length:
                    record["right"][run[i + n]] += 1
    return stats


GENERIC_HEADINGS = {
    "目标", "维护", "读取", "写入", "说明", "简介", "前言", "背景", "概述", "总结",
    "下一步", "下一步可以做什么", "附录", "参考", "示例", "用法", "安装", "结语",
    "为什么", "怎么做", "是什么", "特性", "功能", "注意", "备注", "更新", "版本",
}


def extract_terms(
    text: str,
    limit: int = 6,
    exclude: set[str] | None = None,
) -> list[tuple[str, int]]:
    """返回 [(词, 频次)]，按信息量从高到低，彼此不互为子串。

    标题（Markdown heading）是作者亲手写的概念，质量最高，优先入选但最多占 3 个；
    字级 n-gram 补充剩下的位置。
    """
    if not text:
        return []

    skip = {item.strip().lower() for item in (exclude or set()) if item}
    headings = [h.strip() for h in HEADING_LINE.findall(text)]
    stats = _collect(text)

    candidates: list[tuple[float, int, str, bool]] = []

    seen_heading = 0
    for heading in headings:
        clean = heading.strip("`*_ ").strip()
        if not clean or len(clean) > MAX_HEADING_LEN:
            continue
        if clean in GENERIC_HEADINGS or clean in CJK_STOP_WORDS:
            continue
        if clean.lower() in skip:
            continue
        seen_heading += 1
        if seen_heading > 3:
            break
        candidates.append((9.0 - len(clean) * 0.1, 2, clean, True))

    for gram, record in stats.items():
        freq = record["freq"]
        if freq < 2:
            continue
        if min(_entropy(record["left"]), _entropy(record["right"])) < MIN_ENTROPY:
            continue
        if len(gram) == 2 and gram[1] in TAIL_STOP:
            continue
        if gram.lower() in skip:
            continue
        candidates.append((float(freq) * (1.25 if len(gram) >= 3 else 1.0), freq, gram, False))

    for word in EN_WORD.findall(text):
        lowered = word.lower().strip("-+#")
        if len(lowered) < 4 or lowered in EN_STOP or lowered in skip:
            continue
        candidates.append((float(len(lowered)) * 0.9, 1, lowered, False))

    candidates.sort(key=lambda item: (-item[0], -len(item[2]), item[2]))

    chosen: list[tuple[str, int]] = []
    for weight, freq, term, _is_heading in candidates:
        if any(term in picked or picked in term for picked, _ in chosen):
            continue
        chosen.append((term, max(freq, 1)))
        if len(chosen) >= limit:
            break
    return chosen
