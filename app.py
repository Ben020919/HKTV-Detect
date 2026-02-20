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

    page.goto(base_url + "CONFIRMED") 
    page.wait_for_timeout(2500) 
    page.locator('button:has-text("商戶8小時送貨")').click(force=True)
    page.wait_for_timeout(1000) 

    for status_val, status_name in statuses:
        page.locator('div.ant-select-selector:has-text("運單狀態")').click(force=True)
        page.wait_for_timeout(400) 
        page.locator('button[data-testid="清除全部"]').click(force=True)
        page.wait_for_timeout(300) 
        
        checkbox = page.locator(f'input[value="{status_val}"]')
        try:
            if not checkbox.is_checked(): checkbox.click(force=True)
        except Exception:
            checkbox.check(force=True)
            
        page.wait_for_timeout(200)
        page.locator('button[data-testid="套用"]').click(force=True)
        page.wait_for_timeout(1500) 
        
        try:
            result_text = page.locator('span:has-text("結果")').last.inner_text(timeout=3000)
            date_data[status_val] = extract_total_count(result_text)
        except Exception:
            date_data[status_val] = "0"
            
    return date_data

def scrape_hktvmall(username, password):
    now = datetime.now()
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
        context = browser.new_context()
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,svg}", lambda route: route.abort())

        print(f"\n🤖 [爬蟲] 登入 HKTVmall (時間: {now.strftime('%H:%M:%S')})")
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
            
        # 👉 修改 1：改成 180 秒（3分鐘）執行一次爬蟲
        print("⏳ 休息 3 分鐘後進行下一輪抓取...\n")
        time.sleep(180) 

# ==========================================
# 2. Streamlit 介面與背景執行緒管理
# ==========================================

# 確保背景爬蟲只啟動一次
@st.cache_resource
def start_background_scraper():
    print("啟動背景爬蟲執行緒...")
    thread = threading.Thread(target=run_scraper_loop, daemon=True)
    thread.start()
    return thread

# 啟動爬蟲
start_background_scraper()

# 頁面設定
st.set_page_config(page_title="HKTVmall 訂單監控", layout="wide")
st.title("HKTVmall 訂單監控面板")

# 讀取資料
file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'order_data.json')
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    data = {}
    st.warning("🔄 正在等待爬蟲抓取第一筆資料，這可能需要幾分鐘，請稍候...")

# 顯示最後更新時間與狀態
last_updated = data.get("last_updated", "--")
status_msg = data.get("status_msg", "初始化中...")

st.caption(f"🕒 系統最後更新時間：{last_updated}")
if "休息" in status_msg:
    st.warning(status_msg)
else:
    st.success(status_msg)

st.markdown("---")

# 渲染今日訂單
if "today" in data and data["today"]:
    st.subheader(f"📦 今日訂單 ({data['today'].get('date', '--')})")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("已建立 (CONFIRMED)", data['today'].get('CONFIRMED', '--'))
    with col2: st.metric("已確認 (ACKNOWLEDGED)", data['today'].get('ACKNOWLEDGED', '--'))
    with col3: st.metric("已包裝 (PACKED)", data['today'].get('PACKED', '--'))
    with col4: st.metric("已出貨 (PICKED)", data['today'].get('PICKED', '--'))

st.markdown("<br>", unsafe_allow_html=True)

# 渲染明日訂單
if "tomorrow" in data and data["tomorrow"]:
    st.subheader(f"🚚 明日訂單 ({data['tomorrow'].get('date', '--')})")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("已建立 (CONFIRMED)", data['tomorrow'].get('CONFIRMED', '--'))
    with col2: st.metric("已確認 (ACKNOWLEDGED)", data['tomorrow'].get('ACKNOWLEDGED', '--'))
    with col3: st.metric("已包裝 (PACKED)", data['tomorrow'].get('PACKED', '--'))
    with col4: st.metric("已出貨 (PICKED)", data['tomorrow'].get('PICKED', '--'))

# 👉 修改 2：改成 10 秒更新一次畫面
time.sleep(10)
st.rerun()
