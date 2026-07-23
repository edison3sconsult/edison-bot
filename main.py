import os, json, requests, time, anthropic, re
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
AUTHORIZED_USER = int(os.environ["AUTHORIZED_USER"])
BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

def tg_post(method, **kwargs):
    return requests.post(f"{BASE}/{method}", json=kwargs, timeout=30).json()

def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return requests.post(f"{BASE}/sendMessage", json=data).json()

def send_photo(chat_id, photo_url, caption, reply_markup=None):
    data = {"chat_id": chat_id, "photo": photo_url, "caption": caption}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return requests.post(f"{BASE}/sendPhoto", json=data).json()

def answer_callback(cb_id):
    requests.post(f"{BASE}/answerCallbackQuery", json={"callback_query_id": cb_id})

def ask_claude(prompt, system=""):
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system or "你是Edison Lim的马来西亚华语内容助手。",
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

def get_og_image(url):
    """抓取新闻页面的og:image"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', r.text)
        if match:
            return match.group(1)
        match = re.search(r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']', r.text)
        if match:
            return match.group(1)
    except:
        pass
    return None

SYSTEM = """你是Edison Lim (@edison_ttm) 的内容助手，专门为马来西亚华人生成爆款内容。

文案结构（timtiah风格）：
1. 钩子：具体场景或数字开头，画面感强，让人停下来
2. 背景：为什么重要，贴近马来西亚人日常
3. 数据：真实数字，朋友口吻，不是"根据报告显示"
4. 立场：不偏不倚，引发思考，传递「要有自己的判断」价值观
5. 评论引导：具体问题，让人忍不住留言

要求：口语化马来西亚华语、短句有节奏、用「—」分段、200-300字、加hashtag、段落间单行换行"""

BTN_CAPTION = {"inline_keyboard": [[
    {"text": "✅ 文案满意", "callback_data": "caption_ok"},
    {"text": "✏️ 修改文案", "callback_data": "caption_edit"}
]]}

BTN_IMAGE = {"inline_keyboard": [[
    {"text": "✅ 发布到频道", "callback_data": "publish"},
    {"text": "⏭️ 跳过，下一篇", "callback_data": "next"}
]]}

BTN_NEXT = {"inline_keyboard": [[
    {"text": "▶️ 下一篇", "callback_data": "next"},
    {"text": "🏁 今天完成", "callback_data": "done"}
]]}

state = {}

def get_s(uid):
    if uid not in state:
        state[uid] = {"step": "idle", "topics": [], "captions": [], "images": [], "idx": 0}
    return state[uid]

def gen_topics():
    today = datetime.now().strftime("%Y年%m月%d日")
    raw = ask_claude(f"""今天是{today}。

找出马来西亚今日最热的6个话题，分别属于：💼商业、📊金融、🧠人间清醒、❤️家庭情感。

选题标准：
- 2-3天内在中国报、星洲日报、南洋商报出现过
- 有争议性或情绪共鸣
- 有具体数据或名人事件

必须提供真实可访问的新闻链接。

只回复JSON数组，不要其他文字：
[
  {{"num":1,"cat":"💼 商业","topic":"话题标题","hook":"钩子句","data":"关键数据","source":"来源媒体","url":"https://真实新闻链接"}},
  {{"num":2,"cat":"📊 金融","topic":"话题标题","hook":"钩子句","data":"关键数据","source":"来源媒体","url":"https://真实新闻链接"}},
  {{"num":3,"cat":"🧠 人间清醒","topic":"话题标题","hook":"钩子句","data":"关键数据","source":"来源媒体","url":"https://真实新闻链接"}},
  {{"num":4,"cat":"❤️ 家庭情感","topic":"话题标题","hook":"钩子句","data":"关键数据","source":"来源媒体","url":"https://真实新闻链接"}},
  {{"num":5,"cat":"🧠 人间清醒","topic":"话题标题","hook":"钩子句","data":"关键数据","source":"来源媒体","url":"https://真实新闻链接"}},
  {{"num":6,"cat":"📊 金融","topic":"话题标题","hook":"钩子句","data":"关键数据","source":"来源媒体","url":"https://真实新闻链接"}}
]""")
    raw = raw.strip().strip("```json").strip("```").strip()
    return json.loads(raw)

def gen_caption(t):
    return ask_claude(f"""话题：{t['topic']}
分类：{t['cat']}
钩子参考：{t['hook']}
关键数据：{t['data']}（来源：{t['source']}）

按timtiah结构写200-300字Instagram文案。
段落之间单行换行，不要空行太多。
只回复文案本身，不要任何说明。""", SYSTEM)

def optimize(original, feedback, t):
    return ask_claude(f"""原文案：
{original}

用户反馈：{feedback}
话题：{t['topic']}

根据反馈优化，保持timtiah结构200-300字，只回复新文案。""", SYSTEM)

def handle_msg(msg):
    uid = msg["from"]["id"]
    cid = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if uid != AUTHORIZED_USER:
        return
    s = get_s(uid)

    if text in ["开始", "给我今天的内容", "今天的内容", "/start", "/content"]:
        send(cid, "⚡ 正在搜索今日马来西亚热点，请稍等约30秒...")
        try:
            topics = gen_topics()
            s.update({"topics": topics, "captions": [""]*len(topics), "images": [""]*len(topics), "idx": 0, "step": "show_topics"})
            
            # 预先抓取所有图片
            send(cid, "🖼️ 正在抓取新闻配图...")
            for i, t in enumerate(topics):
                img = get_og_image(t.get("url", ""))
                s["images"][i] = img or ""
            
            lines = "🗞️ 今日6个话题：\n\n"
            for t in topics:
                lines += f"{t['num']}. {t['cat']} — {t['topic']}\n"
            lines += "\n点下面按钮开始生成文案 👇"
            send(cid, lines, {"inline_keyboard": [[{"text": "⚡ 开始逐篇生成", "callback_data": "generate"}]]})
        except Exception as e:
            send(cid, f"❌ 搜索失败：{e}\n\n请重试")
        return

    if s["step"] == "editing":
        t = s["topics"][s["idx"]]
        send(cid, "✏️ 优化中，请稍等...")
        try:
            new = optimize(s["captions"][s["idx"]], text, t)
            s["captions"][s["idx"]] = new
            s["step"] = "review_caption"
            send(cid, f"📝 优化后文案：\n\n{new}", BTN_CAPTION)
        except Exception as e:
            send(cid, f"❌ 优化失败：{e}")
        return

    if s["step"] == "idle" or text == "/help":
        send(cid, "👋 发「给我今天的内容」开始生成今日6篇 ⚡")
        return

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
        send(cid, f"✍️ 正在生成第{t['num']}/6篇...\n{t['cat']} — {t['topic']}")
        try:
            caption = gen_caption(t)
            s["captions"][idx] = caption
            s["step"] = "review_caption"
            
            # 显示配图预览
            img = s["images"][idx]
            if img:
                send_photo(cid, img, f"🖼️ 配图预览\n来源：{t['source']}")
            else:
                send(cid, f"⚠️ 未能抓到配图（来源：{t['source']}）\n可以手动添加图片")
            
            send(cid, f"📝 第{t['num']}/6 文案：\n\n{caption}", BTN_CAPTION)
        except Exception as e:
            send(cid, f"❌ 生成失败：{e}")
        return

    if data == "caption_ok":
        s["step"] = "review_image"
        send(cid, "✅ 文案确认！\n\n图片满意就发布，或者跳到下一篇。", BTN_IMAGE)
        return

    if data == "caption_edit":
        s["step"] = "editing"
        send(cid, "✏️ 告诉我哪里要改：")
        return

    if data == "publish":
        idx = s["idx"]
        t = s["topics"][idx]
        caption = s["captions"][idx]
        img = s["images"][idx]
        try:
            if img:
                # 发图片+文案到频道
                requests.post(f"{BASE}/sendPhoto", json={
                    "chat_id": CHANNEL_ID,
                    "photo": img,
                    "caption": caption
                })
            else:
                # 只发文案
                requests.post(f"{BASE}/sendMessage", json={"chat_id": CHANNEL_ID, "text": caption})
            
            send(cid, f"✅ 第{t['num']}篇已发布到频道！", BTN_NEXT)
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
                 {"inline_keyboard": [[{"text": "⚡ 生成文案", "callback_data": "generate"}]]})
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
                           params={"offset": offset, "timeout": 30}, timeout=35)
            for u in r.json().get("result", []):
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
