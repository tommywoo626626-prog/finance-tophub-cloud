#!/usr/bin/env python3
"""
Generate TOP 10 financial hot topics HTML report from clustered JSON data.
Uses weighted keyword-based category matching for accurate insight generation.
Designed for GitHub Actions cloud environment.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

# Platform display names
PLATFORM_ALIAS = {
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

# Topic category rules with WEIGHTED keywords
# weight=3: entity-specific (company/product name) — strongest signal
# weight=2: domain-specific term — moderate signal
# weight=1: generic sentiment/descriptor — weak signal, only additive
CATEGORY_RULES = [
    {
        "keywords": {
            "国家队": 3, "汇金": 3, "国新": 3, "诚通": 3,
            "社保基金": 3, "央企增持": 2, "回购潮": 2,
            "救市": 2, "护盘": 2, "增持": 1,
        },
        "category": "政策托底",
        "insight_tpl": "“国家队”或央企再次出手，信号意义不可忽视。市场在问：是短期托底还是长期布局？资金量虽然不一定大，但政策意图的传递比实际买入更重要。",
        "angles": [
            "散户视角：国家队出手是“救市信号”吗？回测历史上国家队增持后的市场表现",
            "机构视角：央企增持的资金量和标的分布，哪些行业最受青睐",
            "政策视角：从“窗口指导”到“公开增持”，预期管理方式正在转变",
            "反常识观点：国家队增持不等于市场见底，历史上增持后也曾反复震荡",
            "国际视角：中国“国家队”模式与日本央行买ETF、韩国平准基金的对比",
        ],
    },
    {
        "keywords": {
            "央行": 3, "MLF": 3, "逆回购": 3, "降准": 3, "LPR": 3,
            "美联储": 3, "欧央行": 3, "隔夜逆回购": 3,
            "利率": 2, "降息": 2, "加息": 2,
            "货币政策": 2, "流动性": 2,
        },
        "category": "货币政策",
        "insight_tpl": "货币政策信号出炉，市场对利率走向的预期再次被校准。在汇率、银行息差和实体经济之间，政策正在寻求微妙的平衡。",
        "angles": [
            "散户视角：利率变动对你的房贷、存款、理财有什么直接影响",
            "机构视角：利率不变或调整背后的政策考量——汇率、银行息差还是刺激",
            "国际对比：中美利差和全球利率环境对中国货币政策空间的约束",
            "反常识观点：不降息未必是利空，银行息差保卫战才是当前的头等大事",
            "资产视角：利率环境下，高股息、债券和成长股的逻辑是否成立",
        ],
    },
    {
        "keywords": {
            "A股": 2, "沪指": 3, "深指": 3, "创业板": 3, "科创50": 3,
            "北向资金": 3, "主力资金": 3, "年线": 2, "整数关口": 2,
            "跌破": 2, "反弹": 2, "牛市": 2, "熊市": 2,
            "大跌": 1, "暴涨": 1, "暴跌": 1, "止损": 1, "破位": 1,
        },
        "category": "市场走势",
        "insight_tpl": "A股关键点位引发投资者广泛关注。是技术性调整还是趋势逆转？成交量和资金流向才是判断短期方向的核心变量。",
        "angles": [
            "技术派视角：关键点位跌破或守住的信号意义，历史数据回测",
            "资金视角：今天谁在买、谁在卖？主力资金和北向资金的动向",
            "心理视角：为什么整数关口/年线这么重要？机构考核和量化策略的影响",
            "反常识观点：跌破重要点位不一定是大熊市，历史上多次快速修复",
            "政策视角：市场波动加大时，政策工具箱会不会打开",
        ],
    },
    {
        "keywords": {
            "英伟达": 3, "特斯拉": 3, "苹果": 3, "谷歌": 3, "微软": 3,
            "Meta": 3, "台积电": 3, "马斯克": 3, "SpaceX": 3, "星舰": 3,
            "中际旭创": 3, "光模块": 3, "芯片指数": 3, "纳指": 3, "标普": 3,
            "道指": 3, "美股": 3, "科技股": 3, "AI": 3,
            "人工智能": 2, "半导体": 2, "芯片": 2, "科技巨头": 2,
            "AI宠物": 3, "赛博": 2,
        },
        "category": "外盘科技",
        "insight_tpl": "全球科技股正在经历估值重定价。AI从“讲故事”到“业绩验证”的转换期，任何一个不及预期的财报或政策都可能引发连锁反应。",
        "angles": [
            "美股投资者：科技巨头财报季，AI叙事能否继续支撑估值",
            "A股映射：美股科技股的涨跌如何影响A股AI和半导体板块",
            "产业链视角：从芯片到应用，AI产业链哪个环节最受益",
            "反常识观点：科技巨头即便超预期也可能是“利好出尽”",
            "全球资金流向：美股科技调整是否导致资金向新兴市场回流",
        ],
    },
    {
        "keywords": {
            "原油": 3, "油价": 3, "OPEC": 3, "天然气": 2, "石油": 2,
            "能源": 1, "煤炭": 1,
        },
        "category": "能源市场",
        "insight_tpl": "能源市场的供需博弈进入新阶段。地缘政治、OPEC政策、全球经济预期交织在一起，油价波动率在上升。",
        "angles": [
            "产业链视角：油价变动对化工、航空、物流行业的影响",
            "地缘视角：中东局势对能源供应链的潜在冲击",
            "反常识观点：市场对地缘政治的反应在钝化，油价波动可能没有想象中大",
            "投资视角：能源股和新能源，当下哪个更具性价比",
            "宏观视角：油价走势如何影响全球通胀和央行政策",
        ],
    },
    {
        "keywords": {
            "中东": 3, "伊朗": 3, "以色列": 3, "霍尔木兹": 3, "美伊": 3,
            "空袭": 3, "地缘": 2, "战争": 2, "冲突": 2, "美军": 2,
        },
        "category": "地缘政治",
        "insight_tpl": "地缘政治风险升温，全球避险情绪正在重新定价。冲突的持续时间和烈度将决定资产价格的波动幅度。",
        "angles": [
            "原油视角：中东冲突升级，霍尔木兹海峡风险如何定价",
            "黄金视角：避险需求推升金价，持续性取决于冲突演变",
            "A股映射：地缘事件对A股军工、能源、航运板块的影响",
            "反常识观点：历史上地缘事件对市场的冲击往往是短期的",
            "全球航运：红海/霍尔木兹海峡风险对航运成本和保险的影响",
        ],
    },
    {
        "keywords": {
            "IPO": 3, "长鑫": 3, "打新": 2, "中签": 2, "新股": 2,
            "上市": 1, "科创板": 1, "注册制": 1, "申购": 1,
        },
        "category": "IPO市场",
        "insight_tpl": "重磅IPO引发市场高度关注。在高估值和市场波动交织的背景下，IPO定价与二级市场表现的分化是核心看点。",
        "angles": [
            "打新视角：中签率、估值和上市首日表现的风险收益分析",
            "产业视角：IPO公司的行业地位和竞争优势是否支撑高估值",
            "市场影响：大盘IPO对市场流动性的抽血效应有多大",
            "反常识观点：热门IPO不一定赚钱，历史上“巨无霸”上市后表现分化严重",
            "制度视角：注册制下IPO定价机制和投资者保护的完善",
        ],
    },
    {
        "keywords": {
            "财报": 3, "净利润": 3, "营收": 3, "盈利": 3, "日赚": 3,
            "回购股票": 3, "派息": 3, "季度报": 3, "暴雷": 2, "预亏": 2,
            "预喜": 2, "中报": 2, "年报": 2, "季报": 2, "业绩": 1, "净利": 1,
        },
        "category": "财报业绩",
        "insight_tpl": "财报季进入密集披露期，业绩分化越来越明显。市场对“好预期”的阈值在提高——仅仅是“不错”已经不够，必须“超预期”。",
        "angles": [
            "行业视角：哪些行业超预期、哪些在暴雷？行业景气度的信号",
            "个股视角：财报中隐藏的关键指标——毛利率、现金流、应收账款",
            "预期视角：为什么业绩好股价也可能跌？预期管理的艺术",
            "反常识观点：财报季最危险的不是暴雷，而是“符合预期但估值过高”",
            "策略视角：财报季结束后，机构会如何调仓",
        ],
    },
    {
        "keywords": {
            "黄金": 3, "白银": 3, "金价": 3, "贵金属": 2, "避险资产": 2,
            "黄金ETF": 2, "央行购金": 2,
        },
        "category": "贵金属",
        "insight_tpl": "黄金正在重新成为市场焦点。在全球不确定性上升、央行持续购金的背景下，金价突破后的走势值得关注。",
        "angles": [
            "避险视角：地缘政治和货币政策不确定性如何支撑金价",
            "央行视角：全球央行持续购金背后的去美元化逻辑",
            "资产配置：黄金在投资组合中的角色和合理比例",
            "反常识观点：金价创新高不等于追高合理，要看实际利率和美元",
            "A股映射：金价上涨对A股黄金板块和珠宝消费的影响",
        ],
    },
    {
        "keywords": {
            "可转债": 3, "债券": 3, "债市": 3, "信用债": 2, "固收": 2,
            "利率债": 2, "转债": 1,
        },
        "category": "固收市场",
        "insight_tpl": "股市波动加大时，可转债和固收类资产成为资金避风港。\"下有保底、上不封顶\"的转债策略在当下环境受到更多关注。",
        "angles": [
            "散户视角：可转债“下有保底”是不是神话？普通投资者怎么参与",
            "机构视角：当前转债市场的估值水平、转股溢价率和机会",
            "策略视角：股市震荡时，可转债和纯债怎么搭配",
            "反常识观点：可转债不是“稳赚不赔”，强赎、下修、违约都是风险",
            "长期视角：在利率下行环境中，固收类资产还能提供多少收益",
        ],
    },
    {
        "keywords": {
            "宁德时代": 5, "比亚迪": 5, "磷酸铁锂": 4, "碳酸锂": 4,
            "光伏": 3, "风电": 3, "储能": 3, "电动车": 3,
            "新能源": 2, "产能": 1, "满产": 1,
        },
        "category": "新能源",
        "insight_tpl": "新能源板块陷入“基本面好但股价弱”的背离。产能过剩担忧和出口限制是悬在头上的两把剑，但行业增速并未放缓。",
        "angles": [
            "数据派视角：装机量、产量、出口量的真实增速到底如何",
            "产业链视角：从上游矿产到下游整车，利润分配在发生什么变化",
            "全球视角：欧美关税和本地化要求对中国新能源出海的挑战",
            "反常识观点：业绩增长不等于股价上涨，市场提前定价了产能过剩",
            "技术视角：固态电池和新技术路线对现有产业链格局的冲击",
        ],
    },
    {
        "keywords": {
            "人民币": 3, "汇率": 3, "美元指数": 3, "离岸": 3,
            "外汇": 2, "欧元": 2, "日元": 2, "英鎊": 2, "美元": 1,
        },
        "category": "外汇市场",
        "insight_tpl": "汇率波动加大，人民币兑美元走势牵动全球市场神经。利差、贸易和资本流动三股力量正在角力。",
        "angles": [
            "进出口视角：汇率变动对出口企业和进口成本的直接影响",
            "资本流动：汇率预期如何影响外资流入A股和债市",
            "政策视角：央行稳汇率工具箱里还有哪些牌",
            "反常识观点：人民币贬值不一定是利空，对出口导向型企业是利好",
            "全球视角：美元指数走向和美联储政策对人民币的影响",
        ],
    },
    {
        "keywords": {
            "恒大": 3, "万科": 3, "碧桂园": 3, "保利": 3,
            "房地产": 3, "楼市": 2, "房价": 2, "房贷": 2, "开发商": 1,
        },
        "category": "房地产",
        "insight_tpl": "房地产市场仍处于探底过程中。政策在\"托\"与\"不举\"之间走钢丝——既要防止暴跌，又不想回到老路。",
        "angles": [
            "刚需视角：现在是不是买房的好时机？政策底和市场底的距离",
            "产业视角：头部房企的偿债压力和现金流安全",
            "金融视角：银行对房地产的敞口和不良率风险",
            "反常识观点：房地产不涨不一定是坏事，居民消费力可能因此释放",
            "长期视角：人口结构变化对房地产长期需求的深远影响",
        ],
    },
    {
        "keywords": {
            "拼多多": 3, "消费降级": 3, "CPI": 3, "通胀": 3, "社零": 2,
            "消费": 2, "零售": 2, "内需": 2, "物价": 1,
        },
        "category": "消费经济",
        "insight_tpl": "消费数据是经济冷暖的最直接温度计。消费降级还是升级？数据之间的分歧反映了不同人群的感受差异。",
        "angles": [
            "民生视角：物价上涨和收入预期的变化如何影响消费决策",
            "产业视角：消费分化——高端消费和性价比消费的冰火两重天",
            "数据视角：社零、CPI、电商数据的信号是否一致",
            "反常识观点：消费降级不一定是坏事，性价比经济正在崛起",
            "投资视角：消费板块何时真正触底，哪些细分赛道最先回暖",
        ],
    },
    {
        "keywords": {
            "药明": 3, "恒瑞": 3, "CXO": 3, "创新药": 3, "医保": 2,
            "集采": 2, "生物医药": 2, "疫苗": 2, "医药": 1,
        },
        "category": "医药健康",
        "insight_tpl": "医药板块经历深度调整后出现分化。创新药和CXO的反弹能否持续，取决于政策面和海外订单的走向。",
        "angles": [
            "产业视角：创新药研发管线和获批进展，谁在真正创新",
            "政策视角：医保谈判和集采政策对药企利润的影响",
            "全球视角：CXO的海外订单是否会因中美关系变化",
            "反常识观点：集采不全是利空，对以量换价的仿制药企可能是机会",
            "投资视角：创新药和CXO板块的估值修复空间有多大",
        ],
    },
    {
        "keywords": {
            "反垂断": 3, "垂断": 3, "市场监管总局": 3, "处罚": 3, "罚款": 3,
            "罚没": 3, "滥用市场": 3, "携程": 3, "平台经济": 3, "监管": 2,
            "整改": 2, "约谈": 2,
        },
        "category": "企业监管",
        "insight_tpl": "监管重拳落下，罚款金额和处罚力度比市场预期更猛。这不仅是针对单一企业的信号，更是整个行业合规成本上升的标志性事件。",
        "angles": [
            "企业视角：天价罚单对企业盈利和商业模式的实质性冲击有多大",
            "行业视角：监管风暴会不会扩散到同行业其他企业",
            "投资者视角：突发监管利空之下，短期情绪vs长期价值的博弈",
            "反常识观点：监管处罚未必是灾难，有时反而倒逼行业走向健康竞争",
            "政策视角：反垂断执法力度升级的背后，释放了什么样的政策信号",
        ],
    },
    {
        "keywords": {
            "身家缩水": 3, "万亿富翁": 3, "市值蒸发": 2,
        },
        "category": "资本市场人物",
        "insight_tpl": "顶流富豪或明星投资人的一举一动都牵动市场神经。财富数字变化的背后，是产业周期、企业战略与市场情绪的多重叠加。",
        "angles": [
            "产业视角：个人财富暴增/暴跌背后的企业和行业发生了什么",
            "市场心理：名人效应如何放大市场波动，“明星CEO溢价”值多少钱",
            "反常识观点：身家数字只是账面游戏，和公司实际价值不一定同步",
            "对比视角：同一赛道、不同玩家的财富分化说明了什么",
            "长远视角：回顾历史上富豪财富剧烈波动后，他们和公司是否都恢复",
        ],
    },
    # GENERIC FALLBACK — must be last. Dynamically generates insight from title keywords.
    {
        "keywords": {},
        "category": "财经热点",
        "insight_tpl": "__DYNAMIC__",
        "angles": [
            "数据派视角：这个事件背后的核心数据是什么，趋势如何",
            "产业视角：对相关行业和产业链的传导效应",
            "投资者视角：市场会如何反应，短期情绪和长期价值的博弈",
            "反常识观点：为什么大众可能的第一反应是错的",
            "政策视角：政策层面可能如何应对，有没有工具箱",
        ],
    },
]

# Warm-style prompt template
PROMPT_TEMPLATE = """你是一位财经短视频博主，请用"暖叔"风格，围绕以下话题和角度创作一段口播文案。

话题：{topic}
核心角度：{angle}
看点：{insight}

请严格遵循以下结构：
1. 开头钩子：用反常识或强情绪切入，一句话抓住观众注意力。
2. 中段反常识拆解：解释为什么大众当前的认知可能是错的，抛出对立面。
3. 推进2-3层事实：逐层展开具体数据、事件或市场反应，不空泛。
4. 结尾观察变量：指出接下来需要重点观察的信号，不下方向判断。

暖叔风格固定规则（必须全部满足）：
1. 字数控制在200-280字之间。
2. 口语化、碎片化表达，像聊天而不是念稿。
3. 事件与评论紧密咬合，不要脱离话题。
4. 使用暖叔口语词，如"说白了""你看""咱就说""得明白"等。
5. 短句为主，避免复杂长句。
6. 包含具体信息点、数据或真实细节。
7. 人称使用"我""你""我们"，增强代入感。
8. 禁止出现任何投资建议词汇，如"买入""卖出""抄底""满仓"等。
9. 禁止出现违规词汇、夸张恐吓用语。
10. 禁止公众号腔、新闻播报腔。

参考新闻源：
{sources}

注意：不要包含时间要求（如"15秒""60秒""120秒"），不要给出任何投资买卖建议。只输出可直接用作口播文案的文本。"""


def clean_slash(text):
    return text.replace("/", "、")


def generate_dynamic_insight(title):
    """Generate a dynamic insight from title keywords when no category matches."""
    words = [
        "监管", "处罚", "政策", "业绩", "财报", "科技", "AI", "能源",
        "消费", "市场", "投资", "全球", "趋势", "风险", "机会",
        "暴涨", "暴跌", "突破", "跌破", "反弹", "回落"
    ]
    matched = [w for w in words if w in title]
    if matched:
        return f"「{title[:20]}」成为市场关注焦点，背后的{'和'.join(matched[:3])}信号值得深入解读。事件的连锁反应和后续走向将决定市场短期情绪。"
    return f"「{title[:25]}」引发市场广泛关注。事件背后的深层逻辑和后续发展值得持续跟踪，其对相关板块和整体市场情绪的影响是核心看点。"


def match_category(title):
    """Match a title to the best-fit category using WEIGHTED keyword scoring.
    Entity-specific keywords (weight=3) have priority over generic terms (weight=1).
    """
    best = None
    best_score = 0
    for rule in CATEGORY_RULES:
        score = 0
        kw_dict = rule.get("keywords", {})
        if not kw_dict:
            continue  # skip dynamic fallback
        for kw, weight in kw_dict.items():
            if kw in title:
                score += weight
        if score > best_score:
            best_score = score
            best = rule
    
    if best is None or best_score == 0:
        # Use dynamic fallback (last rule)
        best = CATEGORY_RULES[-1]
    
    return best


def generate_summary(clusters):
    """Generate the 6-dimension summary dynamically."""
    # Gather all titles and count keyword frequencies
    all_titles = []
    for c in clusters[:10]:
        all_titles.extend(c.get("all_titles", [])[:5])
    all_text = " ".join(all_titles)

    # Market sentiment
    negative_kw = ["大跌", "暴跌", "跌破", "暴雷", "抛售", "恐慌", "危机", "冲突", "空袭", "战争", "亏损"]
    positive_kw = ["大涨", "暴涨", "反弹", "创新高", "利好", "增持", "回暖", "突破"]
    neg_count = sum(1 for kw in negative_kw if kw in all_text)
    pos_count = sum(1 for kw in positive_kw if kw in all_text)
    
    if neg_count > pos_count * 2:
        sentiment = "\U0001f631 极度恐慌｜负面事件密集，市场避险情绪浓重"
    elif neg_count > pos_count:
        sentiment = "\U0001f630 恐慌｜负面消息主导，市场承压"
    elif pos_count > neg_count:
        sentiment = "\U0001f60a 中性偏暖｜利好消息对冲中"
    else:
        sentiment = "\U0001f610 中性｜多空交织，市场处于观察窗口"

    # Core narrative
    narratives = []
    for c in clusters[:10]:
        cat = match_category(c["representative_title"])
        cat_name = cat["category"]
        rep_title = c["representative_title"][:20]
        key = f"{cat_name}｜{rep_title}"
        if key not in [n.split("｜")[0] + "｜" + n.split("｜")[1] if "｜" in n else n for n in narratives] and len(narratives) < 4:
            narratives.append(key)
    core_narrative = "；".join(narratives[:3]) if narratives else "全球财经市场动态"

    # Top cover topic
    if clusters:
        top_topic = clusters[0]["representative_title"]
        top_cover = clusters[0]["cover_count"]
        top_cover_str = f"「{clean_slash(top_topic[:30])}」覆盖 {top_cover} 个平台"
    else:
        top_cover_str = "—"

    # New hotspots
    hot_kw_list = ["突发", "刚刚", "最新", "新增", "首次", "紧急", "重磅"]
    new_hot = []
    for c in clusters[:10]:
        for kw in hot_kw_list:
            if kw in c["representative_title"] and len(new_hot) < 3:
                new_hot.append(f"\U0001f525{clean_slash(c['representative_title'][:25])}")
                break
    if not new_hot:
        new_hot = [f"\U0001f525{clean_slash(clusters[i]['representative_title'][:25])}" for i in range(min(3, len(clusters)))]
    new_hot_str = "｜".join(new_hot) if new_hot else "—"

    # Market anomaly
    anomaly = "当日数据暂无明显反常现象，关注成交量与涨跌家数是否背离"
    if "跌" in all_text and "涨" in all_text:
        anomaly = "涨跌互现，市场分化明显；需关注量价关系和板块轮动是否健康"
    elif "跌" in all_text and "增持" in all_text:
        anomaly = "政策托底与市场下跌并存，政策底与市场底的时差正在考验投资者耐心"

    # Tomorrow focus
    tomorrow = "次日开盘走势、成交量变化、政策面是否有进一步动作；国际市场关键事件和重要经济数据"
    if "美联储" in all_text or "利率" in all_text:
        tomorrow = "利率决议后续市场消化情况；政策面跟进措施；重点个股和板块的持续性"
    if "财报" in all_text:
        tomorrow = "后续财报发布、相关板块联动效应、资金面变化"

    return {
        "市场情绪": sentiment,
        "核心叙事": core_narrative,
        "最高覆盖话题": top_cover_str,
        "新增热点": new_hot_str,
        "市场异象": anomaly,
        "明日焦点": tomorrow,
    }


def generate_prompt(topic_name, angle, insight, sources):
    """Generate a self-contained prompt text for a given angle."""
    sources_lines = "\n".join(
        f"- {PLATFORM_ALIAS.get(s['platform'], s['platform'])}｜{clean_slash(s['title'])}：{s['url']}"
        for s in sources
    )
    return PROMPT_TEMPLATE.format(
        topic=clean_slash(topic_name),
        angle=clean_slash(angle),
        insight=clean_slash(insight),
        sources=sources_lines,
    )


def build_html(clusters, summary, date, period):
    rank_icons = ["\U0001f947", "\U0001f948", "\U0001f949", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "\U0001f51f"]

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日财经热搜TOP10 | {date}</title>
<style>
  :root {{
    --bg: #0d1117;
    --card-bg: #161b22;
    --card-border: #30363d;
    --accent: #f0883e;
    --accent2: #58a6ff;
    --accent3: #f778ba;
    --text: #c9d1d9;
    --text-bright: #f0f6fc;
    --text-muted: #8b949e;
    --green: #3fb950;
    --red: #f85149;
    --tag-bg: #1f2937;
    --summary-bg: #1c1208;
    --summary-border: #f0883e;
    --btn-bg: #238636;
    --btn-hover: #2ea043;
    --btn-text: #f0f6fc;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    line-height: 1.7;
    padding: 20px;
    max-width: 900px;
    margin: 0 auto;
  }}
  h1 {{
    color: var(--text-bright);
    font-size: 2em;
    text-align: center;
    margin-bottom: 8px;
    padding: 20px 0;
  }}
  .date {{
    text-align: center;
    color: var(--text-muted);
    font-size: 0.9em;
    margin-bottom: 24px;
  }}
  .summary-card {{
    background: var(--summary-bg);
    border: 2px solid var(--summary-border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 30px;
  }}
  .summary-card h2 {{
    color: var(--accent);
    font-size: 1.3em;
    margin-bottom: 16px;
  }}
  .summary-table {{
    width: 100%;
    border-collapse: collapse;
  }}
  .summary-table th {{
    color: var(--accent);
    text-align: left;
    padding: 8px 12px;
    font-size: 0.85em;
    width: 110px;
    border-bottom: 1px solid var(--card-border);
    vertical-align: top;
  }}
  .summary-table td {{
    padding: 8px 12px;
    color: var(--text);
    font-size: 0.9em;
    border-bottom: 1px solid var(--card-border);
  }}
  .topic-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 20px;
    transition: transform 0.2s;
  }}
  .topic-card:hover {{
    transform: translateY(-2px);
    border-color: var(--accent);
  }}
  .topic-rank {{
    display: inline-block;
    font-size: 1.8em;
    margin-right: 8px;
    vertical-align: middle;
  }}
  .topic-title {{
    font-size: 1.4em;
    color: var(--text-bright);
    display: inline;
    vertical-align: middle;
  }}
  .topic-meta {{
    color: var(--accent);
    font-size: 0.9em;
    margin: 8px 0 16px 0;
    padding-left: 40px;
  }}
  .platform-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
  }}
  .platform-table th {{
    color: var(--accent);
    text-align: left;
    padding: 6px 10px;
    font-size: 0.8em;
    border-bottom: 1px solid var(--card-border);
    width: 100px;
  }}
  .platform-table td {{
    padding: 6px 10px;
    color: var(--text);
    font-size: 0.85em;
    border-bottom: 1px solid rgba(48,54,61,0.5);
  }}
  .platform-table td a {{
    color: var(--accent2);
    text-decoration: none;
    font-size: 0.85em;
  }}
  .platform-table td a:hover {{
    text-decoration: underline;
  }}
  .insight {{
    background: rgba(240,136,62,0.1);
    border-left: 3px solid var(--accent);
    padding: 12px 16px;
    margin: 12px 0;
    border-radius: 6px;
  }}
  .insight-label {{
    color: var(--accent);
    font-weight: bold;
    font-size: 0.9em;
  }}
  .insight-text {{
    color: var(--text);
    font-size: 0.9em;
    margin-top: 4px;
  }}
  .angle {{
    background: rgba(88,166,255,0.08);
    border-left: 3px solid var(--accent2);
    padding: 12px 16px;
    margin: 12px 0;
    border-radius: 6px;
  }}
  .angle-label {{
    color: var(--accent2);
    font-weight: bold;
    font-size: 0.9em;
  }}
  .angle-item {{
    color: var(--text);
    font-size: 0.85em;
    margin: 8px 0;
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .angle-item .num {{
    color: var(--accent2);
    font-weight: bold;
    min-width: 20px;
  }}
  .angle-text {{
    flex: 1;
  }}
  .btn-prompt {{
    background: var(--btn-bg);
    color: var(--btn-text);
    border: none;
    padding: 4px 10px;
    font-size: 0.75em;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.2s;
    white-space: nowrap;
  }}
  .btn-prompt:hover {{
    background: var(--btn-hover);
  }}
  .conclusion {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 20px;
    margin: 30px 0;
  }}
  .conclusion h2 {{
    color: var(--accent);
    font-size: 1.2em;
    margin-bottom: 12px;
  }}
  .conclusion p {{
    color: var(--text);
    font-size: 0.95em;
    margin-bottom: 10px;
  }}
  .conclusion ul {{
    color: var(--text);
    font-size: 0.95em;
    padding-left: 20px;
  }}
  .conclusion li {{
    margin-bottom: 6px;
  }}
  .tag {{
    background: var(--tag-bg);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.8em;
    margin-right: 4px;
  }}
  .modal-overlay {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7);
    z-index: 1000;
    justify-content: center;
    align-items: center;
  }}
  .modal-overlay.active {{
    display: flex;
  }}
  .modal-content {{
    background: var(--card-bg);
    border: 1px solid var(--accent);
    border-radius: 12px;
    padding: 24px;
    max-width: 600px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
  }}
  .modal-content h3 {{
    color: var(--accent);
    margin-bottom: 12px;
  }}
  .modal-content pre {{
    background: var(--bg);
    padding: 12px;
    border-radius: 6px;
    color: var(--text);
    font-size: 0.85em;
    overflow-x: auto;
    white-space: pre-wrap;
    line-height: 1.6;
  }}
  .modal-close {{
    background: var(--accent);
    color: var(--text-bright);
    border: none;
    padding: 6px 16px;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 12px;
  }}
  .copy-hint {{
    color: var(--green);
    font-size: 0.85em;
    margin-top: 8px;
  }}
  .generated-note {{
    text-align: center;
    color: var(--text-muted);
    font-size: 0.8em;
    margin-top: 30px;
    padding: 10px;
    border-top: 1px solid var(--card-border);
  }}
  @media (max-width: 600px) {{
    body {{ padding: 12px; }}
    h1 {{ font-size: 1.4em; }}
    .topic-title {{ font-size: 1.1em; }}
    .platform-table {{ font-size: 0.8em; }}
    .angle-item {{ flex-direction: column; align-items: flex-start; }}
  }}
</style>
</head>
<body>

<h1>\U0001f525 今日财经热搜 TOP 10</h1>
<div class="date">{date} {period} · GitHub Actions 云端自动生成 · 全平台跨覆盖合并排名</div>

<div class="summary-card">
  <h2>\U0001f3af 报告摘要</h2>
  <table class="summary-table">
""")

    for key in ["市场情绪", "核心叙事", "最高覆盖话题", "新增热点", "市场异象", "明日焦点"]:
        html_parts.append(f'    <tr><th>{key}</th><td>{summary.get(key, "—")}</td></tr>\n')

    html_parts.append("""  </table>
</div>
""")

    # Topic cards
    for i, c in enumerate(clusters[:10]):
        rank = rank_icons[i]
        topic_name = clean_slash(c["representative_title"])
        platform_rows = ""
        seen_platforms = set()
        for s in c.get("sources", []):
            pname = PLATFORM_ALIAS.get(s["platform"], s["platform"])
            if pname in seen_platforms:
                continue
            seen_platforms.add(pname)
            title = clean_slash(s["title"])
            url = s["url"]
            platform_rows += f'<tr><td>{pname}</td><td><a href="{url}" target="_blank" rel="noopener">{title}</a></td></tr>\n'

        # Match category
        cat = match_category(topic_name)
        insight = cat["insight_tpl"]
        if insight == "__DYNAMIC__":
            insight = generate_dynamic_insight(topic_name)
        angles = cat["angles"]

        angle_items = []
        for j, angle in enumerate(angles):
            prompt_text = generate_prompt(c["representative_title"], angle, insight, c.get("sources", []))
            prompt_attr = (prompt_text.replace('\\', '\\\\')
                           .replace('"', '&quot;')
                           .replace('\n', '&#10;'))
            angle_items.append(
                f'<div class="angle-item">\n'
                f'  <span class="num">{j+1}</span>\n'
                f'  <span class="angle-text">{clean_slash(angle)}</span>\n'
                f'  <button class="btn-prompt" onclick="showPromptModal(this)" data-prompt="{prompt_attr}">\U0001f4dd 生成提示词</button>\n'
                f'</div>'
            )

        platforms_str = "、".join(c.get("platforms", []))

        html_parts.append(f"""
<div class="topic-card">
  <div class="topic-rank">{rank}</div>
  <span class="topic-title">{topic_name}</span>
  <div class="topic-meta">
    <span class="tag">覆盖 {c['cover_count']} 个平台</span>
    {platforms_str}
  </div>
  <table class="platform-table">
    <thead><tr><th>平台</th><th>代表性标题</th></tr></thead>
    <tbody>{platform_rows}</tbody>
  </table>
  <div class="insight">
    <div class="insight-label">\U0001f4a1 看点</div>
    <div class="insight-text">{insight}</div>
  </div>
  <div class="angle">
    <div class="angle-label">\U0001f50d 解读角度</div>
    {''.join(angle_items)}
  </div>
</div>
""")

    # Conclusion
    narratives_text = ""
    for i, c in enumerate(clusters[:10]):
        cat = match_category(c["representative_title"])
        narratives_text += f"<li><strong>{cat['category']}</strong>——{clean_slash(c['representative_title'][:50])}{'...' if len(c['representative_title']) > 50 else ''}</li>\n"

    html_parts.append(f"""
<div class="conclusion">
  <h2>\U0001f4dd 今日总结</h2>
  <p>{date} {period}，全球财经市场热点覆盖以下主线：</p>
  <ul>
{narratives_text}  </ul>
</div>

<div class="modal-overlay" id="promptModal">
  <div class="modal-content">
    <h3>\U0001f4dd 生成提示词</h3>
    <p style="color:#8b949e;font-size:0.85em;margin-bottom:8px;">以下提示词已包含话题、角度、看点与参考新闻源，可直接复制到任意AI生成口播文案</p>
    <pre id="promptText"></pre>
    <div class="copy-hint" id="copyHint">✅ 已自动复制到剪贴板</div>
    <button class="modal-close" onclick="closePromptModal()">关闭</button>
  </div>
</div>

<script>
function showPromptModal(btn) {{
  const text = btn.getAttribute('data-prompt').replace(/&#10;/g, '\\n');
  document.getElementById('promptText').textContent = text;
  document.getElementById('copyHint').style.display = 'none';
  document.getElementById('promptModal').classList.add('active');
  navigator.clipboard.writeText(text).then(() => {{
    document.getElementById('copyHint').style.display = 'block';
  }}).catch(() => {{
    document.getElementById('copyHint').textContent = '⚠️ 复制失败，请手动复制';
    document.getElementById('copyHint').style.display = 'block';
  }});
}}
function closePromptModal() {{
  document.getElementById('promptModal').classList.remove('active');
}}
document.getElementById('promptModal').addEventListener('click', function(e) {{
  if (e.target === this) closePromptModal();
}});
</script>

<div class="generated-note">
  \U0001f916 本报告由 GitHub Actions 云端定时自动生成 · 数据来源：tophub.today · {date} {period}
</div>

</body>
</html>""")

    return "".join(html_parts)


def main():
    # Read cluster JSON
    json_path = os.environ.get("CLUSTER_JSON")
    if not json_path:
        output_dir = os.environ.get("OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output"))
        date_str = os.environ.get("REPORT_DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        json_path = os.path.join(output_dir, f"tophub_clusters_{date_str}.json")
    
    if not os.path.exists(json_path):
        print(f"Error: cluster JSON not found at {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    clusters = data.get("clusters", [])
    date = data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    period = data.get("period", "上午" if datetime.now(timezone.utc).hour < 4 else "下午")

    if not clusters:
        print("Error: no clusters found")
        sys.exit(1)

    print(f"Generating report for {date} {period} with {len(clusters)} clusters")

    # Generate summary
    summary = generate_summary(clusters)

    # Generate HTML
    html = build_html(clusters, summary, date, period)

    # Save
    output_dir = os.path.dirname(json_path)
    html_path = os.path.join(output_dir, f"index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML saved to {html_path}")

    # Save report URL for email step
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        owner = repo.split("/")[0] if "/" in repo else ""
        repo_name = repo.split("/")[1] if "/" in repo else ""
        pages_url = f"https://{owner}.github.io/{repo_name}/"
        with open(env_file, "a") as f:
            f.write(f"REPORT_URL={pages_url}\n")
        print(f"Report will be available at: {pages_url}")

    print("✅ Report generation complete")


if __name__ == "__main__":
    main()
