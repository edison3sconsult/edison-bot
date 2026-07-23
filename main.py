import os, json, requests, time, anthropic, re, base64, asyncio, threading
from datetime import datetime
from playwright.async_api import async_playwright

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
AUTHORIZED_USER = int(os.environ["AUTHORIZED_USER"])
BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# ── Telegram ─────────────────────────────────────────
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
            files={"photo": ("news.jpg", img_bytes, "image/png")}, timeout=30).json()
    except:
        return {}

def send_channel(img_bytes, caption):
    try:
        if img_bytes:
            r = requests.post(f"{BASE}/sendPhoto",
                data={"chat_id": CHANNEL_ID, "caption": caption},
                files={"photo": ("news.jpg", img_bytes, "image/png")}, timeout=30).json()
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

# ── Claude ───────────────────────────────────────────
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
    return msg.content[0].text

SYSTEM = """你是Edison Lim (@edison_ttm) 的内容助手，专门为马来西亚华人生成爆款内容。

文案结构（timtiah风格）：
1. 钩子：具体场景或数字开头，画面感强
2. 背景：为什么重要，贴近马来西亚人日常
3. 数据：真实数字，朋友口吻
4. 立场：不偏不倚，传递「要有自己的判断」价值观
5. 评论引导：具体问题，让人忍不住留言

要求：口语化马来西亚华语、短句有节奏、用「—」分段、200-300字、加hashtag"""

# ── Playwright ───────────────────────────────────────
async def scrape_fb():
    pages = [
        "https://www.facebook.com/ChinaPressMY",
        "https://www.facebook.com/SinChewDaily",
        "https://www.facebook.com/nanyang.nysp",
    ]
    shots = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu"
        ])
        ctx = await browser.new_context(
            viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
        page = await ctx.new_page()
        for url in pages:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
                shots.append(await page.screenshot(full_page=False))
                await page.evaluate("window.scrollBy(0,800)")
                await page.wait_for_timeout(3000)
                shots.append(await page.screenshot(full_page=False))
            except Exception as e:
                print(f"FB截图失败 {url}: {e}")
        await browser.close()
    return shots

async def scrape_article(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu"
        ])
        ctx = await browser.new_context(
            viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            await page.evaluate("""() => {
                ['header','nav','footer','aside','.sidebar','[class*="ad"]',
                 '[id*="ad"]','[class*="banner"]','[class*="popup"]'].forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.style.display='none');
                });
                const title = document.querySelector('h1');
                const imgs = [...document.querySelectorAll('img')]
                    .filter(i => (i.naturalWidth||i.width)>300 && i.src &&
                        !i.src.includes('logo') && !i.src.includes('icon'));
                imgs.sort((a,b)=>((b.naturalWidth||b.width)*(b.naturalHeight||b.height))-
                    ((a.naturalWidth||a.width)*(a.naturalHeight||a.height)));
                const img = imgs[0];
                if(title && img){
                    document.body.innerHTML = `<div style="background:#fff;padding:30px;max-width:800px;margin:0 auto;font-family:sans-serif;">
                        <h1 style="font-size:24px;font-weight:800;color:#111;margin-bottom:20px;border-bottom:3px solid #e30000;padding-bottom:12px;">${title.textContent.trim()}</h1>
                        <img src="${img.src}" style="width:100%;border-radius:8px;" /></div>`;
                    document.body.style.cssText='margin:0;padding:0;background:#fff;';
                }
            }""")
            await page.wait_for_timeout(2000)
            return await page.screenshot(full_page=False)
        except Exception as e:
            print(f"文章截图失败: {e}")
            return None
        finally:
            await browser.close()

def analyze_fb_screenshots(shots):
    """Claude看截图，返回6个话题（纯文字，不是JSON）"""
    today = datetime.now().strftime("%Y年%m月%d日")
    b64s = [base64.standard_b64encode(s).decode() for s in shots[:6]]

    raw = ask_claude(f"""今天是{today}。以上是马来西亚三家中文媒体Facebook的截图。

分析截图，找出今日最热的6个话题。

用这个格式回复，每个话题一行，用|||分隔字段：
分类|||话题标题|||钩子句|||关键数据|||来源媒体

分类只能是：💼商业、📊金融、🧠人间清醒、❤️家庭情感

例子：
💼商业|||Tealive净利润跌58%|||Tealive 950家门店，净利润却跌了58%|||净利润从RM3,700万跌到RM2,146万|||南洋商报
📊金融|||RON95补贴省下的钱|||财政部省了RM80亿，但去了哪里？|||截至7月净省RM4亿升汽油|||星洲日报
🧠人间清醒|||森林城市网校19人失踪|||430人涉案，19人下落不明|||移民局调查非法出入境|||中国报
❤️家庭情感|||谢贤离世|||谢霆锋雇人照顾但不在身边，父亲走了|||89岁，7月16日肺炎离世|||东方日报
🧠人间清醒|||15岁无牌司机撞死人|||15岁，罗里，撞死摩托骑士，四个违规|||大马每年交通事故死亡超6000人|||星洲日报
📊金融|||特朗普关税重启|||7月24日大马税率升至10-12.5%|||大马出口美国占比12%|||南洋商报

只回复6行，不要任何其他文字。""", images_b64=b64s)

    topics = []
    for i, line in enumerate(raw.strip().split("\n")):
        line = line.strip()
        if not line or "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) >= 5:
            topics.append({
                "num": i+1,
                "cat": parts[0].strip(),
                "topic": parts[1].strip(),
                "hook": parts[2].strip(),
                "data": parts[3].strip(),
                "source": parts[4].strip(),
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
    return ask_claude(f"""原文案：\n{original}\n\n用户反馈：{feedback}\n话题：{t['topic']}\n\n根据反馈优化，保持timtiah结构200-300字，只回复新文案。""", SYSTEM)

def get_article_url(t):
    url = ask_claude(f"""话题：{t['topic']}，来源：{t['source']}，数据：{t['data']}

请给我这篇新闻最可能的真实URL。
只回复URL，不要任何其他文字。""")
    url = url.strip()
    return url if url.startswith("http") else None

# ── 按钮 ─────────────────────────────────────────────
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

# ── 状态 ─────────────────────────────────────────────
state = {}

def get_s(uid):
    if uid not in state:
        state[uid] = {"step":"idle","topics":[],"captions":[],"screenshots":[],"idx":0}
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
        send(cid, "⚡ 正在打开三家中文媒体Facebook截图，请稍等约1分钟...")
        def run():
            try:
                shots = asyncio.run(scrape_fb())
                send(cid, f"📸 截了{len(shots)}张，Claude正在分析选出6个爆款话题...")
                topics = analyze_fb_screenshots(shots)
                if not topics:
                    send(cid, "❌ 分析失败，请重试")
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
        send(cid, "📸 正在截取新闻配图，请稍等...")
        def run():
            try:
                url = get_article_url(t)
                if url:
                    img = asyncio.run(scrape_article(url))
                    if img:
                        s["screenshots"][idx] = img
                        r = send_photo_bytes(cid, img, f"🖼️ 配图预览（{t['source']}）")
                        if r.get("ok"):
                            send(cid, "满意就发布 👇", BTN_PUBLISH)
                            return
                send(cid, "⚠️ 未能截到配图，直接发布文案？", BTN_PUBLISH)
            except Exception as e:
                send(cid, f"⚠️ 截图失败，直接发布文案？", BTN_PUBLISH)
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

# ── 主循环 ───────────────────────────────────────────
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
