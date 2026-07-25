#!/usr/bin/env python3
"""
Fetch tophub.today/c/finance, parse all platform topics,
cluster similar topics by cross-platform coverage, output JSON.
Designed for GitHub Actions cloud environment.

Clustering strategy: multi-signal similarity combining
keyword Jaccard + entity overlap + key-phrase matching.
"""
import urllib.request
import re
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

TOPHUB_URL = "https://tophub.today/c/finance"

# Beijing timezone
def beijing_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)

TODAY = beijing_now().strftime("%Y-%m-%d")
PERIOD = "上午" if beijing_now().hour < 12 else "下午"

# Platform name normalization
PLATFORM_NORM = {
    "第一财经": "第一财经",
    "第一财经商业数据中心": "CBNData",
    "华尔街见闻": "华尔街见闻",
    "新浪财经": "新浪财经",
    "21财经": "21财经",
    "格隆汇": "格隆汇",
    "股吧": "股吧",
    "雪球": "雪球",
    "集思录": "集思录",
    "FT中文网": "FT中文网",
    "CBNData": "CBNData",
    "全网热榜": "全网热榜",
}

# Strong entities: specific company names, people, products
# These are unique enough to indicate "same event" when shared
STRONG_ENTITIES = {
    "宁德时代", "比亚迪", "携程", "中际旭创", "苹果", "特斯拉", "英伟达",
    "谷歌", "微软", "台积电", "马斯克", "SpaceX", "星舰", "恒瑞医药", "药明康德",
    "万科", "碧桂园", "保利", "拼多多", "美团", "京东", "阿里巴巴",
    "方星海", "证监会", "OpenAI", "高通", "长鑫", "长鑫科技",
    "默沙东", "宜家", "川投能源", "闻泰科技", "中兴通讯",
    "汇金", "国新", "诚通", "社保基金",
}

# Weak entities: common financial terms - useful for keyword extraction
# but NOT sufficient alone to merge two topics
WEAK_ENTITIES = {
    "央行", "美联储", "市场监管总局", "国家队",
    "碳酸锂", "锂电池", "光伏", "风电", "储能", "新能源",
    "A股", "沪指", "创业板", "科创板", "港股", "恒指",
    "美股", "纳指", "标普", "道指", "日经",
    "原油", "黄金", "白银", "铜", "铁矿石",
    "逆回购", "隔夜逆回购", "MLF", "LPR", "降准", "降息", "加息",
    "IPO", "财报", "季报", "年报", "中报",
    "可转债", "债券", "ETF", "基金",
    "半导体", "芯片", "光模块", "AI", "人工智能",
    "房地产", "楼市", "房价",
    "人民币", "美元", "汇率", "欧元", "日元",
    "OPEC", "中东", "伊朗", "以色列", "乌克兰", "美伊",
    "反垄断", "垄断", "处罚", "罚没",
    "回购", "增持", "减持", "分红", "派息",
    "TACO指数", "WAIC", "B站",
}

# All entities combined for jieba dictionary
ALL_ENTITIES = STRONG_ENTITIES | WEAK_ENTITIES

# Stopwords for phrase extraction
STOPWORDS = {'的', '了', '是', '在', '和', '与', '或', '等', '也', '都', '不', '为', '对',
             '由', '从', '到', '被', '将', '已', '可', '能', '会', '这', '那', '其', '之',
             '一', '个', '上', '下', '中', '大', '小', '有', '无', '看', '说', '做', '来',
             '去', '给', '让', '使', '用', '要', '想', '需', '应', '该', '此', '些', '即',
             '则', '而', '但', '且', '如', '若', '因', '所', '以', '于', '向', '至', '当',
             '再', '又', '才', '只', '就', '还', '更', '最', '很', '太', '非', '常', '十',
             '百', '千', '万', '亿', '元', '点', '%', '丨', '｜', '—', '·', '：', '。', '，',
             '、', '？', '！', '"', '"', ''', ''', '（', '）', '(', ')', '[', ']', '《', '》'}

# Try to import jieba
try:
    import jieba
    import jieba.analyse
    for entity in ALL_ENTITIES:
        jieba.add_word(entity)
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False


def normalize_platform(raw_name):
    raw_name = raw_name.strip()
    for key, val in PLATFORM_NORM.items():
        if key in raw_name:
            return val
    return raw_name


def fetch_html():
    req = urllib.request.Request(
        TOPHUB_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_platform_blocks(html):
    blocks = []
    pos = 0
    while True:
        start_tag = '<div class="cc-cd" id="'
        idx = html.find(start_tag, pos)
        if idx == -1:
            break
        node_id_start = idx + len(start_tag)
        node_id_end = html.find('"', node_id_start)
        node_id = html[node_id_start:node_id_end]

        next_block = html.find('<div class="cc-cd" id="', idx + 100)
        end = next_block if next_block != -1 else len(html)
        block_html = html[idx:end]

        pname = None
        lb_m = re.search(r'<div class="cc-cd-lb">(.*?)</div>', block_html, re.DOTALL)
        if lb_m:
            inner = lb_m.group(1)
            text = re.sub(r'<img[^>]*>', '', inner).strip()
            text = re.sub(r'<[^>]+>', '', text).strip()
            if text:
                pname = text

        if not pname:
            alt_m = re.search(r'alt="([^"]+)"', block_html)
            if alt_m:
                pname = alt_m.group(1).strip()

        topics = []
        for a_m in re.finditer(
            r'<a href="([^"]+)"[^>]*>\s*<div[^>]*>\s*<span[^>]*>\s*(\d+)\s*</span>\s*<span class="t">([^<]+)</span>\s*<span class="e">([^<]*)</span>',
            block_html,
        ):
            url = a_m.group(1)
            rank = a_m.group(2)
            title = a_m.group(3).strip()
            heat = a_m.group(4).strip()
            if title and url and title != pname and len(title) > 3:
                topics.append({
                    "title": title,
                    "url": url if url.startswith("http") else "https://tophub.today" + url,
                    "rank": int(rank),
                    "heat": heat,
                })

        if pname and topics:
            norm_name = normalize_platform(pname)
            blocks.append({
                "node_id": node_id,
                "platform_name": norm_name,
                "platform_raw": pname,
                "topics": topics,
            })

        pos = end

    return blocks


def extract_keywords(title, topK=10):
    """Extract keywords using jieba TF-IDF."""
    keywords = []
    if JIEBA_AVAILABLE:
        try:
            keywords = jieba.analyse.extract_tags(title, topK=topK, withWeight=False)
        except Exception:
            keywords = []

    if len(keywords) < 3:
        keywords = []
        for entity in ALL_ENTITIES:
            if entity in title:
                keywords.append(entity)
        for c in title:
            if "\u4e00" <= c <= "\u9fff" and c not in keywords:
                keywords.append(c)
        keywords = keywords[:topK]

    return keywords


def extract_strong_entities(title):
    """Extract strong entities (specific names) from title."""
    entities = set()
    for entity in STRONG_ENTITIES:
        if entity in title:
            entities.add(entity)
    return entities


def extract_weak_entities(title):
    """Extract weak entities (common financial terms) from title."""
    entities = set()
    for entity in WEAK_ENTITIES:
        if entity in title:
            entities.add(entity)
    return entities


def extract_numbers_with_units(title):
    """Extract numbers with units (e.g., '51.79亿', '2.4亿', '3800点', '42%').
    Only numbers with units are meaningful for event matching."""
    numbers = set()
    # Match number + unit patterns
    for m in re.finditer(r'(\d+\.?\d*)\s*(万亿|千亿|百亿|十亿|亿|万|千|百|元|点|%|倍|次|个|家|人|名|条|亿股|万股)', title):
        num = m.group(1)
        unit = m.group(2)
        # Only keep meaningful numbers (avoid single digits without context)
        if len(num) >= 2 or unit in ('亿', '万', '万亿', '%', '倍'):
            numbers.add(f"{num}{unit}")
    return numbers


def extract_key_phrases(title):
    """Extract 2+ char meaningful phrases using jieba."""
    phrases = set()
    if JIEBA_AVAILABLE:
        try:
            words = jieba.cut(title, cut_all=False)
            for w in words:
                w = w.strip()
                if len(w) >= 2 and w not in STOPWORDS:
                    phrases.add(w)
        except Exception:
            pass

    if not phrases:
        chars = [c for c in title if "\u4e00" <= c <= "\u9fff"]
        for i in range(len(chars) - 1):
            pair = chars[i] + chars[i+1]
            if pair not in STOPWORDS:
                phrases.add(pair)

    return phrases


def compute_similarity(item1, item2):
    """
    Multi-signal similarity score.
    Returns a score in [0, 1].

    Signals:
    1. Strong entity overlap (most important): if titles share a specific name
    2. Number-with-unit overlap: if titles share specific figures
    3. Weak entity compound: 2+ shared weak entities = likely same topic
    4. Keyword Jaccard: general keyword overlap
    5. Key phrase overlap: phrase-level similarity
    """
    kw1, kw2 = item1["keywords"], item2["keywords"]
    ent1, ent2 = item1["strong_entities"], item2["strong_entities"]
    weak1, weak2 = item1["weak_entities"], item2["weak_entities"]
    num1, num2 = item1["numbers"], item2["numbers"]
    phr1, phr2 = item1["phrases"], item2["phrases"]

    # Signal 1: Strong entity overlap
    # If both titles mention the same company/person, very likely same event
    ent_inter = ent1 & ent2
    ent_score = 0.0
    if ent_inter:
        ent_score = min(len(ent_inter) * 0.35, 0.7)

    # Signal 2: Number-with-unit overlap
    num_inter = num1 & num2
    num_score = 0.0
    if num_inter:
        num_score = min(len(num_inter) * 0.3, 0.5)

    # Signal 3: Weak entity compound signal
    # 2+ shared weak entities (e.g., "央行" + "逆回购", "美伊" + "原油")
    # indicates same topic even without strong entities
    weak_inter = weak1 & weak2
    weak_score = 0.0
    if len(weak_inter) >= 3:
        weak_score = 0.35
    elif len(weak_inter) >= 2:
        weak_score = 0.25

    # Signal 4: Keyword Jaccard
    kw_inter = len(kw1 & kw2)
    kw_union = len(kw1 | kw2)
    kw_sim = kw_inter / kw_union if kw_union > 0 else 0.0

    # Signal 5: Key phrase overlap
    phr_inter = len(phr1 & phr2)
    phr_union = len(phr1 | phr2)
    phr_sim = phr_inter / phr_union if phr_union > 0 else 0.0

    # Weighted combination
    score = ent_score + num_score + weak_score + 0.15 * kw_sim + 0.15 * phr_sim

    return min(score, 1.0)


def clusterTopics(blocks, similarity_threshold=0.35):
    """
    Cluster topics using multi-signal similarity.
    Threshold 0.35 means: need at least one strong entity match (0.35)
    or a number match (0.3) + some keyword/phrase overlap.

    This prevents merging unrelated topics that just share common words like "A股".
    """
    items = []
    for block in blocks:
        for t in block["topics"]:
            items.append({
                "platform": block["platform_name"],
                "title": t["title"],
                "url": t["url"],
                "rank": t["rank"],
                "heat": t["heat"],
                "keywords": set(extract_keywords(t["title"])),
                "strong_entities": extract_strong_entities(t["title"]),
                "weak_entities": extract_weak_entities(t["title"]),
                "numbers": extract_numbers_with_units(t["title"]),
                "phrases": extract_key_phrases(t["title"]),
            })

    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            # Skip exact same title
            if items[i]["title"].strip() == items[j]["title"].strip():
                union(i, j)
                continue

            sim = compute_similarity(items[i], items[j])
            if sim >= similarity_threshold:
                union(i, j)

    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(items[i])

    results = []
    for cluster_id, members in clusters.items():
        # Deduplicate: keep best entry per platform
        platform_best = {}
        for m in members:
            if m["platform"] not in platform_best or m["rank"] < platform_best[m["platform"]]["rank"]:
                platform_best[m["platform"]] = m

        platforms = set(platform_best.keys())
        total_rank = sum(m["rank"] for m in platform_best.values())
        score = len(platforms) * 100 - (total_rank / len(platform_best))
        best_member = min(members, key=lambda x: x["rank"])

        results.append({
            "cluster_id": cluster_id,
            "representative_title": best_member["title"],
            "cover_count": len(platforms),
            "platforms": sorted(platforms),
            "score": score,
            "total_mentions": len(members),
            "avg_rank": round(total_rank / len(platform_best), 1),
            "sources": [
                {
                    "platform": p,
                    "title": m["title"],
                    "url": m["url"],
                    "rank": m["rank"],
                    "heat": m["heat"],
                }
                for p, m in sorted(platform_best.items())
            ],
            "all_titles": [m["title"] for m in members],
        })

    results.sort(key=lambda x: (-x["cover_count"], -x["score"]))
    return results


def main():
    output_dir = os.environ.get("OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output"))
    os.makedirs(output_dir, exist_ok=True)

    print(f"[{TODAY} {PERIOD}] Fetching {TOPHUB_URL} ...")
    html = fetch_html()
    print(f"HTML size: {len(html)} bytes")

    print("Parsing platform blocks...")
    blocks = parse_platform_blocks(html)
    print(f"Parsed {len(blocks)} platform blocks:")
    for b in blocks:
        print(f"  {b['platform_name']} ({b['platform_raw']}): {len(b['topics'])} topics")

    total_topics = sum(len(b["topics"]) for b in blocks)
    print(f"\nTotal topics: {total_topics}")

    print(f"jieba available: {JIEBA_AVAILABLE}")
    print("Clustering similar topics (multi-signal, threshold=0.35)...")
    clusters = clusterTopics(blocks)
    print(f"Formed {len(clusters)} clusters")

    top_clusters = clusters[:15]

    output_path = os.path.join(output_dir, f"tophub_clusters_{TODAY}.json")
    meta_path = os.path.join(output_dir, f"tophub_meta_{TODAY}.json")

    cluster_data = {
        "date": TODAY,
        "period": PERIOD,
        "platforms": list(set(b["platform_name"] for b in blocks)),
        "total_topics": total_topics,
        "clusters": top_clusters,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cluster_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved clusters to {output_path}")

    meta = {
        "date": TODAY,
        "period": PERIOD,
        "platform_count": len(set(b["platform_name"] for b in blocks)),
        "total_topics": total_topics,
        "platform_list": list(set(b["platform_name"] for b in blocks)),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("\nTop 15 clusters:")
    for i, c in enumerate(top_clusters, 1):
        print(f"{i:2d}. [{c['cover_count']} platforms, {c['total_mentions']} mentions] {c['representative_title'][:65]}")
        print(f"     Platforms: {', '.join(c['platforms'])}")
        if c['total_mentions'] > 1:
            for t in c['all_titles'][:5]:
                print(f"       - {t[:70]}")
        print()

    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"CLUSTER_JSON={output_path}\n")
            f.write(f"REPORT_DATE={TODAY}\n")
            f.write(f"REPORT_PERIOD={PERIOD}\n")

    print(f"\nDone. Date: {TODAY}, Period: {PERIOD}")


if __name__ == "__main__":
    main()
