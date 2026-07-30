# -*- coding: utf-8 -*-
"""
어제의 박스오피스 대시보드
--------------------------------------------------------
- KOBIS(영화관입장권통합전산망) 오픈API를 사용한다.
- 일별 박스오피스 TOP 10 + 순위 변동 + 관객수 막대그래프
- 주간 박스오피스 막대그래프
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ----------------------------------------------------------------------------
# 0. 기본 설정
# ----------------------------------------------------------------------------
st.set_page_config(page_title="박스오피스 대시보드", page_icon="🎬", layout="wide")

KOBIS_KEY = st.secrets["KOBIS_KEY"]
DAILY_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
WEEKLY_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"

DAILY_COLORS = ["#fdece9", "#f8b7a8", "#f0836a", "#e04f37", "#b8281a"]   # 옅은 빨강 -> 진한 빨강 (일별)
WEEKLY_COLORS = ["#e9f1fb", "#b9d6f2", "#7fb2e6", "#3d7fc9", "#1c4e8a"]  # 옅은 파랑 -> 진한 파랑 (주간)


# ----------------------------------------------------------------------------
# 1. 화면 스타일 (커스텀 CSS) — 배경 그라데이션, 유리질 카드, 한글 친화 폰트
# ----------------------------------------------------------------------------
def inject_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/[email protected]/dist/web/static/pretendard.css');

        html, body, [class*="css"] {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Malgun Gothic', sans-serif;
        }

        /* 페이지 전체 배경 그라데이션 (시네마 느낌의 붉은 톤) */
        .stApp {
            background:
                radial-gradient(circle at 10% 8%, rgba(224,79,55,0.10) 0%, rgba(224,79,55,0) 40%),
                radial-gradient(circle at 90% 88%, rgba(61,127,201,0.10) 0%, rgba(61,127,201,0) 45%),
                linear-gradient(180deg, #f8f6f6 0%, #f1eef1 100%);
            background-attachment: fixed;
        }

        .main .block-container {
            padding-top: 1.6rem;
            padding-bottom: 3rem;
            max-width: 1180px;
        }

        /* 히어로 배너 */
        .hero {
            background: linear-gradient(135deg, #C81E4B 0%, #E04F37 50%, #F4A261 100%);
            border-radius: 24px;
            padding: 26px 30px;
            display: flex;
            align-items: center;
            gap: 18px;
            box-shadow: 0 14px 32px rgba(200, 30, 75, 0.25);
            margin-bottom: 1.5rem;
            color: #ffffff;
        }
        .hero-icon {
            font-size: 2.2rem;
            background: rgba(255,255,255,0.18);
            width: 62px; height: 62px;
            border-radius: 18px;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0;
        }
        .hero-title {
            font-size: 1.8rem;
            font-weight: 800;
            letter-spacing: -0.5px;
        }
        .hero-sub {
            font-size: 0.95rem;
            opacity: 0.92;
            margin-top: 4px;
        }

        /* 테두리가 있는 컨테이너(st.container(border=True))를 유리질 카드처럼 */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255,255,255,0.72);
            backdrop-filter: blur(14px);
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.6);
            box-shadow: 0 10px 28px rgba(30, 27, 75, 0.07);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            border-radius: 20px;
        }

        /* 섹션 소제목 - 알약 모양 배지 */
        .section-title {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 1.0rem;
            font-weight: 700;
            color: #1e293b;
            background: rgba(255,255,255,0.75);
            padding: 8px 18px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.7);
            box-shadow: 0 4px 14px rgba(30, 27, 75, 0.05);
            margin: 0.4rem 0 1rem 0;
        }

        /* KPI 카드 */
        .kpi-card {
            background: rgba(255,255,255,0.72);
            backdrop-filter: blur(14px);
            border-radius: 20px;
            padding: 18px 20px 16px 20px;
            border: 1px solid rgba(255,255,255,0.6);
            box-shadow: 0 10px 26px rgba(30, 27, 75, 0.07);
            border-top: 5px solid var(--accent, #C81E4B);
            height: 100%;
        }
        .kpi-top {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }
        .kpi-icon {
            width: 36px; height: 36px;
            border-radius: 50%;
            background: var(--accent-soft, rgba(200,30,75,0.15));
            display: flex; align-items: center; justify-content: center;
            font-size: 1.05rem;
            flex-shrink: 0;
        }
        .kpi-label {
            font-size: 0.8rem;
            font-weight: 700;
            color: #6b7280;
        }
        .kpi-value {
            font-size: 1.45rem;
            font-weight: 800;
            color: #111827;
            line-height: 1.3;
            word-break: keep-all;
        }
        .kpi-sub {
            font-size: 0.83rem;
            color: #9ca3af;
            margin-top: 3px;
        }

        /* 위젯 라벨 */
        label {
            font-weight: 700 !important;
            color: #374151 !important;
            font-size: 0.86rem !important;
        }

        /* 알림 박스 */
        div[data-testid="stAlert"] {
            border-radius: 16px;
        }

        /* 데이터프레임 모서리 둥글게 */
        div[data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
        }

        /* 하단 푸터 캡션 */
        .footer-note {
            text-align: center;
            color: #9ca3af;
            font-size: 0.8rem;
            margin-top: 2.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """헥스 색상을 반투명 rgba 문자열로 바꾼다 (아이콘 배경 등에 사용)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def kpi_card(label: str, value: str, sub: str, accent: str, icon: str) -> str:
    """지표 카드 하나를 HTML로 만든다."""
    soft = hex_to_rgba(accent, 0.16)
    return f"""
    <div class="kpi-card" style="--accent: {accent}; --accent-soft: {soft};">
        <div class="kpi-top">
            <div class="kpi-icon">{icon}</div>
            <div class="kpi-label">{label}</div>
        </div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>
    """


# ----------------------------------------------------------------------------
# 2. KOBIS 데이터 불러오기
# ----------------------------------------------------------------------------
@st.cache_data(ttl=60 * 60, show_spinner="일별 박스오피스를 불러오는 중입니다...")
def fetch_daily_box_office(target_dt: str):
    """일별 박스오피스를 가져온다. 실패하면 (None, 에러메시지)를 돌려준다."""
    try:
        res = requests.get(DAILY_URL, params={"key": KOBIS_KEY, "targetDt": target_dt}, timeout=10)
    except requests.exceptions.RequestException as e:
        return None, f"요청 중 오류가 발생했습니다: {e}"

    if res.status_code != 200:
        return None, f"요청이 실패했습니다 (상태코드: {res.status_code})"

    data = res.json()
    # KOBIS는 키가 틀려도 상태코드 200을 준다. 대신 faultInfo 상자가 온다.
    if "faultInfo" in data:
        return None, "인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요."

    box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
    if not box_list:
        return None, "그날 자료가 없습니다. 날짜를 하루 더 앞으로 옮겨 보세요."

    return box_list, None


@st.cache_data(ttl=60 * 60, show_spinner="주간 박스오피스를 불러오는 중입니다...")
def fetch_weekly_box_office(target_dt: str, week_gb: str = "0"):
    """주간 박스오피스를 가져온다. 실패하면 (None, 에러메시지)를 돌려준다."""
    try:
        res = requests.get(
            WEEKLY_URL,
            params={"key": KOBIS_KEY, "targetDt": target_dt, "weekGb": week_gb},
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        return None, f"요청 중 오류가 발생했습니다: {e}"

    if res.status_code != 200:
        return None, f"요청이 실패했습니다 (상태코드: {res.status_code})"

    data = res.json()
    if "faultInfo" in data:
        return None, "인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요."

    week_list = data.get("boxOfficeResult", {}).get("weeklyBoxOfficeList", [])
    if not week_list:
        return None, "그 주의 자료가 아직 없습니다."

    return week_list, None


def format_rank_change(row) -> str:
    """
    순위 변동을 화살표 문자열로 바꾼다.
    KOBIS의 rankInten은 '이전 순위 - 이번 순위' 값이라, 양수면 순위가 올라간 것이다.
    """
    if row.get("rankOldAndNew") == "NEW":
        return "🆕 신규"
    inten = int(row.get("rankInten", 0))
    if inten > 0:
        return f"🔺{inten}"
    if inten < 0:
        return f"🔻{abs(inten)}"
    return "− 0"


# ----------------------------------------------------------------------------
# 3. 화면 그리기 시작
# ----------------------------------------------------------------------------
inject_style()

# 한국 시간 기준 어제 날짜를 여덟 자리로 (배포 서버 시계는 외국 기준일 수 있다)
now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
yesterday = now_kst - timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")

st.markdown(
    f"""
    <div class="hero">
        <div class="hero-icon">🎬</div>
        <div>
            <div class="hero-title">어제의 박스오피스</div>
            <div class="hero-sub">조회 기준일(어제): {yesterday.strftime('%Y-%m-%d')} · KOBIS 영화관입장권통합전산망 기준</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

box_list, err = fetch_daily_box_office(target_dt)
if err:
    st.error(err)
    st.stop()

df = pd.DataFrame(box_list)

# 글자로 온 숫자들을 진짜 숫자로 바꾸기
numeric_cols = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt", "rankInten"]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

df["순위변동"] = df.apply(format_rank_change, axis=1)

# ----------------------------------------------------------------------------
# 4. 지표 카드 3장
# ----------------------------------------------------------------------------
top = df.sort_values("rank").iloc[0]

card1, card2, card3 = st.columns(3)
with card1:
    st.markdown(
        kpi_card("어제 1위", top["movieNm"], "일별 박스오피스 기준", "#D4A017", "🏆"),
        unsafe_allow_html=True,
    )
with card2:
    st.markdown(
        kpi_card("어제 관객수", f"{int(top['audiCnt']):,}명", top["movieNm"], "#3D7FC9", "🎟️"),
        unsafe_allow_html=True,
    )
with card3:
    st.markdown(
        kpi_card("누적 관객", f"{int(top['audiAcc']):,}명", top["movieNm"], "#6C5CE7", "📈"),
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------------
# 5. 일별 박스오피스 표 (순위 변동 포함)
# ----------------------------------------------------------------------------
st.markdown('<div class="section-title">📋 박스오피스 TOP 10</div>', unsafe_allow_html=True)

table = df[["rank", "movieNm", "순위변동", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
table.columns = ["순위", "영화명", "순위변동", "개봉일", "관객수", "누적관객", "스크린수"]
table = table.sort_values("순위").reset_index(drop=True)

with st.container(border=True):
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "관객수": st.column_config.ProgressColumn(
                "관객수", format="%d명", min_value=0, max_value=float(table["관객수"].max())
            ),
        },
    )

# ----------------------------------------------------------------------------
# 6. 일별 관객수 막대그래프 (가로 막대 - 영화 제목이 세로로 찌그러지는 문제 해결)
# ----------------------------------------------------------------------------
st.markdown('<div class="section-title">📈 어제 관객수 상위 10편</div>', unsafe_allow_html=True)

top10 = table.sort_values("관객수", ascending=True).tail(10)  # 가로 막대는 아래->위 순서라 오름차순 정렬

fig_daily = px.bar(
    top10,
    x="관객수",
    y="영화명",
    orientation="h",
    text="관객수",
    color="관객수",
    color_continuous_scale=DAILY_COLORS,
)
fig_daily.update_traces(
    texttemplate="%{text:,}명",
    textposition="outside",
    marker_line_color="rgba(0,0,0,0.05)",
    marker_line_width=1,
)
fig_daily.update_layout(
    height=460,
    margin={"l": 10, "r": 40, "t": 10, "b": 10},
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Pretendard, sans-serif", color="#374151"),
    coloraxis_showscale=False,
    xaxis=dict(showgrid=True, gridcolor="#eef0f4", title=None),
    yaxis=dict(title=None, tickfont=dict(size=13)),
)

with st.container(border=True):
    st.plotly_chart(fig_daily, use_container_width=True, config={"displaylogo": False})

# ----------------------------------------------------------------------------
# 7. 주간 박스오피스 막대그래프
# ----------------------------------------------------------------------------
# 이번 주는 아직 집계가 끝나지 않았을 수 있으므로, 완전히 끝난 지난주(월~일) 기준으로 조회한다.
today_kst = now_kst.date()
this_monday = today_kst - timedelta(days=today_kst.weekday())
last_full_monday = this_monday - timedelta(days=7)
last_full_sunday = last_full_monday + timedelta(days=6)
weekly_target_dt = last_full_monday.strftime("%Y%m%d")

st.markdown('<div class="section-title">🗓️ 주간 박스오피스</div>', unsafe_allow_html=True)
st.caption(
    f"집계 기간: {last_full_monday.strftime('%Y-%m-%d')} ~ {last_full_sunday.strftime('%Y-%m-%d')} (월~일, 지난 완결 주간 기준)"
)

week_list, week_err = fetch_weekly_box_office(weekly_target_dt, week_gb="0")

if week_err:
    st.info(f"ℹ️ {week_err}")
else:
    wdf = pd.DataFrame(week_list)
    week_numeric_cols = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt", "rankInten"]
    for col in week_numeric_cols:
        if col in wdf.columns:
            wdf[col] = pd.to_numeric(wdf[col], errors="coerce").fillna(0)
    if "rankOldAndNew" in wdf.columns:
        wdf["순위변동"] = wdf.apply(format_rank_change, axis=1)
    else:
        wdf["순위변동"] = "-"

    wtable = wdf[["rank", "movieNm", "순위변동", "audiCnt", "audiAcc", "scrnCnt"]].copy()
    wtable.columns = ["순위", "영화명", "순위변동", "주간관객수", "누적관객", "스크린수"]
    wtable = wtable.sort_values("순위").reset_index(drop=True)

    week_col1, week_col2 = st.columns([1, 1.3])

    with week_col1:
        with st.container(border=True):
            st.markdown("**📋 주간 TOP 10 표**")
            st.dataframe(
                wtable,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "주간관객수": st.column_config.ProgressColumn(
                        "주간관객수", format="%d명", min_value=0, max_value=float(wtable["주간관객수"].max())
                    ),
                },
            )

    with week_col2:
        wtop10 = wtable.sort_values("주간관객수", ascending=True).tail(10)
        fig_weekly = px.bar(
            wtop10,
            x="주간관객수",
            y="영화명",
            orientation="h",
            text="주간관객수",
            color="주간관객수",
            color_continuous_scale=WEEKLY_COLORS,
        )
        fig_weekly.update_traces(
            texttemplate="%{text:,}명",
            textposition="outside",
            marker_line_color="rgba(0,0,0,0.05)",
            marker_line_width=1,
        )
        fig_weekly.update_layout(
            height=440,
            margin={"l": 10, "r": 40, "t": 10, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Pretendard, sans-serif", color="#374151"),
            coloraxis_showscale=False,
            xaxis=dict(showgrid=True, gridcolor="#eef0f4", title=None),
            yaxis=dict(title=None, tickfont=dict(size=13)),
        )
        with st.container(border=True):
            st.markdown("**📊 주간 관객수 그래프**")
            st.plotly_chart(fig_weekly, use_container_width=True, config={"displaylogo": False})

st.markdown(
    '<div class="footer-note">데이터 출처: KOBIS 영화관입장권통합전산망 오픈API</div>',
    unsafe_allow_html=True,
)
