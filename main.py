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

async def scrape_fb_posts():
    """扫描Facebook，抓取帖子文字+图片URL"""
    all_posts = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu"
        ])
        ctx = await browser.new_context(
            viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
            locale="zh-CN",
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"}
        )
        page = await ctx.new_page()

        for fb in FB_PAGES:
            try:
                print(f"扫描: {fb['url']}")
                await page.goto(fb["url"], wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(6000)

                # 关闭登录弹窗
                for selector in ['[aria-label="Close"]', '[data-testid="royal_login_form"] button']:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible():
                            await btn.click()
                            await page.wait_for_timeout(1000)
                    except:
                        pass

                # 滚动加载更多内容
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(2000)

                # 抓取帖子
                posts = await page.evaluate("""() => {
                    const results = [];
                    // 找所有帖子容器
                    const postContainers = document.querySelectorAll('[data-pagelet*="FeedUnit"], [role="article"]');
                    
                    postContainers.forEach(container => {
                        // 找文字
                        const textEl = container.querySelector('[data-ad-comet-preview="message"], [data-testid="post_message"], p, span');
                        const text = textEl ? textEl.innerText.trim() : '';
                        
                        // 找图片 - 找最大的图片
                        const imgs = [...container.querySelectorAll('img')].filter(img => {
                            const w = img.naturalWidth || img.width || 0;
                            const h = img.naturalHeight || img.height || 0;
                            const src = img.src || '';
                            return w > 300 && h > 200 && src.includes('facebook') && 
                                   (src.includes('scontent') || src.includes('fbcdn'));
                        });
                        
                        imgs.sort((a,b) => 
                            ((b.naturalWidth||b.width)*(b.naturalHeight||b.height)) - 
                            ((a.naturalWidth||a.width)*(a.naturalHeight||a.height))
                        );
                        
                        const imgSrc = imgs.length > 0 ? imgs[0].src : '';
                        
                        // 找链接
                        const links = [...container.querySelectorAll('a[href]')]
                            .map(a => a.href)
                            .filter(h => h.includes('sinchew') || h.includes('chinapress') || 
                                        h.includes('enanyang') || h.includes('orientaldaily') ||
                                        h.includes('malaymail') || h.includes('thestar'));
                        
                        if (text.length > 10 || imgSrc) {
                            results.push({
                                text: text.slice(0, 300),
                                img: imgSrc,
                                link: links[0] || ''
                            });
                        }
                    });
                    
                    return results.slice(0, 15);
                }""")

                for post in posts:
                    post["source"] = fb["name"]
                all_posts.extend(posts)
                print(f"✅ {fb['name']}: {len(posts)} 篇帖子")

            except Exception as e:
                print(f"❌ {fb['name']}: {e}")

        await browser.close()
    return all_posts

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
                img = None
                if img_url:
                    img = download_fb_image(img_url)

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
