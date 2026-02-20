import streamlit as st
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, time as dt_time
import threading
import json
import time
import os
import re
from dotenv import load_dotenv

# ==========================================
# 1. 爬蟲機器人功能區塊
# ==========================================
def extract_total_count(text):
    if not text: return "0"
    numbers = re.findall(r'\d+', text)
    return numbers[-1] if numbers else "0"

def scrape_single_date(page, date_str):
    base_url = (
        f"https://merchant.shoalter.com/zh/order-management/orders/toship"
        f"?bu=HKTV&deliveryType=STANDARD_DELIVERY&productReadyMethod=STANDARD_DELIVERY_ALL"
        f"&searchType=ORDER_ID&storefrontCodes=H0956004%2CH0956006%2CH0956007%2CH0956008%2CH0956010%2CH0956012"
        f"&dateType=PICK_UP_DATE&startDate={date_str}&endDate={date_str}"
        f"&pageSize=20&pageNumber=1&sortColumn=orderDate&waybillStatuses="
    )
    statuses = [("CONFIRMED", "已建立"), ("ACKNOWLEDGED", "已確認"), ("PACKED", "已包裝"), ("PICKED", "已出貨")]
    date_data = {"date": date_str}

    # 1. 進入當天的初始頁面 (顯示總數)
    page.goto(base_url)
    page.wait_for_timeout(5000) # 給網頁充分的時間初始化

    # 2. 點擊「商戶8小時送貨」
    try:
        page.locator('button:has-text("商戶8小時送貨")').click(timeout=3000, force=True)
        page.wait_for_timeout(3000)
    except Exception:
        pass

    # 3. 讓機器人乖乖打開選單，一個一個勾選
    for status_val, status_name in statuses:
        try:
            # 展開「運單狀態」選單
            page.locator('div.ant-select-selector:has-text("運單狀態")').click(force=True)
            page.wait_for_timeout(1500) # 等待選單動畫展開

            # 點擊「清除全部」確保不會疊加
            page.locator('button[data-testid="清除全部"]').click(force=True)
            page.wait_for_timeout(1000)

            # 強制勾選目標狀態
            checkbox = page.locator(f'input[value="{status_val}"]')
            checkbox.click(force=True)
            page.wait_for_timeout(1000)

            # 點擊「套用」
            page.locator('button[data-testid="套用"]').click(force=True)

            # 🛑 核心關鍵：強制等待 6 秒！
            # 讓網頁有足夠的時間從總數 (例如 18) 刷新為實際過濾後的數字！
            page.wait_for_timeout(6000)

            # 抓取刷新後的文字
            result_text = page.locator('span:has-text("結果")').last.inner_text(timeout=5000)
            date_data[status_val] = extract_total_count(result_text)

        except Exception as e:
            print(f"抓取 {status_name} 失敗: {e}")
            date_data[status_val] = "0"
            
    return date_data

def scrape_hktvmall(username, password):
    now = datetime.utcnow() + timedelta(hours=8)
    
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'order_data.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            results_data = json.load(f)
    except Exception:
        results_data = {"today": {}, "tomorrow": {}}

    results_data["status_msg"] = "⚡ 機器人運行中：每 3 分鐘自動抓取最新資料..."

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}) 
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,svg}", lambda route: route.abort()) 

        print(f"\n🤖 [爬蟲] 登入 HKTVmall (香港時間: {now.strftime('%H:%M:%S')})")
        page.goto("https://merchant.shoalter.com/login") 
        page.locator('#account').fill(username)
        page.locator('#password').fill(password)
        page.locator('button[data-testid="繼續"]').click()
        page.wait_for_timeout(5000) 

        print(f"🤖 [爬蟲] 正在抓取 【今日訂單】 ({today_str})...")
        results_data["today"] = scrape_single_date(page, today_str)

        print(f"🤖 [爬蟲] 正在抓取 【明日訂單】 ({tomorrow_str})...")
        results_data["tomorrow"] = scrape_single_date(page, tomorrow_str)

        results_data["last_updated"] = now.strftime("%Y-%m-%d %H:%M:%S")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, ensure_ascii=False, indent=4)
            
        print(f"🎉 [爬蟲] 抓取完成！\n")
        browser.close()

def run_scraper_loop():
    load_dotenv()
    MY_USERNAME = os.getenv("HKTV_USERNAME")
    MY_PASSWORD = os.getenv("HKTV_PASSWORD")
    
    if not MY_USERNAME or not MY_PASSWORD:
        print("❌ [系統嚴重錯誤] 找不到帳號或密碼！")
        return
        
    while True:
        try:
            scrape_hktvmall(MY_USERNAME, MY_PASSWORD)
        except Exception as e:
            print(f"❌ [爬蟲] 發生錯誤: {e}")
            
        print("⏳ 休息 3 分鐘後進行下一輪抓取...\n")
        time.sleep(180) 

# ==========================================
# 2. Streamlit 介面與背景執行緒管理
# ==========================================

@st.cache_resource
def start_background_scraper():
    print("啟動背景爬蟲執行緒...")
    os.system("playwright install chromium")
    thread = threading.Thread(target=run_scraper_loop, daemon=True)
    thread.start()
    return thread

start_background_scraper()

st.set_page_config(page_title="HKTVmall 訂單監控", layout="wide")
st.title("HKTVmall 訂單監控面板")

file_path = os.path.join(os.path.
