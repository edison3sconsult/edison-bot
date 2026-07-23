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

# 排除关键词——广告/logo/无关图片
EXCLUDE_KEYWORDS = [
    'logo','icon','avatar','banner','ad','sponsor','grab','shopee',
    'lazada','tiktok','facebook','youtube','twitter','instagram',
    'apple','google','whatsapp','telegram','qrcode','qr-code',
    'payment','pay','wallet','button','gif','pixel','tracker',
    '1x1','placeholder','blank','loading','spinner'
]

async def scrape_news_with_links():
    """截图新闻网站，同时抓取新闻列表"""
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
                print(f"扫描: {site['url']}")
                await page.goto(site["url"], wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)
                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                except:
                    pass

                # 抓新闻链接
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
                print(f"✅ {site['name']}: {len(articles)} 篇新闻")
            except Exception as e:
                print(f"❌ {site['name']} 失败: {e}")
        await browser.close()
    return results

async def screenshot_article(url):
    """截取文章主图+标题，严格过滤广告图片"""
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

            # 隐藏广告和无关元素
            await page.evaluate("""() => {
                const hideSelectors = [
                    'header','nav','footer','aside','.sidebar',
                    '[class*="ad"]','[id*="ad"]','[class*="banner"]',
                    '[class*="popup"]','[class*="modal"]',
                    '[class*="newsletter"]','[class*="subscribe"]',
                    '[class*="social"]','[class*="share"]',
                    '[class*="related"]','[class*="recommend"]',
                    'iframe','video','script','style',
                    '[class*="widget"]','[class*="sponsor"]'
                ];
                hideSelectors.forEach(sel => {
                    try {
                        document.querySelectorAll(sel).forEach(el => {
                            el.style.display = 'none';
                        });
                    } catch(e) {}
                });
            }""")

            # 找标题和主图
            result = await page.evaluate("""(excludeKeywords) => {
                const title = document.querySelector('h1');
                if (!title) return null;

                // 找所有图片，严格过滤
                const allImgs = [...document.querySelectorAll('img')];
                const validImgs = allImgs.filter(img => {
                    const src = (img.src || '').toLowerCase();
                    const alt = (img.alt || '').toLowerCase();
                    const cls = (img.className || '').toLowerCase();

                    // 排除无效图片
                    if (!src || src.startsWith('data:') || src.includes('svg')) return false;

                    // 排除广告关键词
                    for (const kw of excludeKeywords) {
                        if (src.includes(kw) || alt.includes(kw) || cls.includes(kw)) return false;
                    }

                    // 必须有合理尺寸
                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    if (w < 200 || h < 100) return false;

                    // 宽高比要合理（不是太方或太窄）
                    const ratio = w / h;
                    if (ratio < 0.5 || ratio > 4) return false;

                    return true;
                });

                // 按面积排序，选最大的
                validImgs.sort((a, b) => {
                    const aArea = (a.naturalWidth||a.width) * (a.naturalHeight||a.height);
                    const bArea = (b.naturalWidth||b.width) * (b.naturalHeight||b.height);
                    return bArea - aArea;
                });

                const img = validImgs[0];
                if (!img) return {title: title.textContent.trim(), imgSrc: null};

                return {
                    title: title.textContent.trim(),
                    imgSrc: img.src,
                    imgW: img.naturalWidth || img.width,
                    imgH: img.naturalHeight || img.height
                };
            }""", EXCLUDE_KEYWORDS)

            if not result:
                return None

            # 重建页面只显示标题+主图
            title_text = result.get("title", "")
            img_src = result.get("imgSrc", "")

            if title_text and img_src:
                await page.evaluate(f"""() => {{
                    document.body.innerHTML = `<div style="background:#fff;padding:24px;max-width:800px;margin:0 auto;font-family:'PingFang SC',sans-serif;">
                        <h1 style="font-size:22px;font-weight:800;color:#111;margin-bottom:16px;border-bottom:3px solid #e30000;padding-bottom:12px;">{title_text}</h1>
                        <img src="{img_src}" style="width:100%;border-radius:8px;display:block;" /></div>`;
                    document.body.style.cssText='margin:0;padding:0;background:#fff;';
                }}""")
                await page.wait_for_timeout(2000)
            elif title_text:
                await page.evaluate(f"""() => {{
                    document.body.innerHTML = `<div style="background:#fff;padding:24px;max-width:800px;margin:0 auto;font-family:'PingFang SC',sans-serif;">
                        <h1 style="font-size:22px;font-weight:800;color:#111;margin-bottom:16px;border-bottom:3px solid #e30000;padding-bottom:12px;">{title_text}</h1>
                        <p style="color:#666;font-size:16px;">（暂无主图）</p></div>`;
                    document.body.style.cssText='margin:0;padding:0;background:#fff;';
                }}""")
                await page.wait_for_timeout(1000)

            return await page.screenshot(full_page=False, type="png")

        except Exception as e:
            print(f"文章截图失败: {e}")
            return None
        finally:
            await browser.close()

def select_topics(news_results):
    """Claude从真实新闻列表选6个爆款话题"""
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
        article_url = t.get("url", "")
        send(cid, "📸 正在截取新闻配图，请稍等...")
        def run():
            try:
                if article_url and article_url.startswith("http"):
                    print(f"截图URL: {article_url}")
                    img = asyncio.run(screenshot_article(article_url))
                    if img:
                        s["screenshots"][idx] = img
                        r = send_photo_bytes(cid, img, f"🖼️ 配图预览（{t['source']}）")
                        if r.get("ok"):
                            send(cid, "满意就发布 👇", BTN_PUBLISH)
                            return
                send(cid, "⚠️ 未能截到配图，直接发布文案？", BTN_PUBLISH)
            except Exception as e:
                print(f"截图错误: {e}")
                send(cid, "⚠️ 截图失败，直接发布文案？", BTN_PUBLISH)
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
