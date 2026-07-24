import os, json, requests, time, anthropic, re, threading
from datetime import datetime
from playwright.async_api import async_playwright
import asyncio

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
AUTHORIZED_USER = int(os.environ["AUTHORIZED_USER"])
BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def send(chat_id, text, reply_markup=None, parse_mode=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        return requests.post(f"{BASE}/sendMessage", json=data, timeout=30).json()
    except:
        return {}

def answer_cb(cb_id):
    try:
        requests.post(f"{BASE}/answerCallbackQuery",
            json={"callback_query_id": cb_id}, timeout=10)
    except:
        pass

def ask_claude(prompt, system=""):
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=system or "你是Edison Lim的马来西亚华语内容助手。",
        messages=[{"role": "user", "content": prompt}]
    )
    if not msg.content:
        raise ValueError("Claude返回空内容")
    return msg.content[0].text

SYSTEM = """你是Edison Lim (@edison_ttm) 的内容助手，专门为马来西亚华人生成爆款内容。

文案结构（timtiah风格）：
1. 钩子：具体场景或数字开头，画面感强
2. 背景：为什么重要，贴近马来西亚人日常
3. 数据：真实数字，朋友口吻
4. 立场：不偏不倚，传递「要有自己的判断」价值观
5. 评论引导：具体问题，让人忍不住留言

要求：口语化马来西亚华语、短句有节奏、用「—」分段、200-300字、加hashtag"""

# ── Playwright 扫Facebook ────────────────────────────
async def scan_facebook():
    """扫描三家Facebook，返回帖子列表（含直链）"""
    FB_PAGES = [
        {"name": "星洲日报", "url": "https://www.facebook.com/SinChewDaily"},
        {"name": "中国报", "url": "https://www.facebook.com/ChinaPressMY"},
        {"name": "南洋商报", "url": "https://www.facebook.com/nanyang.nysp"},
    ]
    
    all_posts = []
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222") if False else \
                  await p.chromium.launch(headless=True, args=[
                      "--no-sandbox","--disable-setuid-sandbox",
                      "--disable-dev-shm-usage","--disable-gpu"
                  ])
        ctx = await browser.new_context(
            viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
            locale="zh-CN"
        )
        page = await ctx.new_page()
        
        for fb in FB_PAGES:
            try:
                print(f"扫描: {fb['url']}")
                await page.goto(fb["url"], wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(6000)
                
                # 滚动加载帖子
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(2000)
                
                # 找帖子：文字+直链+互动数
                posts = await page.evaluate("""() => {
                    const results = [];
                    const seen = new Set();
                    
                    // 找所有帖子容器
                    const articles = document.querySelectorAll('[role="article"]');
                    
                    articles.forEach(container => {
                        // 找帖子直链
                        const postLink = container.querySelector('a[href*="/posts/"], a[href*="/permalink/"]');
                        if (!postLink) return;
                        
                        const href = postLink.href;
                        if (seen.has(href)) return;
                        seen.add(href);
                        
                        // 找文字内容
                        const allText = container.innerText || '';
                        const lines = allText.split('\n').filter(l => l.trim().length > 10);
                        const text = lines.slice(0, 5).join(' ').trim().slice(0, 250);
                        
                        // 找新闻链接
                        const newsLinks = [...container.querySelectorAll('a[href]')]
                            .map(l => l.href)
                            .filter(h => h.includes('sinchew') || h.includes('chinapress') || 
                                        h.includes('enanyang') || h.includes('orientaldaily') ||
                                        h.includes('malaymail') || h.includes('thestar'));
                        
                        // 抓互动数（like/comment/share数字）
                        let likes = 0, comments = 0, shares = 0;
                        const allNums = allText.match(/\d[\d,]*/g) || [];
                        
                        // Facebook通常格式：数字K 或 纯数字
                        const interactionEl = container.querySelectorAll('span[aria-hidden="true"], div[role="button"]');
                        interactionEl.forEach(el => {
                            const t = el.innerText || '';
                            const num = parseFloat(t.replace(',','').replace('K','000').replace('k','000'));
                            if (!isNaN(num) && num > 0 && num < 1000000) {
                                if (likes === 0) likes = num;
                                else if (comments === 0) comments = num;
                                else if (shares === 0) shares = num;
                            }
                        });
                        
                        // 备用：找包含数字的span
                        if (likes === 0) {
                            const spans = [...container.querySelectorAll('span')];
                            spans.forEach(s => {
                                const t = (s.innerText||'').trim();
                                if (/^[\d,\.]+K?$/.test(t)) {
                                    const n = parseFloat(t.replace(',','').replace('K','000'));
                                    if (n > 0 && n < 500000) {
                                        if (likes === 0) likes = n;
                                        else if (comments === 0) comments = n;
                                    }
                                }
                            });
                        }
                        
                        const total_engagement = likes + comments * 3 + shares * 5;
                        
                        if (text.length > 15) {
                            results.push({
                                post_url: href,
                                text: text,
                                news_url: newsLinks[0] || '',
                                likes: Math.round(likes),
                                comments: Math.round(comments),
                                shares: Math.round(shares),
                                total: Math.round(total_engagement)
                            });
                        }
                    });
                    
                    // 按互动数排序
                    results.sort((a, b) => b.total - a.total);
                    return results.slice(0, 20);
                }""")
                
                for p in posts:
                    p["source"] = fb["name"]
                all_posts.extend(posts)
                print(f"✅ {fb['name']}: {len(posts)} 条帖子")
                
            except Exception as e:
                print(f"❌ {fb['name']}: {e}")
        
        await browser.close()
    
    return all_posts

def select_6_topics(posts):
    """按互动数排序，让Claude cross-check选出10小时内最爆的6个话题"""
    today = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    
    # 整理帖子给Claude分析
    text = f"现在是{today}（马来西亚时间）。以下是三家中文媒体Facebook帖子，已按互动数从高到低排序：\n\n"
    for i, p in enumerate(posts[:35]):
        engagement = p.get('total', 0)
        likes = p.get('likes', 0)
        comments = p.get('comments', 0)
        text += f"{i+1}. [{p['source']}] 👍{likes} 💬{comments} 🔥总分{engagement}\n"
        text += f"   内容：{p['text'][:150]}\n"
        if p.get('news_url'):
            text += f"   📰 {p['news_url']}\n"
        text += f"   🔗 {p['post_url']}\n\n"
    
    text += """请做严格的cross-check分析：

【第一步：找重叠话题】
找出同一个话题在2家或以上媒体同时出现的——这些才是真正的爆款。

【第二步：按优先级排序】
优先级从高到低：
① 3家媒体都有 + 互动数高 ← 最爆
② 2家媒体都有 + 互动数高
③ 只有1家但互动数极高（like+comment超过500）
④ 其他不要选

【第三步：选6个】
从上面选出6个最值得做的话题，必须有争议性或情绪共鸣，有具体数字。

严格按以下格式回复，每行用|||分隔，共6行：
话题标题|||一句话背景|||关键数字或事实|||出现媒体（如：星洲+中国报）|||新闻URL|||帖子URL

只回复6行，不要任何其他文字。"""
    
    raw = ask_claude(text)
    print(f"Claude选题：\n{raw[:600]}")
    
    topics = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) >= 4:
            topics.append({
                "num": len(topics)+1,
                "cat": "",
                "topic": parts[0].strip(),
                "hook": parts[1].strip(),
                "data": parts[2].strip(),
                "source": parts[3].strip(),
                "news_url": parts[4].strip() if len(parts) > 4 else "",
                "post_url": parts[5].strip() if len(parts) > 5 else "",
            })
        if len(topics) == 6:
            break
    return topics

def gen_caption(t):
    return ask_claude(f"""话题：{t['topic']}
分类：{t['cat']}
钩子参考：{t['hook']}
关键数据：{t['data']}（来源：{t['source']}）

按timtiah结构写200-300字Instagram文案。段落间单行换行。只回复文案。""", SYSTEM)

def optimize(original, feedback, t):
    return ask_claude(f"""原文案：
{original}

用户反馈：{feedback}
话题：{t['topic']}

根据反馈优化，保持timtiah结构200-300字，只回复新文案。""", SYSTEM)

def publish_to_channel(caption):
    requests.post(f"{BASE}/sendMessage",
        json={"chat_id": CHANNEL_ID, "text": caption}, timeout=30)

# ── 按钮 ─────────────────────────────────────────────
BTN_CAPTION = {"inline_keyboard":[[
    {"text":"✅ 文案满意", "callback_data":"caption_ok"},
    {"text":"✏️ 修改文案", "callback_data":"caption_edit"}
]]}
BTN_PUBLISH = {"inline_keyboard":[[
    {"text":"✅ 发布文案到频道", "callback_data":"publish"},
    {"text":"⏭️ 下一篇", "callback_data":"next"}
]]}
BTN_NEXT = {"inline_keyboard":[[
    {"text":"▶️ 下一篇", "callback_data":"next"},
    {"text":"🏁 今天完成", "callback_data":"done"}
]]}

# ── 状态 ─────────────────────────────────────────────
state = {}

def get_s(uid):
    if uid not in state:
        state[uid] = {"step":"idle","topics":[],"captions":[],"idx":0}
    return state[uid]

# ── 消息处理 ─────────────────────────────────────────
def handle_msg(msg):
    uid = msg["from"]["id"]
    cid = msg["chat"]["id"]
    text = msg.get("text","").strip()
    if uid != AUTHORIZED_USER:
        return
    s = get_s(uid)

    if text in ["开始","给我今天的内容","今天的内容","/start","/content"]:
        send(cid, "⚡ 正在扫描星洲日报、中国报、南洋商报 Facebook，请稍等约1分钟...")
        def run():
            try:
                posts = asyncio.run(scan_facebook())
                if not posts:
                    send(cid, "❌ 扫描失败，请重试")
                    return
                send(cid, f"📱 扫到{len(posts)}条帖子，正在选出6个爆款话题...")
                topics = select_6_topics(posts)
                if not topics:
                    send(cid, "❌ 选题失败，请重试")
                    return
                s.update({"topics":topics,"captions":[""]*len(topics),"idx":0,"step":"show_topics"})
                
                lines = "🔥 今日最爆6个话题（按互动数排序）：\n\n"
                for t in topics:
                    lines += f"{t['num']}. {t['topic']}\n"
                    if t.get('source'):
                        lines += f"   📌 {t['source']}\n"
                lines += "\n满意就点开始生成文案 👇"
                send(cid, lines, {"inline_keyboard":[[
                    {"text":"⚡ 开始逐篇生成","callback_data":"generate"}
                ]]})
            except Exception as e:
                send(cid, f"❌ 失败：{e}\n\n请重试")
        threading.Thread(target=run, daemon=True).start()
        return

    if s["step"] == "editing":
        t = s["topics"][s["idx"]]
        send(cid, "✏️ 优化中...")
        try:
            new = optimize(s["captions"][s["idx"]], text, t)
            s["captions"][s["idx"]] = new
            s["step"] = "review_caption"
            send(cid, f"📝 优化后文案：\n\n{new}", BTN_CAPTION)
        except Exception as e:
            send(cid, f"❌ 失败：{e}")
        return

    send(cid, "👋 发「给我今天的内容」开始 ⚡")

def handle_callback(cb):
    uid = cb["from"]["id"]
    cid = cb["message"]["chat"]["id"]
    data = cb["data"]
    answer_cb(cb["id"])
    if uid != AUTHORIZED_USER:
        return
    s = get_s(uid)

    if data == "generate":
        idx = s["idx"]
        t = s["topics"][idx]
        send(cid, f"✍️ 生成第{t['num']}/6篇：{t['topic']}")
        def run():
            try:
                caption = gen_caption(t)
                s["captions"][idx] = caption
                s["step"] = "review_caption"
                
                # 发文案
                send(cid, f"📝 第{t['num']}/6 文案：\n\n{caption}", BTN_CAPTION)
            except Exception as e:
                send(cid, f"❌ 生成失败：{e}")
        threading.Thread(target=run, daemon=True).start()
        return

    if data == "caption_ok":
        idx = s["idx"]
        t = s["topics"][idx]
        s["step"] = "review"
        
        # 发链接让用户下载图片
        links_msg = f"📌 第{t['num']}篇配图链接：\n\n"
        
        if t.get("post_url"):
            links_msg += f"🖼️ Facebook帖子（有图）：\n{t['post_url']}\n\n"
        if t.get("news_url"):
            links_msg += f"📰 新闻原文：\n{t['news_url']}\n\n"
        
        links_msg += "👆 点链接保存图片后，按下面发布文案到频道"
        send(cid, links_msg, BTN_PUBLISH)
        return

    if data == "caption_edit":
        s["step"] = "editing"
        send(cid, "✏️ 告诉我哪里要改：")
        return

    if data == "publish":
        idx = s["idx"]
        t = s["topics"][idx]
        caption = s["captions"][idx]
        try:
            publish_to_channel(caption)
            send(cid, f"✅ 第{t['num']}篇文案已发布到频道！\n\n记得手动配上你从Facebook保存的图片 📸", BTN_NEXT)
            s["step"] = "published"
        except Exception as e:
            send(cid, f"❌ 发布失败：{e}")
        return

    if data == "next":
        s["idx"] += 1
        if s["idx"] >= len(s["topics"]):
            send(cid, "🎉 今日6篇全部完成！明天发「给我今天的内容」继续。")
            s["step"] = "idle"
        else:
            t = s["topics"][s["idx"]]
            s["step"] = "show_topics"
            send(cid, f"第{t['num']}/6：{t['cat']} — {t['topic']}",
                 {"inline_keyboard":[[{"text":"⚡ 生成文案","callback_data":"generate"}]]})
        return

    if data == "done":
        send(cid, "✅ 今天完成！明天见 👋")
        s["step"] = "idle"
        return

def main():
    print("✅ Edison Bot 启动！")
    offset = 0
    while True:
        try:
            r = requests.get(f"{BASE}/getUpdates",
                params={"offset":offset,"timeout":30}, timeout=35)
            data = r.json()
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                if "message" in u:
                    handle_msg(u["message"])
                elif "callback_query" in u:
                    handle_callback(u["callback_query"])
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
