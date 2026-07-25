#!/usr/bin/env python3
"""
Fetch tophub.today/c/finance, parse all platform topics,
cluster similar topics by cross-platform coverage, output JSON.
Designed for GitHub Actions cloud environment.

Clustering strategy: Dynamic IDF-weighted keyword overlap.
No hardcoded entity lists — words are weighted by how rare they are
across all titles, so distinctive terms (company names, specific events)
automatically get high similarity scores.
"""
import urllib.request
import re
import json
import os
import sys
import math
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

# Stopwords: common Chinese function words and punctuation
STOPWORDS = {'的', '了', '是', '在', '和', '与', '或', '等', '也', '都', '不', '为', '对',
             '由', '从', '到', '被', '将', '已', '可', '能', '会', '这', '那', '其', '之',
             '一', '个', '上', '下', '中', '大', '小', '有', '无', '看', '说', '做', '来',
             '去', '给', '让', '使', '用', '要', '想', '需', '应', '该', '此', '些', '即',
             '则', '而', '但', '且', '如', '若', '因', '所', '以', '于', '向', '至', '当',
             '再', '又', '才', '只', '就', '还', '更', '最', '很', '太', '非', '常', '十',
             '百', '千', '万', '亿', '元', '点', '%', '丨', '｜', '—', '·', '：', '。', '，',
             '、', '？', '！', '"', '"', ''', ''', '（', '）', '(', ')', '[', ']', '《', '》',
             # Common generic financial words that are too broad for matching
             '什么', '怎么', '为什么', '如何', '可以', '可能', '已经', '继续', '还是', '不是',
             '这个', '一个', '没有', '只有', '就是', '还是', '其实', '真的',
             }

# Very common words to exclude from matching (appear in too many titles to be distinctive)
# These will also be filtered by the dynamic IDF threshold
COMMON_FINANCE_WORDS = {
    'A股', '沪指', '创业板', '科创板', '港股', '恒指', '美股', '纳指', '标普', '道指',
    '市场', '股市', '板块', '行情', '收盘', '盘前', '盘后', '早报', '收评',
    '投资', '交易', '资金', '利好', '利空', '下跌', '上涨', '暴涨', '暴跌',
    '公告', '通知', '新闻', '热点', '话题',
}

# Try to import jieba
try:
    import jieba
    import jieba.analyse
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


def segment_title(title):
    """Segment title into meaningful words using jieba.
    Returns a set of 2+ character words, excluding stopwords."""
    words = set()
    if JIEBA_AVAILABLE:
        try:
            for w in jieba.cut(title, cut_all=False):
                w = w.strip()
                if len(w) >= 2 and w not in STOPWORDS:
                    words.add(w)
        except Exception:
            pass

    if not words:
        # Fallback: extract character pairs
        chars = [c for c in title if "\u4e00" <= c <= "\u9fff"]
        for i in range(len(chars) - 1):
            pair = chars[i] + chars[i + 1]
            if pair not in STOPWORDS:
                words.add(pair)

    return words


def extract_numbers_with_units(title):
    """Extract numbers with units (e.g., '51.79亿', '2.4亿', '3800点', '42%').
    Only numbers with units are meaningful for event matching."""
    numbers = set()
    for m in re.finditer(r'(\d+\.?\d*)\s*(万亿|千亿|百亿|十亿|亿|万|千|百|元|点|%|倍|次|个|家|人|名|条|亿股|万股)', title):
        num = m.group(1)
        unit = m.group(2)
        if len(num) >= 2 or unit in ('亿', '万', '万亿', '%', '倍'):
            numbers.add(f"{num}{unit}")
    return numbers


def extract_key_substrings(title, min_len=4):
    """Extract distinctive substrings from title.
    Only 4+ character contiguous Chinese sequences — these are likely
    entity names (company names, place names, specific phrases).
    Shorter sequences generate too much noise."""
    substrings = set()
    for m in re.finditer(r'[\u4e00-\u9fff]{4,}', title):
        s = m.group()
        if len(s) <= 7:
            substrings.add(s)
        else:
            # For long sequences, extract 4-5 char windows
            for i in range(len(s) - 3):
                substrings.add(s[i:i+4])
            for i in range(len(s) - 4):
                substrings.add(s[i:i+5])
    return substrings


def clusterTopics(blocks, similarity_threshold=0.25):
    """
    Cluster topics using dynamic IDF-weighted keyword overlap.

    Algorithm:
    1. Segment all titles into words using jieba
    2. Compute IDF (inverse document frequency) for each word
    3. Filter out very common words (appear in >25% of titles)
    4. For each pair of titles from different platforms:
       - Require a "strong signal": 2+ shared distinctive words,
         OR 1 shared 3+ char word with high IDF (>3.5),
         OR 1 shared 4+ char substring (entity name)
       - Compute weighted overlap: sum(IDF of shared words) / min(total IDF weight)
       - Add bonus for shared numbers-with-units and substrings
    5. Merge pairs above threshold using union-find

    The strong signal requirement prevents chain merges through generic words
    like "下周" or "重磅", while still allowing entity-based matches like
    "宁德时代" or "霍尔木兹" to trigger merges.
    """
    # Step 1: Collect all items with segmented words
    items = []
    for block in blocks:
        for t in block["topics"]:
            words = segment_title(t["title"])
            numbers = extract_numbers_with_units(t["title"])
            substrings = extract_key_substrings(t["title"])
            items.append({
                "platform": block["platform_name"],
                "title": t["title"],
                "url": t["url"],
                "rank": t["rank"],
                "heat": t["heat"],
                "words": words,
                "numbers": numbers,
                "substrings": substrings,
            })

    n = len(items)

    # Step 2: Compute document frequency and IDF for each word
    df = defaultdict(int)
    for item in items:
        for w in item["words"]:
            df[w] += 1

    # IDF: log(N / df), with smoothing
    idf = {w: math.log(n / max(df[w], 1)) for w in df}

    # Step 3: Filter out very common words (appear in >25% of titles)
    common_cutoff = max(n * 0.25, 5)
    distinctive_words = {w for w, d in df.items() if d <= common_cutoff}
    distinctive_words -= COMMON_FINANCE_WORDS

    # Precompute IDF-weighted word vectors for each item
    for item in items:
        item["weighted_words"] = {w: idf.get(w, 0) for w in item["words"] if w in distinctive_words}
        item["total_weight"] = sum(item["weighted_words"].values())

    # Step 4: Union-Find
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

    # Step 5: Compare all pairs from different platforms
    for i in range(n):
        if items[i]["total_weight"] == 0:
            continue
        for j in range(i + 1, n):
            if items[i]["platform"] == items[j]["platform"]:
                continue
            if items[j]["total_weight"] == 0:
                continue

            # Exact title match
            if items[i]["title"].strip() == items[j]["title"].strip():
                union(i, j)
                continue

            # Shared distinctive words
            shared_words = set(items[i]["weighted_words"].keys()) & set(items[j]["weighted_words"].keys())

            # Shared 4+ char substrings (entity names)
            shared_sub = items[i]["substrings"] & items[j]["substrings"]
            strong_subs = {s for s in shared_sub if len(s) >= 4}

            # Strong signal check: must have enough evidence to merge
            # Option A: 2+ shared distinctive words
            # Option B: 1 shared 3+ char word with high IDF (>3.5) — catches "宁德时代", "携程"
            # Option C: 1 shared 4+ char substring — catches jieba segmentation differences
            has_strong_word = any(
                len(w) >= 3 and idf.get(w, 0) > 3.0 for w in shared_words
            )

            if len(shared_words) < 2 and not has_strong_word and not strong_subs:
                continue

            # Strong entity override: if two titles share a 3+ char word with
            # high IDF AND at least one other distinctive word, force merge.
            # This handles cases where one title has many irrelevant distinctive
            # words (e.g., "LIVE", "Day") that dilute the overlap coefficient.
            if has_strong_word and len(shared_words) >= 2:
                union(i, j)
                continue

            shared_weight = sum(items[i]["weighted_words"][w] for w in shared_words)

            # Weighted overlap coefficient
            min_weight = min(items[i]["total_weight"], items[j]["total_weight"])
            sim = shared_weight / min_weight if min_weight > 0 else 0

            # Substring bonus: shared 4+ char entity names
            if strong_subs:
                sim += 0.12 * min(len(strong_subs), 3)

            # Number bonus
            shared_num = items[i]["numbers"] & items[j]["numbers"]
            if shared_num:
                sim += 0.08 * len(shared_num)

            if sim >= similarity_threshold:
                union(i, j)

    # Step 6: Build cluster summaries
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
    print("Clustering similar topics (IDF-weighted, threshold=0.25)...")
    clusters = clusterTopics(blocks)
    print(f"Formed {len(clusters)} clusters")

    # Count multi-platform clusters
    multi = [c for c in clusters if c["cover_count"] >= 2]
    single = [c for c in clusters if c["cover_count"] == 1]
    print(f"  Multi-platform clusters: {len(multi)}")
    print(f"  Single-platform clusters: {len(single)}")

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
