import os, json, requests, time, anthropic, re, asyncio, threading
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
AUTHORIZED_USER = int(os.environ["AUTHORIZED_USER"])
SCRAPINGBEE_KEY = os.environ.get("SCRAPINGBEE_KEY", "QNEIXTNF4SKJV562MWIFDUR52VYK4R2D8XAFA5HLLAEID57WUH0TM5KOFTAIRIG7CBBRLUV4QPBCLH62")
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
            files={"photo": ("news.jpg", img_bytes, "image/jpeg")}, timeout=30).json()
    except:
        return {}

def send_channel(img_bytes, caption):
    try:
        if img_bytes:
            r = requests.post(f"{BASE}/sendPhoto",
                data={"chat_id": CHANNEL_ID, "caption": caption},
                files={"photo": ("news.jpg", img_bytes, "image/jpeg")}, timeout=30).json()
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

NEWS_SITES = [
    {"name": "星洲日报", "url": "https://www.sinchew.com.my"},
    {"name": "中国报", "url": "https://www.chinapress.com.my"},
    {"name": "南洋商报", "url": "https://www.enanyang.my"},
    {"name": "东方日报", "url": "https://www.orientaldaily.com.my"},
]

def scrape_with_bee(url, render_js=True, wait=3000):
    """用ScrapingBee抓取任何页面"""
    r = requests.get(
        "https://app.scrapingbee.com/api/v1/",
        params={
            "api_key": SCRAPINGBEE_KEY,
            "url": url,
            "render_js": "true" if render_js else "false",
            "wait": str(wait),
        },
        timeout=60
    )
    print(f"ScrapingBee {url[:50]}: {r.status_code}, {len(r.content)} bytes")
    if r.status_code == 200:
        return r.text
    return None

def scrape_news_sites():
    """抓取新闻网站，提取今日新闻列表"""
    all_articles = []

    for site in NEWS_SITES:
        try:
            html = scrape_with_bee(site["url"])
            if not html:
                continue

            # 提取所有链接和标题
            links = re.findall(r'href=["\']([^"\']+)["\'][^>]*>([^<]{10,150})<', html)
            
            for href, text in links:
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) < 10 or len(text) > 200:
                    continue
                # 过滤非新闻链接
                if any(k in href.lower() for k in ['#','javascript','mailto','facebook','twitter']):
                    continue
                # 只要该媒体自己的链接
                domain = site["url"].replace("https://www.", "")
                if domain not in href and not href.startswith("/"):
                    continue
                    
                full_url = href if href.startswith("http") else site["url"] + href
                all_articles.append({
                    "title": text,
                    "url": full_url,
                    "source": site["name"]
                })

            print(f"✅ {site['name']}: {len([a for a in all_articles if a['source']==site['name']])} 篇")
        except Exception as e:
            print(f"❌ {site['name']}: {e}")

    return all_articles

def select_topics(articles):
    """Claude选出6个爆款话题"""
    today = datetime.now().strftime("%Y年%m月%d日")
    
    news_text = f"今天是{today}。以下是马来西亚中文媒体今日新闻：\n\n"
    for i, a in enumerate(articles[:60]):
        news_text += f"{i+1}. [{a['source']}] {a['title']} | {a['url']}\n"
    
    news_text += """\n请选出6个最有爆款潜力的话题。

选题标准：有争议性、有情绪共鸣、有数据、贴近马来西亚华人日常。

严格按以下格式回复，每行用|||分隔，共6行：
分类|||话题标题|||钩子句|||关键数据|||来源媒体|||新闻URL

分类只能是：💼商业、📊金融、🧠人间清醒、❤️家庭情感

只回复6行，不要任何其他文字。"""

    raw = ask_claude(news_text)
    print(f"Claude选题：\n{raw[:400]}")

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

def get_article_image(article_url, topic):
    """用ScrapingBee打开文章，提取og:image并下载"""
    if not article_url or not article_url.startswith("http"):
        return None
    
    try:
        print(f"抓取文章图片: {article_url[:80]}")
        html = scrape_with_bee(article_url, render_js=True, wait=3000)
        if not html:
            return None

        # 找og:image
        og_matches = re.findall(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']',
            html
        )
        if not og_matches:
            og_matches = re.findall(
                r'content=["\'](https?://[^"\'>\s]+)["\'][^>]+property=["\']og:image["\']',
                html
            )
        
        # 也找twitter:image
        if not og_matches:
            og_matches = re.findall(
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']',
                html
            )

        print(f"找到{len(og_matches)}个图片URL")
        
        for img_url in og_matches[:3]:
            img_url = img_url.replace("&amp;", "&")
            # 排除广告/图标
            if any(k in img_url.lower() for k in ['logo','icon','favicon','banner','default']):
                continue
            
            print(f"下载: {img_url[:80]}")
            # 用ScrapingBee下载图片（绕过防盗链）
            r = requests.get(
                "https://app.scrapingbee.com/api/v1/",
                params={
                    "api_key": SCRAPINGBEE_KEY,
                    "url": img_url,
                    "render_js": "false",
                },
                timeout=30
            )
            print(f"图片下载: {r.status_code}, {len(r.content)} bytes, {r.headers.get('content-type','')}")
            if r.status_code == 200 and len(r.content) > 10000:
                ct = r.headers.get('content-type', '')
                if any(t in ct for t in ['image','jpeg','png','webp','jpg']):
                    print("✅ 图片下载成功")
                    return r.content
                    
    except Exception as e:
        print(f"文章图片失败: {e}")
    
    return None

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
        send(cid, "⚡ 正在扫描星洲日报、中国报、南洋商报、东方日报，请稍等约1分钟...")
        def run():
            try:
                articles = scrape_news_sites()
                if not articles:
                    send(cid, "❌ 扫描失败，请重试")
                    return
                send(cid, f"📰 扫描到{len(articles)}篇新闻，Claude正在选出6个爆款话题...")
                topics = select_topics(articles)
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
        send(cid, "📸 正在获取新闻配图，请稍等约30秒...")
        def run():
            try:
                img = get_article_image(t.get("url",""), t["topic"])
                if img:
                    s["screenshots"][idx] = img
                    r = send_photo_bytes(cid, img, f"🖼️ 配图预览（{t['source']}）")
                    if r.get("ok"):
                        send(cid, "满意就发布 👇", BTN_PUBLISH)
                        return
                send(cid, "⚠️ 未能获取配图，直接发布文案？", BTN_PUBLISH)
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
