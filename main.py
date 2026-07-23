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
    return requests.post(f"{BASE}/sendMessage", json=data, timeout=30).json()

def send_photo_bytes(chat_id, img_bytes, caption, reply_markup=None):
    data = {"chat_id": chat_id, "caption": caption}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return requests.post(f"{BASE}/sendPhoto", data=data,
        files={"photo": ("news.jpg", img_bytes, "image/jpeg")}, timeout=30).json()

def send_channel_photo(img_bytes, caption):
    return requests.post(f"{BASE}/sendPhoto",
        data={"chat_id": CHANNEL_ID, "caption": caption},
        files={"photo": ("news.jpg", img_bytes, "image/jpeg")}, timeout=30).json()

def send_channel_text(text):
    return requests.post(f"{BASE}/sendMessage",
        json={"chat_id": CHANNEL_ID, "text": text}, timeout=30).json()

def answer_callback(cb_id):
    requests.post(f"{BASE}/answerCallbackQuery", json={"callback_query_id": cb_id})

SYSTEM = """你是Edison Lim (@edison_ttm) 的内容助手，专门为马来西亚华人生成爆款内容。

文案结构（timtiah风格）：
1. 钩子：具体场景或数字开头，画面感强
2. 背景：为什么重要，贴近马来西亚人日常
3. 数据：真实数字，朋友口吻
4. 立场：不偏不倚，传递「要有自己的判断」价值观
5. 评论引导：具体问题，让人忍不住留言

要求：口语化马来西亚华语、短句有节奏、用「—」分段、200-300字、加hashtag"""

FB_PAGES = [
    ("中国报", "https://www.facebook.com/ChinaPressMY"),
    ("星洲日报", "https://www.facebook.com/SinChewDaily"),
    ("南洋商报", "https://www.facebook.com/nanyang.nysp"),
]

async def scrape_fb():
    """截图三家Facebook页面"""
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu"
        ])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
        page = await ctx.new_page()

        for name, url in FB_PAGES:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
                # 截两屏
                for scroll in [0, 800, 1600]:
                    await page.evaluate(f"window.scrollTo(0, {scroll})")
                    await page.wait_for_timeout(2000)
                    img = await page.screenshot(type="jpeg", quality=80)
                    results.append({"name": name, "img": img})
            except Exception as e:
                print(f"FB截图失败 {name}: {e}")

        await browser.close()
    return results

def analyze_screenshots(screenshots):
    """把Facebook截图发给Claude，让它从截图里分析出6个话题"""
    content = []
    for s in screenshots:
        b64 = base64.standard_b64encode(s["img"]).decode()
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg", "data": b64
        }})

    today = datetime.now().strftime("%Y年%m月%d日")
    content.append({"type": "text", "text": f"""今天是{today}。

以上是马来西亚三家中文媒体（中国报、星洲日报、南洋商报）Facebook页面的真实截图。

请仔细看这些截图，找出今日互动最高、最有爆款潜力的6个话题。

重要规则：
- 只能选截图里真实看到的新闻
- 不能编造任何话题
- 如果截图不清晰，描述你看到的内容

回复格式，只回复JSON数组：
[
  {{"num":1,"cat":"💼 商业","topic":"截图中看到的真实话题标题","hook":"钩子句","data":"截图中的真实数据","source":"媒体名称"}},
  {{"num":2,"cat":"📊 金融","topic":"截图中看到的真实话题标题","hook":"钩子句","data":"截图中的真实数据","source":"媒体名称"}},
  {{"num":3,"cat":"🧠 人间清醒","topic":"截图中看到的真实话题标题","hook":"钩子句","data":"截图中的真实数据","source":"媒体名称"}},
  {{"num":4,"cat":"❤️ 家庭情感","topic":"截图中看到的真实话题标题","hook":"钩子句","data":"截图中的真实数据","source":"媒体名称"}},
  {{"num":5,"cat":"🧠 人间清醒","topic":"截图中看到的真实话题标题","hook":"钩子句","data":"截图中的真实数据","source":"媒体名称"}},
  {{"num":6,"cat":"📊 金融","topic":"截图中看到的真实话题标题","hook":"钩子句","data":"截图中的真实数据","source":"媒体名称"}}
]"""})

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        start = raw.index('[')
        end = raw.rindex(']') + 1
        return json.loads(raw[start:end])

async def screenshot_article(url):
    """截取新闻文章，只留标题+主图"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu"
        ])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            await page.evaluate("""() => {
                ['header','nav','footer','aside','[class*="ad"]','[id*="ad"]',
                 '[class*="banner"]','[class*="popup"]','.social-share','.related',
                 '.newsletter','iframe'].forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.style.display='none');
                });
                const title = document.querySelector('h1');
                const img = [...document.querySelectorAll('img')]
                    .filter(i => (i.naturalWidth||i.width) > 300 && i.src &&
                        !i.src.includes('logo') && !i.src.includes('icon'))
                    .sort((a,b) => (b.naturalWidth*b.naturalHeight)-(a.naturalWidth*a.naturalHeight))[0];
                if (title && img) {
                    document.body.innerHTML = `<div style="background:#fff;padding:30px;max-width:800px;margin:0 auto;font-family:sans-serif;">
                        <h1 style="font-size:24px;font-weight:800;color:#111;margin-bottom:20px;border-bottom:3px solid #e30000;padding-bottom:12px;">${title.textContent.trim()}</h1>
                        <img src="${img.src}" style="width:100%;border-radius:8px;display:block;" /></div>`;
                    document.body.style.cssText = 'margin:0;padding:0;background:#fff;';
                }
            }""")
            await page.wait_for_timeout(2000)
            return await page.screenshot(type="jpeg", quality=85)
        except Exception as e:
            print(f"文章截图失败: {e}")
            return None
        finally:
            await browser.close()

def gen_caption(t):
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": f"""话题：{t['topic']}
分类：{t['cat']}
钩子参考：{t['hook']}
关键数据：{t['data']}（来源：{t['source']}）

按timtiah结构写200-300字Instagram文案。段落间单行换行。只回复文案本身。"""}]
    )
    return msg.content[0].text

def optimize(original, feedback, t):
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": f"原文案：\n{original}\n\n用户反馈：{feedback}\n话题：{t['topic']}\n\n根据反馈优化，保持timtiah结构200-300字，只回复新文案。"}]
    )
    return msg.content[0].text

BTN_CAPTION = {"inline_keyboard": [[
    {"text": "✅ 文案满意", "callback_data": "caption_ok"},
    {"text": "✏️ 修改文案", "callback_data": "caption_edit"}
]]}
BTN_PUBLISH = {"inline_keyboard": [[
    {"text": "✅ 发布到频道", "callback_data": "publish"},
    {"text": "⏭️ 下一篇", "callback_data": "next"}
]]}
BTN_NEXT = {"inline_keyboard": [[
    {"text": "▶️ 下一篇", "callback_data": "next"},
    {"text": "🏁 今天完成", "callback_data": "done"}
]]}

state = {}

def get_s(uid):
    if uid not in state:
        state[uid] = {"step":"idle","topics":[],"captions":[],"screenshots":[],"idx":0}
    return state[uid]

def handle_msg(msg):
    uid = msg["from"]["id"]
    cid = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if uid != AUTHORIZED_USER:
        return
    s = get_s(uid)

    if text in ["开始","给我今天的内容","今天的内容","/start","/content"]:
        send(cid, "⚡ 正在打开Facebook截图，请稍等约1-2分钟...")

        def run():
            try:
                send(cid, "📸 截图中：中国报、星洲日报、南洋商报...")
                screenshots = asyncio.run(scrape_fb())
                send(cid, f"✅ 已截 {len(screenshots)} 张截图\n🤖 Claude正在分析热点话题...")

                topics = analyze_screenshots(screenshots)
                s.update({"topics":topics,"captions":[""]*len(topics),
                          "screenshots":[None]*len(topics),"idx":0,"step":"show_topics"})

                lines = "🗞️ 今日6个爆款话题：\n\n"
                for t in topics:
                    lines += f"{t['num']}. {t['cat']} — {t['topic']}\n"
                lines += "\n点下面按钮开始逐篇生成 👇"
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
            send(cid, f"❌ 优化失败：{e}")
        return

    send(cid, "👋 发「给我今天的内容」开始 ⚡")

def handle_callback(cb):
    uid = cb["from"]["id"]
    cid = cb["message"]["chat"]["id"]
    data = cb["data"]
    answer_callback(cb["id"])
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
        send(cid, "📸 正在搜索并截取新闻配图...")

        def run():
            try:
                # 用Google搜索找新闻URL
                search_q = f"{t['topic']} site:sinchew.com.my OR site:chinapress.com.my OR site:enanyang.my OR site:orientaldaily.com.my"
                search_r = requests.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"q": search_q, "num": 1,
                            "key": os.environ.get("GOOGLE_API_KEY",""),
                            "cx": os.environ.get("GOOGLE_CX","")},
                    timeout=10
                ).json()
                
                news_url = None
                if "items" in search_r:
                    news_url = search_r["items"][0]["link"]
                
                if news_url:
                    img_bytes = asyncio.run(screenshot_article(news_url))
                    if img_bytes:
                        s["screenshots"][idx] = img_bytes
                        r = send_photo_bytes(cid, img_bytes, f"🖼️ 配图\n来源：{t['source']}")
                        if r.get("ok"):
                            send(cid, "满意就发布到频道 👇", BTN_PUBLISH)
                            return

                send(cid, "⚠️ 未找到配图，直接发布文案？", BTN_PUBLISH)
            except Exception as e:
                send(cid, f"⚠️ 截图失败，直接发布文案？\n({e})", BTN_PUBLISH)

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
        img_bytes = s["screenshots"][idx]
        try:
            if img_bytes:
                r = send_channel_photo(img_bytes, caption)
                if not r.get("ok"):
                    send_channel_text(caption)
            else:
                send_channel_text(caption)
            send(cid, f"✅ 第{t['num']}篇已发布！", BTN_NEXT)
            s["step"] = "published"
        except Exception as e:
            send(cid, f"❌ 发布失败：{e}")
        return

    if data == "next":
        s["idx"] += 1
        if s["idx"] >= len(s["topics"]):
            send(cid, "🎉 今日6篇全部完成！\n\n明天发「给我今天的内容」继续。")
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
            for u in r.json().get("result",[]):
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
