#!/usr/bin/env python3
"""
Fetch tophub.today/c/finance, parse all platform topics,
cluster similar topics by cross-platform coverage, output JSON.
Designed for GitHub Actions cloud environment.
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

# Try to import jieba, fall back to character-level tokenization
try:
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

        # Platform name: <div class="cc-cd-lb">... <span>平台名</span></div>
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


def extract_keywords(title, topK=8):
    """Extract keywords from a title using jieba if available, else character-level."""
    if JIEBA_AVAILABLE:
        try:
            keywords = jieba.analyse.extract_tags(title, topK=topK, withWeight=False)
        except Exception:
            keywords = []
    else:
        keywords = []
    
    if len(keywords) < 3:
        chars = [c for c in title if "\u4e00" <= c <= "\u9fff"]
        keywords = list(set(chars))[:topK]
    return keywords


def title_similarity(title1, title2, kw1=None, kw2=None):
    if kw1 is None:
        kw1 = set(extract_keywords(title1))
    if kw2 is None:
        kw2 = set(extract_keywords(title2))
    if not kw1 or not kw2:
        return 0.0
    inter = len(kw1 & kw2)
    union = len(kw1 | kw2)
    return inter / union if union > 0 else 0.0


def cluster_topics(blocks, similarity_threshold=0.25):
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
            if items[i]["platform"] == items[j]["platform"]:
                continue
            sim = title_similarity(items[i]["title"], items[j]["title"], items[i]["keywords"], items[j]["keywords"])
            if sim >= similarity_threshold:
                union(i, j)

    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(items[i])

    results = []
    for cluster_id, members in clusters.items():
        platforms = set(m["platform"] for m in members)
        total_rank = sum(m["rank"] for m in members)
        score = len(platforms) * 100 - (total_rank / len(members))
        best_member = min(members, key=lambda x: x["rank"])

        platform_best = {}
        for m in members:
            if m["platform"] not in platform_best or m["rank"] < platform_best[m["platform"]]["rank"]:
                platform_best[m["platform"]] = m

        results.append({
            "cluster_id": cluster_id,
            "representative_title": best_member["title"],
            "cover_count": len(platforms),
            "platforms": sorted(platforms),
            "score": score,
            "total_mentions": len(members),
            "avg_rank": round(total_rank / len(members), 1),
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
    print(f"Parsed {len(blocks)} platforms:")
    for b in blocks:
        print(f"  {b['platform_name']} ({b['platform_raw']}): {len(b['topics'])} topics")

    total_topics = sum(len(b["topics"]) for b in blocks)
    print(f"\nTotal topics: {total_topics}")

    print("Clustering similar topics...")
    clusters = cluster_topics(blocks)
    print(f"Formed {len(clusters)} clusters")

    top_clusters = clusters[:15]

    output_path = os.path.join(output_dir, f"tophub_clusters_{TODAY}.json")
    meta_path = os.path.join(output_dir, f"tophub_meta_{TODAY}.json")

    cluster_data = {
        "date": TODAY,
        "period": PERIOD,
        "platforms": [b["platform_name"] for b in blocks],
        "total_topics": total_topics,
        "clusters": top_clusters,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cluster_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved clusters to {output_path}")

    # Also save metadata separately for the report generator
    meta = {
        "date": TODAY,
        "period": PERIOD,
        "platform_count": len(blocks),
        "total_topics": total_topics,
        "platform_list": [b["platform_name"] for b in blocks],
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("\nTop 15 clusters:")
    for i, c in enumerate(top_clusters, 1):
        print(f"{i:2d}. [{c['cover_count']} platforms] {c['representative_title']}")
        print(f"     Platforms: {', '.join(c['platforms'])}")

    # Save cluster path as env var for next step
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"CLUSTER_JSON={output_path}\n")
            f.write(f"REPORT_DATE={TODAY}\n")
            f.write(f"REPORT_PERIOD={PERIOD}\n")

    print(f"\n✅ Done. Date: {TODAY}, Period: {PERIOD}")


if __name__ == "__main__":
    main()
