import streamlit as st
import pandas as pd

# --- 設定頁面 ---
st.set_page_config(page_title="星展傳說對決回饋計算機", page_icon="💳", layout="wide")

st.title("💳 星展傳說對決聯名卡 (2025版) 帳單回饋試算")
st.markdown("""
此工具依據 **2025/12/31 前申辦** 且 **已設定自動扣繳** 之權益進行試算：
- **指定通路 (生活玩家)**：10% (上限 1000 點)
- **一般消費**：1.2% (無上限)
- **國外消費**：2.5% (無上限)
""")

# --- 參數設定 ---
RATE_DOMESTIC = 0.012  # 1.2%
RATE_FOREIGN = 0.025   # 2.5%
RATE_SPECIAL = 0.10    # 10% (含原始回饋)
CAP_SPECIAL = 1000     # 加碼回饋上限 (點數)

# 關鍵字清單 (依據權益手冊與客服確認)
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
    is_foreign_default = st.checkbox("預設所有交易為國外消費?", value=False, help="若您的帳單大多是海外交易請勾選")

# --- 核心計算邏輯 ---
def calculate_points(df, col_name, col_amt):
    results = []
    accumulated_special_points = 0 # 累計「加碼」獲得的點數 (監控 1000 點上限)
    
    for index, row in df.iterrows():
        name = str(row[col_name])
        try:
            amt = float(str(row[col_amt]).replace(",", "").replace("$", ""))
        except:
            amt = 0
            
        if amt <= 0: continue # 忽略負項或0元

        # 1. 判斷排除
        is_excluded = any(k in name for k in EXCLUDE_KEYWORDS)
        
        # 2. 判斷指定通路
        is_special = any(k.lower() in name.lower() for k in SPECIAL_KEYWORDS)
        
        # 3. 判斷國外 (這裡簡化，若關鍵字沒寫，需手動或依賴設定)
        is_foreign = is_foreign_default 
        
        rate = 0
        points = 0
        note = ""

        if is_excluded:
            rate = 0
            note = "🚫 排除項目"
        elif is_special:
            # 判斷基礎回饋率 (假設指定通路多為國內，若為國外需視情況)
            base_rate = RATE_FOREIGN if is_foreign else RATE_DOMESTIC
            
            # 傳說對決卡加碼邏輯：總共給 10%。
            # 加碼部分 = 10% - 基礎率
            extra_rate = RATE_SPECIAL - base_rate
            extra_points_potential = amt * extra_rate
            
            # 檢查上限
            if accumulated_special_points + extra_points_potential <= CAP_SPECIAL:
                rate = RATE_SPECIAL
                points = round(amt * rate)
                accumulated_special_points += extra_points_potential
                note = "🔥 指定 10%"
            else:
                # 爆表了
                remaining_cap = max(0, CAP_SPECIAL - accumulated_special_points)
                if remaining_cap > 0:
                    # 部分吃到加碼
                    base_points = round(amt * base_rate)
                    points = base_points + remaining_cap
                    accumulated_special_points += extra_points_potential # 紀錄已爆
                    rate = points / amt # 換算實際回饋率
                    note = "⚠️ 達上限 (部分加碼)"
                else:
                    # 全爆，回歸一般
                    rate = base_rate
                    points = round(amt * rate)
                    note = "一般消費 (上限已滿)"
        else:
            # 一般消費
            rate = RATE_FOREIGN if is_foreign else RATE_DOMESTIC
            points = round(amt * rate)
            note = "一般消費"
            
        results.append({
            "消費項目": name,
            "金額": int(amt),
            "回饋率": f"{rate*100:.1f}%",
            "預估點數": int(points),
            "說明": note
        })
        
    return pd.DataFrame(results), accumulated_special_points

# --- 主畫面：上傳與顯示 ---
uploaded_file = st.file_uploader("📂 上傳帳單 (支援 CSV 或 Excel)", type=["csv", "xlsx", "xls"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        st.write("### 1️⃣ 請確認對應欄位")
        cols = df.columns.tolist()
        col1, col2 = st.columns(2)
        target_name = col1.selectbox("請選擇「商店名稱/摘要」的欄位", cols, index=cols.index("摘要") if "摘要" in cols else 0)
        target_amt = col2.selectbox("請選擇「金額/台幣金額」的欄位", cols, index=cols.index("金額") if "金額" in cols else 1)
        
        if st.button("🚀 開始計算"):
            result_df, used_cap = calculate_points(df, target_name, target_amt)
            
            st.divider()
            # 儀表板
            total_spend = result_df['金額'].sum()
            total_points = result_df['預估點數'].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("總消費", f"${total_spend:,.0f}")
            m2.metric("預估總點數", f"{total_points:,.0f} 點")
            m3.metric("加碼額度使用 (上限1000)", f"{int(used_cap)} / {CAP_SPECIAL}")
            
            if used_cap >= CAP_SPECIAL:
                st.error("🚨 本月加碼額度已用完，後續指定消費將降為一般回饋！")
            else:
                st.success(f"✅ 還可以刷約 ${int((CAP_SPECIAL - used_cap) / 0.088):,.0f} 元的指定通路消費")

            st.dataframe(result_df, use_container_width=True)
            
    except Exception as e:
        st.error(f"讀取檔案失敗，請確認格式。錯誤：{e}")

else:
    st.info("💡 提示：您可以從星展網銀下載 CSV/Excel 帳單，直接上傳即可。")
    st.markdown("---")
    st.caption("隱私聲明：此工具僅在您的瀏覽器端運行運算逻辑，不會儲存您的帳單資料。")
