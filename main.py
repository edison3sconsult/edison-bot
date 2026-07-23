import os, json, requests, time, anthropic, re, base64, asyncio, threading
from datetime import datetime
from playwright.async_api import async_playwright

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
AUTHORIZED_USER = int(os.environ["AUTHORIZED_USER"])
BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(f"{BASE}/sendMessage", json=data, timeout=30).json()
    except:
        return {}

def send_photo_bytes(chat_id, img_bytes, caption, reply_markup=None):
    data = {"chat_id": chat_id, "caption": caption}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(f"{BASE}/sendPhoto", data=data,
            files={"photo": ("news.png", img_bytes, "image/png")}, timeout=30).json()
    except:
        return {}

def send_channel(img_bytes, caption):
    try:
        if img_bytes:
            r = requests.post(f"{BASE}/sendPhoto",
                data={"chat_id": CHANNEL_ID, "caption": caption},
                files={"photo": ("news.png", img_bytes, "image/png")}, timeout=30).json()
            if r.get("ok"):
                return True
        requests.post(f"{BASE}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": caption}, timeout=30)
        return True
    except:
        return False

def answer_cb(cb_id):
    try:
        requests.post(f"{BASE}/answerCallbackQuery",
            json={"callback_query_id": cb_id}, timeout=10)
    except:
        pass

def ask_claude(prompt, system="", images_b64=None):
    content = []
    if images_b64:
        for b64 in images_b64:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64}
            })
    content.append({"type": "text", "text": prompt})
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=system or "你是Edison Lim的马来西亚华语内容助手。",
        messages=[{"role": "user", "content": content}]
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

NEWS_SITES = [
    {"name": "中国报", "url": "https://www.chinapress.com.my"},
    {"name": "星洲日报", "url": "https://www.sinchew.com.my"},
    {"name": "南洋商报", "url": "https://www.enanyang.my"},
    {"name": "东方日报", "url": "https://www.orientaldaily.com.my"},
]

async def scrape_news_with_links():
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu"
        ])
        ctx = await browser.new_context(
            viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            locale="zh-CN"
        )
        page = await ctx.new_page()
        for site in NEWS_SITES:
            try:
                await page.goto(site["url"], wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)
                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                except:
                    pass
                articles = await page.evaluate("""() => {
                    const items = [];
                    const seen = new Set();
                    const links = [...document.querySelectorAll('a[href]')];
                    for (const a of links) {
                        const href = a.href;
                        if (!href || seen.has(href)) continue;
                        if (href.includes('javascript') || href.includes('#')) continue;
                        const text = (a.innerText || a.textContent || '').trim();
                        if (!text || text.length < 8 || text.length > 200) continue;
                        seen.add(href);
                        items.push({title: text, url: href});
                        if (items.length >= 25) break;
                    }
                    return items;
                }""")
                results.append({
                    "site": site["name"],
                    "url": site["url"],
                    "articles": articles
                })
                print(f"✅ {site['name']}: {len(articles)} 篇")
            except Exception as e:
                print(f"❌ {site['name']}: {e}")
        await browser.close()
    return results

async def get_news_image(topic, source, article_url):
    """用Unsplash搜索相关图片，稳定快速"""
    
    # 关键词映射：话题 -> 英文搜索词
    keyword_map = {
        "关税": "tariff trade war",
        "特朗普": "donald trump",
        "令吉": "malaysia ringgit currency",
        "股市": "stock market malaysia",
        "经济": "malaysia economy",
        "油价": "petrol fuel pump malaysia",
        "RON95": "petrol fuel pump",
        "补贴": "fuel subsidy malaysia",
        "森林城市": "forest city johor",
        "选举": "malaysia election voting",
        "森州": "negeri sembilan malaysia",
        "柔佛": "johor malaysia",
        "华为": "huawei technology",
        "AI": "artificial intelligence technology",
        "OpenAI": "artificial intelligence robot",
        "谢贤": "hong kong celebrity actor",
        "交通": "malaysia traffic accident road",
        "无牌": "car accident malaysia road",
        "房价": "malaysia property house",
        "失业": "unemployment job malaysia",
        "大学": "university malaysia graduate",
        "医院": "hospital malaysia healthcare",
        "诈骗": "malaysia scam fraud",
        "TikTok": "social media smartphone",
        "Grab": "grab malaysia food delivery",
        "ZUS": "coffee malaysia cafe",
        "Tealive": "bubble tea malaysia",
    }
    
    # 找最匹配的关键词
    search_term = "malaysia news"
    for kw, eng in keyword_map.items():
        if kw in topic:
            search_term = eng
            break
    
    print(f"Unsplash搜索: {search_term}")
    
    try:
        # Unsplash Source API - 免费无需key
        url = f"https://source.unsplash.com/800x500/?{requests.utils.quote(search_term)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 10000:
            print("✅ Unsplash图片获取成功")
            # 在图片上叠加标题文字
            return r.content
    except Exception as e:
        print(f"Unsplash失败: {e}")
    
    # 备用：Picsum随机图片（保证有图）
    try:
        r = requests.get("https://picsum.photos/800/500", timeout=10, allow_redirects=True)
        if r.status_code == 200:
            print("✅ 备用图片获取成功")
            return r.content
    except:
        pass
    
    return None



def select_topics(news_results):
    today = datetime.now().strftime("%Y年%m月%d日")
    news_text = f"今天是{today}。以下是马来西亚中文媒体今日新闻列表：\n\n"
    for r in news_results:
        news_text += f"【{r['site']}】\n"
        for i, a in enumerate(r["articles"][:20]):
            news_text += f"{i+1}. {a['title']} | {a['url']}\n"
        news_text += "\n"

    news_text += """请从以上新闻中选出6个最有爆款潜力的话题。

选题标准：有争议性、有情绪共鸣、有数据、贴近马来西亚华人日常。

严格按以下格式回复，每行一个话题，用|||分隔，共6行：
分类|||话题标题|||钩子句|||关键数据|||来源媒体|||新闻URL

分类只能是：💼商业、📊金融、🧠人间清醒、❤️家庭情感

只回复6行，不要任何其他文字。"""

    raw = ask_claude(news_text)
    print(f"Claude选题：\n{raw[:500]}")

    topics = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) >= 5:
            topics.append({
                "num": len(topics)+1,
                "cat": parts[0].strip(),
                "topic": parts[1].strip(),
                "hook": parts[2].strip(),
                "data": parts[3].strip(),
                "source": parts[4].strip(),
                "url": parts[5].strip() if len(parts) >= 6 else "",
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

BTN_CAPTION = {"inline_keyboard":[[
    {"text":"✅ 文案满意","callback_data":"caption_ok"},
    {"text":"✏️ 修改文案","callback_data":"caption_edit"}
]]}
BTN_PUBLISH = {"inline_keyboard":[[
    {"text":"✅ 发布到频道","callback_data":"publish"},
    {"text":"⏭️ 下一篇","callback_data":"next"}
]]}
BTN_NEXT = {"inline_keyboard":[[
    {"text":"▶️ 下一篇","callback_data":"next"},
    {"text":"🏁 今天完成","callback_data":"done"}
]]}

state = {}

def get_s(uid):
    if uid not in state:
        state[uid] = {"step":"idle","topics":[],"captions":[],"screenshots":[],"idx":0}
    return state[uid]

def handle_msg(msg):
    uid = msg["from"]["id"]
    cid = msg["chat"]["id"]
    text = msg.get("text","").strip()
    if uid != AUTHORIZED_USER:
        return
    s = get_s(uid)

    if text in ["开始","给我今天的内容","今天的内容","/start","/content"]:
        send(cid, "⚡ 正在扫描中国报、星洲日报、南洋商报、东方日报，请稍等约1分钟...")
        def run():
            try:
                news_results = asyncio.run(scrape_news_with_links())
                if not news_results:
                    send(cid, "❌ 扫描失败，请重试")
                    return
                total = sum(len(r["articles"]) for r in news_results)
                send(cid, f"📰 扫描到{total}篇新闻，Claude正在选出6个爆款话题...")
                topics = select_topics(news_results)
                if not topics:
                    send(cid, "❌ 选题失败，请重试")
                    return
                s.update({"topics":topics,"captions":[""]*len(topics),
                          "screenshots":[None]*len(topics),"idx":0,"step":"show_topics"})
                lines = "🗞️ 今日6个爆款话题：\n\n"
                for t in topics:
                    lines += f"{t['num']}. {t['cat']} — {t['topic']}\n"
                lines += "\n点下面开始逐篇生成 👇"
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
        send(cid, f"✍️ 生成第{t['num']}/6篇：{t['cat']} — {t['topic']}")
        def run():
            try:
                caption = gen_caption(t)
                s["captions"][idx] = caption
                s["step"] = "review_caption"
                send(cid, f"📝 第{t['num']}/6 文案：\n\n{caption}", BTN_CAPTION)
            except Exception as e:
                send(cid, f"❌ 生成失败：{e}")
        threading.Thread(target=run, daemon=True).start()
        return

    if data == "caption_ok":
        idx = s["idx"]
        t = s["topics"][idx]
        s["step"] = "review_image"
        send(cid, "📸 正在搜索新闻配图（三重策略），请稍等约30秒...")
        def run():
            try:
                img = asyncio.run(get_news_image(
                    t["topic"], t["source"], t.get("url","")
                ))
                if img and len(img) > 5000:
                    s["screenshots"][idx] = img
                    r = send_photo_bytes(cid, img, f"🖼️ 配图预览（{t['source']}）")
                    if r.get("ok"):
                        send(cid, "满意就发布 👇", BTN_PUBLISH)
                        return
                send(cid, "⚠️ 三个策略都找不到配图，直接发布文案？", BTN_PUBLISH)
            except Exception as e:
                print(f"配图错误: {e}")
                send(cid, "⚠️ 配图失败，直接发布文案？", BTN_PUBLISH)
        threading.Thread(target=run, daemon=True).start()
        return

    if data == "caption_edit":
        s["step"] = "editing"
        send(cid, "✏️ 告诉我哪里要改：")
        return

    if data == "publish":
        idx = s["idx"]
        t = s["topics"][idx]
        caption = s["captions"][idx]
        img = s["screenshots"][idx]
        try:
            send_channel(img, caption)
            send(cid, f"✅ 第{t['num']}篇已发布！", BTN_NEXT)
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
    print("✅ Edison Bot V2 启动！")
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
