"""
社宅招租爬蟲 - 自動排程版
每天 23:59 自動爬取新北市社宅、住都中心、桃園市社宅的最新招租公告
有新公告時發送 Email 通知
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import smtplib
import schedule
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================
# 請在這裡填入你的設定
# ============================================================
EMAIL_SENDER   = "ray970111@gmail.com"
EMAIL_PASSWORD = "lzszfhmxhulyappj"   # 不含空格
EMAIL_RECEIVER = "ray970111@gmail.com"             # 可以跟寄件者相同
EMAIL_CC       = "allen327@gmail.com"      # 副本收件人
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

CACHE_FILE = "social_housing_cache.json"
LOG_FILE   = "crawler_log.txt"


def log(msg):
    """寫入 log 並印出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================
# 各網站爬蟲
# ============================================================

def crawl_new_taipei():
    """新北市住宅及都市更新中心 - 招租快訊（新網址 nthurc.org.tw）"""
    results = []
    try:
        url = "https://www.nthurc.org.tw/leasing-news/residential-area"
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "lxml")

        # 抓含招租關鍵字的連結
        seen = set()
        for a_tag in soup.find_all("a", href=True):
            title = a_tag.text.strip()
            if "招租" in title and len(title) > 5:
                href = a_tag["href"]
                if not href.startswith("http"):
                    href = "https://www.nthurc.org.tw" + href
                if title not in seen:
                    seen.add(title)
                    # 嘗試找同層日期
                    parent = a_tag.find_parent(["li", "div", "article"])
                    date = ""
                    if parent:
                        import re
                        m = re.search(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", parent.get_text())
                        date = m.group(0) if m else ""
                    results.append({
                        "title":  title,
                        "link":   href,
                        "date":   date,
                        "source": "新北市社宅"
                    })
        log(f"  新北市社宅：抓到 {len(results)} 筆")
    except Exception as e:
        log(f"  新北市社宅爬取失敗：{e}")
    return results


def crawl_ura():
    """國家住宅及都市更新中心 - 社會住宅最新訊息（搜尋「招租」關鍵字）"""
    results = []
    try:
        url = "https://www.hurc.org.tw/hurc/docList?uid=292&pid=227&rn=-463365283"
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "lxml")

        import re
        seen = set()
        for a_tag in soup.find_all("a"):
            title = a_tag.text.strip()
            if "招租" not in title or len(title) <= 5:
                continue
            if title in seen:
                continue
            seen.add(title)

            # 該網站連結藏在 onclick 的 javascript:ga(...) 裡，格式：
            # javascript:ga('target', '分類', '標題', 'docDetail?uid=292&pid=227&doc_id=XXXX', '點擊')
            # 需從第4個參數取出真正的路徑
            href = ""
            onclick = a_tag.get("onclick", "") or a_tag.get("href", "")
            m = re.search(r'(docDetail[^()\s]+)', onclick)
            if m:
                href = "https://www.hurc.org.tw/hurc/" + m.group(1)
            else:
                raw_href = a_tag.get("href", "")
                if raw_href and not raw_href.startswith("javascript"):
                    href = raw_href if raw_href.startswith("http") else "https://www.hurc.org.tw" + raw_href

            if not href:
                continue

            parent = a_tag.find_parent(["li", "div", "article", "tr"])
            date = ""
            if parent:
                m2 = re.search(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", parent.get_text())
                date = m2.group(0) if m2 else ""

            results.append({
                "title":  title,
                "link":   href,
                "date":   date,
                "source": "住都中心"
            })

        log(f"  住都中心：抓到 {len(results)} 筆")
    except Exception as e:
        log(f"  住都中心爬取失敗：{e}")
    return results


def crawl_taoyuan():
    """桃園市住宅及都市更新中心 - 招租中社會住宅"""
    results = []
    try:
        # 新網址（原 socialhousing.tycg.gov.tw 已停用）
        url = "https://www.tyhurc.org.tw/w/tshsc/SocialHousing"
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "lxml")

        # 每個社宅是一個 <li> 內含 <a>，連結格式為 /w/tshsc/SocialHousing_XXXX
        for a_tag in soup.select("a[href*='SocialHousing_']"):
            title = a_tag.get("title", "") or a_tag.text.strip()
            title = title.replace("前往 - ", "").strip()
            href  = a_tag.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.tyhurc.org.tw" + href

            # 日期：在同一個 <li> 或 <a> 的文字內，格式類似 "17\n6 2025"
            parent = a_tag.find_parent("li") or a_tag
            raw_text = parent.get_text(separator=" ", strip=True)
            # 嘗試從文字中找日期（格式：月 日 年 或 年/月/日）
            import re
            date_match = re.search(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}\s+\d{4})", raw_text)
            date = date_match.group(0) if date_match else ""

            if title:
                results.append({
                    "title":  title,
                    "link":   href,
                    "date":   date,
                    "source": "桃園市社宅"
                })

        log(f"  桃園市社宅：抓到 {len(results)} 筆")
    except Exception as e:
        log(f"  桃園市社宅爬取失敗：{e}")
    return results


# ============================================================
# 比對新舊資料
# ============================================================

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_new_items(current, previous):
    prev_set = {(item["source"], item["title"]) for item in previous}
    return [item for item in current
            if (item["source"], item["title"]) not in prev_set]


# ============================================================
# Email 通知
# ============================================================

def send_email(new_items):
    try:
        subject = f"📢 社宅新公告通知（共 {len(new_items)} 筆）"

        # 純文字版
        text_body = f"社宅爬蟲偵測到 {len(new_items)} 筆新公告：\n\n"
        for item in new_items:
            text_body += f"【{item['source']}】{item['date']}\n"
            text_body += f"{item['title']}\n"
            text_body += f"{item['link']}\n\n"

        # HTML 版（更好看）
        rows = ""
        for item in new_items:
            rows += f"""
            <tr>
              <td style="padding:8px;border-bottom:1px solid #eee;color:#555;white-space:nowrap">{item['source']}</td>
              <td style="padding:8px;border-bottom:1px solid #eee;color:#555;white-space:nowrap">{item['date']}</td>
              <td style="padding:8px;border-bottom:1px solid #eee">
                <a href="{item['link']}" style="color:#0066cc;text-decoration:none">{item['title']}</a>
              </td>
            </tr>"""

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:auto">
          <h2 style="color:#0066cc">📢 社宅招租新公告</h2>
          <p>偵測到 <strong>{len(new_items)}</strong> 筆新公告，請盡快查看：</p>
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="background:#f0f4ff">
                <th style="padding:8px;text-align:left">來源</th>
                <th style="padding:8px;text-align:left">日期</th>
                <th style="padding:8px;text-align:left">公告名稱</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
          <p style="color:#999;font-size:12px;margin-top:20px">
            此信件由社宅爬蟲自動發送 · {datetime.now().strftime("%Y-%m-%d %H:%M")}
          </p>
        </body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = EMAIL_RECEIVER
        msg["Cc"]      = EMAIL_CC
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            all_recipients = [EMAIL_RECEIVER, EMAIL_CC]
            server.sendmail(EMAIL_SENDER, all_recipients, msg.as_string())

        log(f"  Email 已發送至 {EMAIL_RECEIVER}，副本：{EMAIL_CC}")
    except Exception as e:
        log(f"  Email 發送失敗：{e}")


# ============================================================
# 主流程
# ============================================================

def run_crawl():
    log("=" * 50)
    log("開始爬取社宅招租資訊...")

    current = []
    for fn in [crawl_new_taipei, crawl_ura, crawl_taoyuan]:
        current.extend(fn())

    log(f"合計抓到 {len(current)} 筆資料")

    previous  = load_cache()
    new_items = find_new_items(current, previous)

    if new_items:
        log(f"發現 {len(new_items)} 筆新公告，準備發送通知...")
        send_email(new_items)
    else:
        log("沒有新公告")

    save_cache(current)
    log("本次爬取完成")


# ============================================================
# 排程設定
# ============================================================

if __name__ == "__main__":
    log("社宅爬蟲啟動！每天 23:59 自動執行。")
    log("按 Ctrl+C 可停止程式。")

    # 啟動時先跑一次，確認一切正常
    run_crawl()

    # 設定每天 23:59 執行
    schedule.every().day.at("23:59").do(run_crawl)

    while True:
        schedule.run_pending()
        time.sleep(30)