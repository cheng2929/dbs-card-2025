import streamlit as st
import pandas as pd
import pdfplumber
import re

# --- 設定頁面 ---
st.set_page_config(page_title="星展傳說對決回饋計算機 (多卡版)", page_icon="💳", layout="wide")

st.title("💳 星展傳說對決聯名卡 (2025版) 回饋試算")
st.markdown("""
支援 **多卡過濾**、**PDF 帳單** 與 **CSV/Excel** 匯入。
- **指定通路**：10% (上限 1000 點)
- **一般消費**：1.2% (無上限)
""")

# --- 參數設定 ---
RATE_DOMESTIC = 0.012
RATE_FOREIGN = 0.025
RATE_SPECIAL = 0.10
CAP_SPECIAL = 1000

SPECIAL_KEYWORDS = [
    "App Store", "Google Play", "Garena", "Steam", "Nintendo", "PlayStation", 
    "MyCard", "Blizzard", "Xbox", "Ubisoft", 
    "YouTube", "Netflix", "Disney", "Spotify", "KKBOX", "Apple TV", "Twitch",
    "Uber", "Foodpanda", "麥當勞", "肯德基", "摩斯", "必勝客", "拿坡里",
    "LINE Pay", "連加", "蝦皮"
]

EXCLUDE_KEYWORDS = [
    "年費", "循環息", "預借現金", "滯納金", "手續費", "掛失",
    "繳稅", "燃料費", "中華電信", "台電", "自來水", "全聯", "悠遊卡", "一卡通"
]

# --- 側邊欄：設定 ---
with st.sidebar:
    st.header("⚙️ 設定")
    # 新增：卡號過濾功能
    target_card_last4 = st.text_input("💳 指定卡號末四碼 (若有多張卡請填寫)", max_chars=4, help="只計算這張卡的消費，留空則計算全部")
    st.divider()
    is_foreign_default = st.checkbox("預設全為國外消費", False)
    st.info("💡 密碼提示：身分證後4碼 + 生日後4碼")

# --- 核心邏輯：解析 PDF (含卡號分流) ---
def parse_pdf_dbs(file, password, target_last4):
    transactions = []
    current_card_section = None # 追蹤目前讀取到的卡號區段
    
    try:
        with pdfplumber.open(file, password=password) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            lines = full_text.split('\n')
            for line in lines:
                # 0. 偵測卡號區段 (如果帳單有分卡列示)
                # 尋找類似 "卡號：xxxx-xxxx-xxxx-1234" 或 "**** **** **** 1234"
                card_header_match = re.search(r'(?:卡號|Card No|正卡|附卡).*?(\d{4})$', line.strip())
                if not card_header_match:
                     # 嘗試找單純的卡號格式 **** **** **** 1234
                     card_header_match = re.search(r'(?:\d{4}|\*{4}).{1,3}(?:\d{4}|\*{4}).{1,3}(?:\d{4}|\*{4}).{1,3}(\d{4})', line)
                
                if card_header_match:
                    current_card_section = card_header_match.group(1)
                    # print(f"切換至卡號區段: {current_card_section}") # Debug用

                # 1. 基礎排除
                if any(x in line for x in ["本期應繳", "信用額度", "DBS", "繳款截止日", "帳單結帳日", "循環信用", "預借現金額度"]):
                    continue
                if len(re.findall(r'\d{4}/\d{2}/\d{2}', line)) > 1: # 單行多日期排除
                    continue

                # 2. 交易抓取
                match = re.search(r'(\d{4}/\d{2}/\d{2})\s+(.+?)\s+([0-9,]+)(?:\s|$)', line)
                if match:
                    # 如果使用者有指定卡號，且目前已偵測到卡號區段，則進行過濾
                    # 若 PDF 沒偵測到區段(current_card_section is None)，為避免漏抓，預設都收(或建議用CSV)
                    if target_last4 and current_card_section:
                        if current_card_section != target_last4:
                            continue # 跳過這筆，因為不是目標卡片

                    date_str = match.group(1)
                    desc_str = match.group(2).strip()
                    amt_str = match.group(3)
                    
                    if re.match(r'\d{4}/\d{2}/\d{2}', desc_str): continue # 防呆

                    try:
                        amt = float(amt_str.replace(",", ""))
                        transactions.append({
                            "交易日期": date_str,
                            "商店名稱": desc_str,
                            "金額": amt,
                            "歸屬卡號": current_card_section if current_card_section else "未偵測"
                        })
                    except:
                        continue
        return pd.DataFrame(transactions)

    except Exception as e:
        return str(e)

# --- 核心邏輯：計算點數 ---
def calculate_points(df, col_name, col_amt, is_foreign_default):
    results = []
    accumulated_special_points = 0
    
    for index, row in df.iterrows():
        name = str(row[col_name])
        try:
            amt = float(str(row[col_amt]).replace(",", "").replace("$", "").replace("NT", ""))
        except:
            amt = 0
        if amt <= 0: continue

        is_excluded = any(k in name for k in EXCLUDE_KEYWORDS)
        is_special = any(k.lower() in name.lower() for k in SPECIAL_KEYWORDS)
        is_foreign = is_foreign_default 
        
        rate = 0
        points = 0
        note = ""

        if is_excluded:
            rate = 0
            note = "🚫 排除"
        elif is_special:
            base_rate = RATE_FOREIGN if is_foreign else RATE_DOMESTIC
            extra_rate = RATE_SPECIAL - base_rate
            extra_points_potential = amt * extra_rate
            
            if accumulated_special_points + extra_points_potential <= CAP_SPECIAL:
                rate = RATE_SPECIAL
                points = round(amt * rate)
                accumulated_special_points += extra_points_potential
                note = "🔥 指定 10%"
            else:
                remaining_cap = max(0, CAP_SPECIAL - accumulated_special_points)
                if remaining_cap > 0:
                    base_points = round(amt * base_rate)
                    points = base_points + remaining_cap
                    accumulated_special_points += extra_points_potential
                    rate = points / amt 
                    note = "⚠️ 混合計算"
                else:
                    rate = base_rate
                    points = round(amt * rate)
                    note = "上限已滿"
        else:
            rate = RATE_FOREIGN if is_foreign else RATE_DOMESTIC
            points = round(amt * rate)
            note = "一般消費"
            
        results.append({
            "商店名稱": name,
            "金額": int(amt),
            "回饋率": f"{rate*100:.1f}%",
            "預估點數": int(points),
            "說明": note
        })
        
    return pd.DataFrame(results), accumulated_special_points

# --- 主畫面 ---
file_type = st.radio("選擇上傳檔案類型", ["PDF 帳單", "CSV / Excel"], horizontal=True)
uploaded_file = st.file_uploader("上傳檔案", type=["pdf", "csv", "xlsx"])

df = None

if uploaded_file:
    # PDF 模式
    if file_type == "PDF 帳單":
        password = st.text_input("🔒 請輸入 PDF 密碼 (身分證後4碼 + 生日後4碼)", type="password")
        
        if password:
            with st.spinner("正在讀取並過濾卡號..."):
                result = parse_pdf_dbs(uploaded_file, password, target_card_last4)
                if isinstance(result, str): 
                    st.error(f"讀取失敗：{result}")
                elif result.empty:
                    st.warning("找不到交易紀錄。若有指定卡號，請確認末四碼是否正確。")
                else:
                    df = result
                    st.success(f"讀取成功！共 {len(df)} 筆資料")
                    if target_card_last4:
                        st.caption(f"已過濾卡號末四碼：**{target_card_last4}**")
                    col_name, col_amt = "商店名稱", "金額"

    # CSV 模式
    else: 
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.write("### 1️⃣ 欄位對應")
            cols = df.columns.tolist()
            c1, c2, c3 = st.columns(3)
            col_name = c1.selectbox("商店名稱", cols, index=0)
            col_amt = c2.selectbox("金額", cols, index=1 if len(cols)>1 else 0)
            
            # CSV 卡號過濾邏輯
            if target_card_last4:
                col_card = c3.selectbox("卡號欄位 (用於過濾)", ["(不使用)"] + cols)
                if col_card != "(不使用)":
                    before_len = len(df)
                    # 轉字串並過濾
                    df = df[df[col_card].astype(str).str.contains(target_card_last4, na=False)]
                    after_len = len(df)
                    st.info(f"已依據卡號 `{target_card_last4}` 過濾： {before_len} 筆 ➔ {after_len} 筆")
            
        except Exception as e:
            st.error(f"檔案格式錯誤: {e}")

    # --- 計算結果 ---
    if df is not None and not df.empty:
        if st.button("🚀 開始計算回饋"):
            result_df, used_cap = calculate_points(df, col_name, col_amt, is_foreign_default)
            
            st.divider()
            t_spend = result_df['金額'].sum()
            t_points = result_df['預估點數'].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("總消費", f"${t_spend:,.0f}")
            m2.metric("預估點數", f"{t_points:,.0f}")
            m3.metric("加碼額度", f"{int(used_cap)} / 1000")
            
            if used_cap >= 1000:
                st.error("🚨 10% 加碼已達上限！")
            
            st.dataframe(result_df, use_container_width=True)
