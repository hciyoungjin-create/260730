# -*- coding: utf-8 -*-
"""
전국 고령화 지도 (시군구별 인구 구조 단계구분도)
--------------------------------------------------------
- 인구 데이터: 읍·면·동 단위 연도별 인구 (2015~2026)
- 경계 데이터: 전국 시군구 255개 GeoJSON
- '코드' 열을 기준으로 인구 데이터(읍면동)와 경계 데이터(시군구)를 연결한다.
- 연도 슬라이더, 지표 선택(고령화율/유소년 비율), 시도 확대 기능 포함
- 지도에서 지역을 클릭/선택하면 지도 왼쪽 위 패널에 정보 표로 정리해서 보여준다.
"""

import re

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ----------------------------------------------------------------------------
# 0. 기본 설정
# ----------------------------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", page_icon="🗺️", layout="wide")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

GRAY = "#d9d9d9"          # 데이터가 없는 지역을 칠할 회색
NO_DATA_LABEL = "데이터 없음"

# 지표별 설정: 어떤 열을 볼지, 색을 몇 단계로 어디서 끊을지, 어떤 색을 쓸지
# * 고령화율 구간(19·23·28·38%)은 연도가 바뀌어도 그대로 고정해서 해마다 비교할 수 있게 한다.
# * 유소년 비율은 값 자체가 훨씬 작기 때문에(대략 3~18%) 같은 구간을 쓰면 지도가 한 색이 되어버린다.
#   그래서 유소년 비율 전용 구간을 새로 잡았다.
METRIC_CONFIG = {
    "고령화율 (65세 이상 비율)": {
        "ratio_col": "고령화율",
        "count_col": "고령인구",
        "short": "고령화율",
        "icon": "👴",
        "bins": [-np.inf, 19, 23, 28, 38, np.inf],
        "labels": ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"],
        # 옅은 색 -> 진한 색 (5단계로 끊어서 칠하고, 연속 그라데이션은 쓰지 않는다)
        "colors": ["#fef0e6", "#fbc59a", "#f5904f", "#e2611f", "#a8380f"],
    },
    "유소년 비율 (0~14세 비율)": {
        "ratio_col": "유소년비율",
        "count_col": "유소년인구",
        "short": "유소년 비율",
        "icon": "🧒",
        "bins": [-np.inf, 6, 8, 10, 12, np.inf],
        "labels": ["6% 미만", "6% ~ 8%", "8% ~ 10%", "10% ~ 12%", "12% 이상"],
        "colors": ["#e9f1fb", "#b9d6f2", "#7fb2e6", "#3d7fc9", "#1c4e8a"],
    },
}

# 시도 드롭다운에 쓸 순서 (관용적인 순서로 나열)
SIDO_ORDER = [
    "전국",
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도",
    "경상남도", "제주특별자치도",
]

# 옛 시도 이름 -> 현재(경계 데이터 기준) 시도 이름
SIDO_RENAME = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
}

ACCENT = "#6C5CE7"      # 전국 카드 · 히어로 배너에 쓰는 포인트 색


def hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """헥스 색상을 반투명 rgba 문자열로 바꾼다 (아이콘 배경 등에 사용)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


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

        /* 페이지 전체 배경 그라데이션 */
        .stApp {
            background:
                radial-gradient(circle at 12% 10%, rgba(108,92,231,0.10) 0%, rgba(108,92,231,0) 40%),
                radial-gradient(circle at 88% 85%, rgba(61,127,201,0.10) 0%, rgba(61,127,201,0) 45%),
                linear-gradient(180deg, #f6f7fc 0%, #eef0f8 100%);
            background-attachment: fixed;
        }

        .main .block-container {
            padding-top: 1.6rem;
            padding-bottom: 3rem;
            max-width: 1180px;
        }

        /* 히어로 배너 */
        .hero {
            background: linear-gradient(135deg, #6C5CE7 0%, #8b6ff2 45%, #b985e6 100%);
            border-radius: 24px;
            padding: 26px 30px;
            display: flex;
            align-items: center;
            gap: 18px;
            box-shadow: 0 14px 32px rgba(108, 92, 231, 0.28);
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

        /* 위젯 라벨 */
        label, .stSlider label, .stSelectbox label {
            font-weight: 700 !important;
            color: #374151 !important;
            font-size: 0.86rem !important;
        }

        /* KPI 카드 */
        .kpi-card {
            background: rgba(255,255,255,0.72);
            backdrop-filter: blur(14px);
            border-radius: 20px;
            padding: 18px 20px 16px 20px;
            border: 1px solid rgba(255,255,255,0.6);
            box-shadow: 0 10px 26px rgba(30, 27, 75, 0.07);
            border-top: 5px solid var(--accent, #6C5CE7);
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
            background: var(--accent-soft, rgba(108,92,231,0.15));
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
            font-size: 1.5rem;
            font-weight: 800;
            color: #111827;
            line-height: 1.3;
        }
        .kpi-sub {
            font-size: 0.83rem;
            color: #9ca3af;
            margin-top: 3px;
        }

        /* 지도 위 커스텀 범례 */
        .legend-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            margin: 4px 0 14px 0;
        }
        .legend-chip {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            color: #374151;
            background: #f7f8fc;
            padding: 5px 12px;
            border-radius: 999px;
            border: 1px solid #eef0f4;
        }
        .legend-dot {
            width: 11px; height: 11px;
            border-radius: 50%;
            display: inline-block;
        }

        /* 지도 왼쪽 위 '선택한 지역' 패널 */
        .selection-panel-title {
            font-size: 0.85rem;
            font-weight: 700;
            color: #374151;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .selection-empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            gap: 6px;
            color: #9ca3af;
            font-size: 0.8rem;
            background: #f7f8fc;
            border: 1px dashed #dcdfe6;
            border-radius: 14px;
            padding: 24px 10px;
            height: 100%;
        }
        .selection-empty .big {
            font-size: 1.6rem;
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


def legend_html(cfg: dict) -> str:
    """지도 위에 보여줄 커스텀 범례를 HTML로 만든다."""
    chips = "".join(
        f'<div class="legend-chip"><span class="legend-dot" style="background:{color}"></span>{label}</div>'
        for label, color in zip(cfg["labels"], cfg["colors"])
    )
    chips += (
        f'<div class="legend-chip"><span class="legend-dot" '
        f'style="background:{GRAY}"></span>{NO_DATA_LABEL}</div>'
    )
    return f'<div class="legend-row">{chips}</div>'


# ----------------------------------------------------------------------------
# 2. 데이터 불러오기 (한 번 불러온 결과는 캐시에 저장해서 재사용)
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="인구 데이터를 내려받는 중입니다...")
def load_population() -> pd.DataFrame:
    """읍·면·동 인구 데이터를 읽어온다. '코드'는 숫자가 아니라 이름표이므로 문자열로 읽는다."""
    df = pd.read_csv(POP_URL, compression="gzip", dtype={"코드": str})
    return df


@st.cache_data(show_spinner="지도 경계 데이터를 내려받는 중입니다...")
def load_geojson() -> dict:
    """전국 시군구 경계 GeoJSON을 읽어온다."""
    response = requests.get(GEOJSON_URL, timeout=30)
    response.raise_for_status()
    return response.json()


def fix_old_code(code: str) -> str:
    """
    행정구역 개편으로 예전 코드가 최신 경계 데이터와 안 맞는 경우를 보정한다.
    - 강원도(옛 코드 42) -> 강원특별자치도(51)
    - 전라북도(옛 코드 45) -> 전북특별자치도(52)
    - 군위군(옛 코드 47720, 경북) -> 27720(대구광역시로 편입)
    """
    if code == "47720":
        return "27720"
    prefix = code[:2]
    if prefix == "42":
        return "51" + code[2:]
    if prefix == "45":
        return "52" + code[2:]
    return code


# ----------------------------------------------------------------------------
# 3. 연도별 · 시군구별 인구 통계 계산 (모든 연도를 한 번에 계산해서 캐시에 저장)
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="연도별 시군구 인구를 계산하는 중입니다...")
def build_full_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    읍·면·동 인구 데이터를 연도별 · 시군구 단위로 합쳐서
    고령화율(65세 이상 비율)과 유소년 비율(0~14세 비율)을 함께 계산한다.
    """
    df = df.copy()

    # '계_' 로 시작하는 나이별 열에서 나이 숫자를 뽑아낸다.
    # 예: '계_0세' -> 0, '계_100세 이상' -> 100
    total_cols, elderly_cols, youth_cols = [], [], []
    for col in df.columns:
        if col.startswith("계_"):
            m = re.search(r"(\d+)", col)
            if not m:
                continue
            age = int(m.group(1))
            total_cols.append(col)
            if age >= 65:
                elderly_cols.append(col)
            if age <= 14:
                youth_cols.append(col)

    # 숫자가 아닌 값이 섞여 있어도 계산이 되도록 안전하게 숫자로 변환
    numeric_part = df[total_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    elderly_part = df[elderly_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    youth_part = df[youth_cols].apply(pd.to_numeric, errors="coerce").fillna(0)

    # '코드' 앞 5자리 = 시군구 코드
    code5 = df["코드"].str[:5]

    # 옛 시도 이름을 현재 이름으로 통일 (강원도->강원특별자치도, 전라북도->전북특별자치도)
    sido = df["시도"].replace(SIDO_RENAME)

    work = pd.concat(
        [
            df[["연도", "시군구"]],
            sido.rename("시도"),
            code5.rename("시군구코드"),
            numeric_part.sum(axis=1).rename("전체인구"),
            elderly_part.sum(axis=1).rename("고령인구"),
            youth_part.sum(axis=1).rename("유소년인구"),
        ],
        axis=1,
    )

    grouped = (
        work.groupby(["연도", "시군구코드"])
        .agg(
            시도=("시도", "first"),
            시군구=("시군구", "first"),
            전체인구=("전체인구", "sum"),
            고령인구=("고령인구", "sum"),
            유소년인구=("유소년인구", "sum"),
        )
        .reset_index()
    )

    grouped["고령화율"] = grouped["고령인구"] / grouped["전체인구"] * 100
    grouped["유소년비율"] = grouped["유소년인구"] / grouped["전체인구"] * 100

    return grouped


@st.cache_data(show_spinner=False)
def build_geo_table(geojson_data: dict) -> pd.DataFrame:
    """GeoJSON 속성(코드 · 시군구 · 시도)만 뽑아서 표로 만든다."""
    rows = [f["properties"] for f in geojson_data["features"]]
    geo_df = pd.DataFrame(rows)[["코드", "시군구", "시도"]]
    return geo_df


def extract_selected_codes(map_event) -> list:
    """plotly 선택 이벤트에서 클릭/선택된 지역의 '코드' 목록을 뽑아낸다."""
    if not map_event:
        return []
    selection = map_event.get("selection") if hasattr(map_event, "get") else None
    if not selection:
        return []
    points = selection.get("points", [])
    codes = []
    for pt in points:
        loc = pt.get("location")
        if loc is not None:
            codes.append(loc)
    return codes


# ----------------------------------------------------------------------------
# 4. 화면 그리기 시작
# ----------------------------------------------------------------------------
inject_style()

population_df = load_population()
geojson_data = load_geojson()
full_table = build_full_table(population_df)
geo_table = build_geo_table(geojson_data)

st.markdown(
    """
    <div class="hero">
        <div class="hero-icon">🗺️</div>
        <div>
            <div class="hero-title">전국 고령화 지도</div>
            <div class="hero-sub">시군구별 인구 구조(고령화율 · 유소년 비율)를 5단계로 나누어 한눈에 살펴봅니다.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# 5. 컨트롤 패널 (연도 슬라이더 / 지표 선택 / 시도 선택)
# ----------------------------------------------------------------------------
with st.container(border=True):
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])

    year_min = int(full_table["연도"].min())
    year_max = int(full_table["연도"].max())

    with ctrl_col1:
        selected_year = st.slider(
            "📅 연도 선택", min_value=year_min, max_value=year_max, value=year_max, step=1
        )

    with ctrl_col2:
        metric_name = st.selectbox("📊 지표 선택", list(METRIC_CONFIG.keys()))

    with ctrl_col3:
        # 경계 데이터에 실제로 있는 시도만 선택지로 제공 (없는 이름이 섞이지 않도록)
        available_sido = [s for s in SIDO_ORDER if s == "전국" or s in geo_table["시도"].unique()]
        selected_sido = st.selectbox("📍 시도 선택 (확대)", available_sido)

cfg = METRIC_CONFIG[metric_name]
ratio_col = cfg["ratio_col"]
count_col = cfg["count_col"]

# ----------------------------------------------------------------------------
# 6. 선택한 연도의 시군구 데이터 + 경계 데이터 합치기
# ----------------------------------------------------------------------------
year_df = full_table[full_table["연도"] == selected_year].copy()
year_df["코드_보정"] = year_df["시군구코드"].apply(fix_old_code)

# 경계 데이터(255개 시군구)를 기준으로 왼쪽 조인 -> 매칭 안 되는 지역도 빠짐없이 지도에 남는다
merged = geo_table.merge(
    year_df[["코드_보정", ratio_col]],
    left_on="코드",
    right_on="코드_보정",
    how="left",
)
merged["비율"] = merged[ratio_col]

# 5단계 구간 나누기 (지도 색칠용). 값이 없으면 '데이터 없음' -> 회색
merged["구간"] = pd.cut(
    merged["비율"], bins=cfg["bins"], labels=cfg["labels"], right=False
).astype("object")
missing_mask = merged["비율"].isna()
merged.loc[missing_mask, "구간"] = NO_DATA_LABEL

merged["비율_표시"] = merged["비율"].apply(
    lambda v: f"{v:.1f}%" if pd.notna(v) else NO_DATA_LABEL
)

color_map = dict(zip(cfg["labels"], cfg["colors"]))
color_map[NO_DATA_LABEL] = GRAY
category_order = cfg["labels"] + [NO_DATA_LABEL]

# 시도를 선택했으면 그 시도에 속한 지역만 남긴다 -> fitbounds가 자동으로 그 지역만 확대해 보여준다
if selected_sido != "전국":
    view_df = merged[merged["시도"] == selected_sido].copy()
else:
    view_df = merged

# ----------------------------------------------------------------------------
# 7. 지표 카드 3장 (전국 기준 - 시도 선택과 무관하게 항상 전국 값)
# ----------------------------------------------------------------------------
nation_total = year_df["전체인구"].sum()
nation_count = year_df[count_col].sum()
nation_ratio = nation_count / nation_total * 100 if nation_total else np.nan

row_max = year_df.loc[year_df[ratio_col].idxmax()]
row_min = year_df.loc[year_df[ratio_col].idxmin()]

st.write("")
card1, card2, card3 = st.columns(3)
with card1:
    st.markdown(
        kpi_card(
            f"전국 {cfg['short']} ({selected_year}년)",
            f"{nation_ratio:.1f}%",
            "전국 시군구 합산 기준",
            ACCENT,
            "🇰🇷",
        ),
        unsafe_allow_html=True,
    )
with card2:
    st.markdown(
        kpi_card(
            "가장 높은 시군구",
            f"{row_max['시군구']} · {row_max[ratio_col]:.1f}%",
            row_max["시도"],
            cfg["colors"][-1],
            "🔺",
        ),
        unsafe_allow_html=True,
    )
with card3:
    st.markdown(
        kpi_card(
            "가장 낮은 시군구",
            f"{row_min['시군구']} · {row_min[ratio_col]:.1f}%",
            row_min["시도"],
            cfg["colors"][1],
            "🔻",
        ),
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------------
# 8. 지도 그리기 + 왼쪽 위 '선택한 지역' 정보 패널
# ----------------------------------------------------------------------------
st.markdown(
    f'<div class="section-title">🗺️ {selected_year}년 {metric_name} 지도'
    f'{" · " + selected_sido if selected_sido != "전국" else ""}</div>',
    unsafe_allow_html=True,
)

fig = px.choropleth(
    view_df,
    geojson=geojson_data,
    locations="코드",                    # 경계 데이터 쪽 열: 시군구 코드(5자리)
    featureidkey="properties.코드",      # 이름이 아니라 코드로 맞춘다
    color="구간",
    category_orders={"구간": category_order},
    color_discrete_map=color_map,
    hover_name="시군구",
    hover_data={"시도": True, "비율_표시": True, "코드": False, "구간": False},
    labels={"시도": "시도", "비율_표시": metric_name},
)

# 배경 지도(타일) 없이 경계선만 보이도록 설정
fig.update_geos(visible=False, fitbounds="locations")
fig.update_traces(marker_line_color="white", marker_line_width=0.6)
fig.update_layout(
    showlegend=False,   # 기본 범례 대신 지도 위 커스텀 범례(legend_html)를 사용한다
    margin={"r": 10, "t": 10, "l": 10, "b": 10},
    height=600,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Pretendard, sans-serif", color="#374151"),
)

# 연도 · 지표 · 시도가 바뀌면 이전 클릭 선택이 새 지도와 어긋나지 않도록 키를 새로 만든다
chart_key = f"choropleth_{selected_year}_{metric_name}_{selected_sido}"

with st.container(border=True):
    st.markdown(legend_html(cfg), unsafe_allow_html=True)
    info_col, map_col = st.columns([1, 3.2])

    # 지도를 먼저 그려서 클릭/선택 결과(map_event)를 얻는다
    with map_col:
        map_event = st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displaylogo": False, "modeBarButtonsToRemove": ["select2d", "lasso2d"]},
            on_select="rerun",
            selection_mode=["points"],
            key=chart_key,
        )

    # 지도 왼쪽 위 패널: 클릭/선택한 지역을 표로 정리해서 보여준다
    with info_col:
        st.markdown('<div class="selection-panel-title">🖱️ 선택한 지역</div>', unsafe_allow_html=True)
        selected_codes = extract_selected_codes(map_event)

        if selected_codes:
            info_df = (
                view_df[view_df["코드"].isin(selected_codes)][["시도", "시군구", "비율_표시"]]
                .rename(columns={"비율_표시": cfg["short"]})
                .reset_index(drop=True)
            )
            st.dataframe(info_df, hide_index=True, use_container_width=True)
        else:
            st.markdown(
                """
                <div class="selection-empty">
                    <div class="big">👆</div>
                    지도를 클릭하면<br>선택한 지역 정보가<br>여기에 표시됩니다
                </div>
                """,
                unsafe_allow_html=True,
            )

# 데이터가 없어 회색으로 표시된 지역 안내
missing_in_view = view_df[view_df["비율"].isna()]
if not missing_in_view.empty:
    names = ", ".join(missing_in_view["시도"] + " " + missing_in_view["시군구"])
    st.warning(
        f"⚠️ {selected_year}년에는 다음 지역의 코드가 경계 데이터와 맞지 않아 "
        f"회색(데이터 없음)으로 표시됩니다: {names}"
    )

# ----------------------------------------------------------------------------
# 9. 상위 10 / 하위 10 표
# ----------------------------------------------------------------------------
st.markdown(
    f'<div class="section-title">📋 {metric_name} 상위·하위 지역 '
    f"({selected_year}년, 전국 기준)</div>",
    unsafe_allow_html=True,
)

display_df = year_df[["시도", "시군구", ratio_col]].rename(columns={ratio_col: metric_name}).copy()
display_df[metric_name] = display_df[metric_name].round(1)

top10 = display_df.sort_values(metric_name, ascending=False).head(10).reset_index(drop=True)
bottom10 = display_df.sort_values(metric_name, ascending=True).head(10).reset_index(drop=True)
top10.insert(0, "순위", range(1, len(top10) + 1))
bottom10.insert(0, "순위", range(1, len(bottom10) + 1))

bar_max = float(display_df[metric_name].max())

col_left, col_right = st.columns(2)
with col_left:
    with st.container(border=True):
        st.markdown(f"**🔺 {metric_name} 높은 지역 TOP 10**")
        st.dataframe(
            top10,
            use_container_width=True,
            hide_index=True,
            column_config={
                metric_name: st.column_config.ProgressColumn(
                    metric_name, format="%.1f%%", min_value=0, max_value=bar_max
                )
            },
        )
with col_right:
    with st.container(border=True):
        st.markdown(f"**🔻 {metric_name} 낮은 지역 TOP 10**")
        st.dataframe(
            bottom10,
            use_container_width=True,
            hide_index=True,
            column_config={
                metric_name: st.column_config.ProgressColumn(
                    metric_name, format="%.1f%%", min_value=0, max_value=bar_max
                )
            },
        )

st.markdown(
    '<div class="footer-note">데이터 출처: 행정안전부 주민등록인구 (읍·면·동) · '
    "경계 데이터: 전국 시군구 GeoJSON</div>",
    unsafe_allow_html=True,
)
