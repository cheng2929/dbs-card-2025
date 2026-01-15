import streamlit as st
import pandas as pd
import pdfplumber
import re

# --- 設定頁面 ---
st.set_page_config(page_title="星展傳說對決回饋計算機 (PDF版)", page_icon="💳", layout="wide")

st.title("💳 星展傳說對決聯名卡 (2025版) 回饋試算")
st.markdown("""
支援 **PDF 帳單 (含密碼)** 與 **CSV/Excel** 匯入。
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

# --- 核心邏輯：解析 PDF ---
def parse_pdf_dbs(file, password):
    transactions = []
    try:
        with pdfplumber.open(file, password=password) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            lines = full_text.split('\n')
            for line in lines:
                # 1. 基礎關鍵字排除 (排除表頭、頁尾)
                if any(x in line for x in ["本期應繳", "信用額度", "DBS", "繳款截止日", "帳單結帳日", "循環信用", "預借現金額度"]):
                    continue

                # 2. 進階排除：如果一行出現兩個以上的日期 (通常是摘要列：結帳日+截止日)
                dates_in_line = re.findall(r'\d{4}/\d{2}/\d{2}', line)
                if len(dates_in_line) > 1:
                    continue

                # 抓取規則：日期 + 說明 + 金額
                match = re.search(r'(\d{4}/\d{2}/\d{2})\s+(.+?)\s+([0-9,]+)(?:\s|$)', line)
                
                if match:
                    date_str = match.group(1)
                    desc_str = match.group(2).strip()
                    amt_str = match.group(3)
                    
                    # 3. 防呆排除：如果抓到的「商店名稱」其實是日期 (例如抓錯位)
                    if re.match(r'\d{4}/\d{2}/\d{2}', desc_str):
                        continue

                    try:
                        amt = float(amt_str.replace(",", ""))
                        transactions.append({
                            "交易日期": date_str,
                            "商店名稱": desc_str,
                            "金額": amt
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

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 設定")
    is_foreign_default = st.checkbox("預設全為國外消費", False)
    st.info("💡 密碼提示：身分證後4碼 + 生日後4碼")

# --- 主畫面 ---
file_type = st.radio("選擇上傳檔案類型", ["PDF 帳單", "CSV / Excel"], horizontal=True)
uploaded_file = st.file_uploader("上傳檔案", type=["pdf", "csv", "xlsx"])

df = None

if uploaded_file:
    if file_type == "PDF 帳單":
        password = st.text_input("🔒 請輸入 PDF 密碼 (身分證後4碼 + 生日後4碼)", type="password")
        
        if password:
            with st.spinner("正在破解 PDF 封印並讀取資料..."):
                result = parse_pdf_dbs(uploaded_file, password)
                if isinstance(result, str): 
                    st.error(f"讀取失敗：{result}")
                    st.warning("請確認密碼正確，或改用 CSV 上傳。")
                elif result.empty:
                    st.warning("⚠️ 讀取成功但找不到交易紀錄。可能是 PDF 排版無法識別，建議使用 CSV。")
                else:
                    df = result
                    st.success(f"成功讀取 {len(df)} 筆交易！")
                    col_name, col_amt = "商店名稱", "金額"
        else:
            st.info("請輸入密碼以解鎖 PDF")

    else: # CSV/Excel
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            st.write("預覽資料 (前5筆):", df.head())
            cols = df.columns.tolist()
            c1, c2 = st.columns(2)
            col_name = c1.selectbox("商店名稱欄位", cols, index=0)
            col_amt = c2.selectbox("金額欄位", cols, index=1 if len(cols)>1 else 0)
        except Exception as e:
            st.error(f"檔案格式錯誤: {e}")

    # --- 顯示計算結果 ---
    if df is not None:
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
