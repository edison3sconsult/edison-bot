import os, json, requests, time, anthropic, re, base64, asyncio, threading
from datetime import datetime
from playwright.async_api import async_playwright

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

FB_PAGES = [
    {"name": "中国报", "url": "https://www.facebook.com/ChinaPressMY"},
    {"name": "星洲日报", "url": "https://www.facebook.com/SinChewDaily"},
    {"name": "南洋商报", "url": "https://www.facebook.com/nanyang.nysp"},
]

def scrape_fb_with_scrapingbee():
    """用ScrapingBee访问Facebook，绕过反爬虫"""
    all_posts = []
    
    fb_pages = [
        {"name": "中国报", "url": "https://www.facebook.com/ChinaPressMY"},
        {"name": "星洲日报", "url": "https://www.facebook.com/SinChewDaily"},
        {"name": "南洋商报", "url": "https://www.facebook.com/nanyang.nysp"},
    ]
    
    for fb in fb_pages:
        try:
            print(f"ScrapingBee抓取: {fb['url']}")
            r = requests.get(
                "https://app.scrapingbee.com/api/v1/",
                params={
                    "api_key": SCRAPINGBEE_KEY,
                    "url": fb["url"],
                    "render_js": "true",
                    "wait": "5000",
                    "window_width": "1280",
                    "window_height": "900",
                },
                timeout=60
            )
            
            print(f"ScrapingBee状态: {r.status_code}, 长度: {len(r.content)}")
            if r.status_code != 200:
                print(f"❌ {fb['name']}: {r.status_code} - {r.text[:200]}")
                continue
            
            html = r.text
            print(f"HTML前300字: {html[:300]}")
            
            # 从HTML提取图片URL (scontent = Facebook CDN图片)
            img_urls = re.findall(r"(https://scontent[^\"'\s]+\.(?:jpg|jpeg|png|webp)(?:[^\"'\s]*)?)", html)
            
            # 提取文字内容
            texts = re.findall(r'"message":\{"text":"([^"]{20,300})"', html)
            if not texts:
                # 备用：找中文内容
                texts = re.findall(r"[\u4e00-\u9fff][^\n<\"]{20,200}", html)

            
            print(f"✅ {fb['name']}: {len(img_urls)}张图, {len(texts)}条文字")
            
            # 配对文字和图片
            for i, text in enumerate(texts[:10]):
                img = img_urls[i] if i < len(img_urls) else ""
                all_posts.append({
                    "source": fb["name"],
                    "text": text[:200],
                    "img": img,
                })
                
        except Exception as e:
            print(f"❌ {fb['name']}: {e}")
    
    return all_posts

def download_image_scrapingbee(img_url):
    """用ScrapingBee下载图片"""
    if not img_url:
        return None
    try:
        # 先直接试下载（Facebook CDN图片有时可以直接下）
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.facebook.com/",
        }
        r = requests.get(img_url, headers=headers, timeout=15)
        if r.status_code == 200 and len(r.content) > 5000:
            print(f"✅ 直接下载成功")
            return r.content
    except:
        pass
    
    try:
        # 用ScrapingBee下载
        r = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": SCRAPINGBEE_KEY,
                "url": img_url,
                "render_js": "false",
            },
            timeout=30
        )
        if r.status_code == 200 and len(r.content) > 5000:
            print(f"✅ ScrapingBee下载成功")
            return r.content
    except Exception as e:
        print(f"图片下载失败: {e}")
    
    return None

def search_google_image(topic):
    """用ScrapingBee搜索Google Images"""
    try:
        query = topic + " Malaysia 2026"
        search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&tbm=isch"
        
        r = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": SCRAPINGBEE_KEY,
                "url": search_url,
                "render_js": "true",
                "wait": "3000",
            },
            timeout=45
        )
        
        if r.status_code != 200:
            return None
            
        # 找图片URL
        urls = re.findall(r'(https://[^"\s]+\.(?:jpg|jpeg|png|webp))', r.text)
        urls = [u for u in urls if not any(k in u for k in ['google','gstatic','logo','icon'])]
        
        if urls:
            # 下载第一张
            img_r = requests.get(urls[0], timeout=10)
            if img_r.status_code == 200 and len(img_r.content) > 5000:
                print(f"✅ Google图片找到: {urls[0][:60]}")
                return img_r.content
    except Exception as e:
        print(f"Google图片搜索失败: {e}")
    return None

def get_best_image(topic, source, img_url):
    """获取最佳配图"""
    # 1. 先试Facebook帖子图片
    if img_url:
        img = download_image_scrapingbee(img_url)
        if img:
            return img
    
    # 2. Google Images搜索
    img = search_google_image(topic)
    if img:
        return img
    
    # 3. 备用：Unsplash
    try:
        keyword_map = {
            "关税": "tariff trade", "令吉": "malaysia ringgit",
            "油价": "petrol fuel", "RON95": "petrol pump",
            "选举": "malaysia election", "谢贤": "hong kong actor",
            "交通": "traffic accident", "AI": "artificial intelligence",
            "华为": "huawei technology", "诈骗": "fraud scam",
        }
        kw = next((v for k,v in keyword_map.items() if k in topic), "malaysia news")
        r = requests.get(f"https://source.unsplash.com/800x500/?{requests.utils.quote(kw)}", 
                        timeout=15, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 5000:
            print("✅ Unsplash备用图片")
            return r.content
    except:
        pass
    
    return None

async def scrape_fb_posts():
    """兼容接口，实际用ScrapingBee"""
    return scrape_fb_with_scrapingbee()

def download_fb_image(img_url):
    """下载Facebook帖子图片"""
    if not img_url:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.facebook.com/",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        }
        r = requests.get(img_url, headers=headers, timeout=15)
        if r.status_code == 200 and len(r.content) > 5000:
            return r.content
    except Exception as e:
        print(f"下载图片失败: {e}")
    return None

def select_topics(posts):
    """Claude分析帖子，选出6个爆款话题"""
    today = datetime.now().strftime("%Y年%m月%d日")

    posts_text = f"今天是{today}。以下是马来西亚三家中文媒体Facebook今日帖子：\n\n"
    for i, p in enumerate(posts[:30]):
        posts_text += f"{i+1}. [{p['source']}] {p['text'][:150]}\n"
    posts_text += "\n"

    posts_text += """请从以上帖子中选出6个最有爆款潜力的话题。

选题标准：有争议性、有情绪共鸣、贴近马来西亚华人日常、多家媒体出现的优先。

严格按以下格式回复，每行一个话题，用|||分隔，共6行：
分类|||话题标题|||钩子句|||关键数据|||来源媒体|||帖子编号

分类只能是：💼商业、📊金融、🧠人间清醒、❤️家庭情感

只回复6行，不要任何其他文字。"""

    raw = ask_claude(posts_text)
    print(f"Claude选题：\n{raw[:400]}")

    topics = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) >= 5:
            # 找对应帖子的图片
            post_idx = -1
            if len(parts) >= 6:
                try:
                    post_idx = int(re.search(r'\d+', parts[5]).group()) - 1
                except:
                    pass

            img_url = ""
            if 0 <= post_idx < len(posts):
                img_url = posts[post_idx].get("img", "")

            topics.append({
                "num": len(topics)+1,
                "cat": parts[0].strip(),
                "topic": parts[1].strip(),
                "hook": parts[2].strip(),
                "data": parts[3].strip(),
                "source": parts[4].strip(),
                "img_url": img_url,
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
        send(cid, "⚡ 正在打开三家Facebook扫描今日热帖，请稍等约1分钟...")
        def run():
            try:
                posts = asyncio.run(scrape_fb_posts())
                if not posts:
                    send(cid, "❌ Facebook扫描失败，请重试")
                    return
                send(cid, f"📰 扫描到{len(posts)}条帖子，Claude正在选出6个爆款话题...")
                topics = select_topics(posts)
                if not topics:
                    send(cid, "❌ 选题失败，请重试")
                    return
                s.update({"topics":topics,"captions":[""]*len(topics),
                          "screenshots":[None]*len(topics),
                          "posts": posts,
                          "idx":0,"step":"show_topics"})
                lines = "🗞️ 今日6个爆款话题：\n\n"
                for t in topics:
                    has_img = "🖼️" if t.get("img_url") else "📝"
                    lines += f"{t['num']}. {has_img} {t['cat']} — {t['topic']}\n"
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
        send(cid, "📸 正在获取Facebook配图...")
        def run():
            try:
                img_url = t.get("img_url", "")
                img = get_best_image(t["topic"], t["source"], img_url)

                if img:
                    s["screenshots"][idx] = img
                    r = send_photo_bytes(cid, img, f"🖼️ Facebook配图（{t['source']}）")
                    if r.get("ok"):
                        send(cid, "满意就发布 👇", BTN_PUBLISH)
                        return

                # 没有图片就直接问要不要发布
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
