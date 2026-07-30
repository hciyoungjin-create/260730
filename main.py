# -*- coding: utf-8 -*-
"""
전국 고령화 지도 (시군구별 인구 구조 단계구분도)
--------------------------------------------------------
- 인구 데이터: 읍·면·동 단위 연도별 인구 (2015~2026)
- 경계 데이터: 전국 시군구 255개 GeoJSON
- '코드' 열을 기준으로 인구 데이터(읍면동)와 경계 데이터(시군구)를 연결한다.
- 연도 슬라이더, 지표 선택(고령화율/유소년 비율), 시도 확대 기능 포함
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
st.set_page_config(page_title="전국 고령화 지도", layout="wide")

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
        "bins": [-np.inf, 19, 23, 28, 38, np.inf],
        "labels": ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"],
        # 옅은 색 -> 진한 색 (5단계로 끊어서 칠하고, 연속 그라데이션은 쓰지 않는다)
        "colors": ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"],
    },
    "유소년 비율 (0~14세 비율)": {
        "ratio_col": "유소년비율",
        "count_col": "유소년인구",
        "bins": [-np.inf, 6, 8, 10, 12, np.inf],
        "labels": ["6% 미만", "6% ~ 8%", "8% ~ 10%", "10% ~ 12%", "12% 이상"],
        "colors": ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
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


# ----------------------------------------------------------------------------
# 1. 데이터 불러오기 (한 번 불러온 결과는 캐시에 저장해서 재사용)
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
# 2. 연도별 · 시군구별 인구 통계 계산 (모든 연도를 한 번에 계산해서 캐시에 저장)
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


# ----------------------------------------------------------------------------
# 3. 데이터 준비
# ----------------------------------------------------------------------------
population_df = load_population()
geojson_data = load_geojson()
full_table = build_full_table(population_df)
geo_table = build_geo_table(geojson_data)

st.title("🗺️ 전국 고령화 지도")
st.caption("시군구별 인구 구조(고령화율 · 유소년 비율)를 5단계로 나누어 표시합니다.")

# ----------------------------------------------------------------------------
# 4. 화면 상단 컨트롤: 연도 슬라이더 / 지표 선택 / 시도 선택
# ----------------------------------------------------------------------------
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])

year_min = int(full_table["연도"].min())
year_max = int(full_table["연도"].max())

with ctrl_col1:
    selected_year = st.slider(
        "연도 선택", min_value=year_min, max_value=year_max, value=year_max, step=1
    )

with ctrl_col2:
    metric_name = st.selectbox("지표 선택", list(METRIC_CONFIG.keys()))

with ctrl_col3:
    # 경계 데이터에 실제로 있는 시도만 선택지로 제공 (없는 이름이 섞이지 않도록)
    available_sido = [s for s in SIDO_ORDER if s == "전국" or s in geo_table["시도"].unique()]
    selected_sido = st.selectbox("시도 선택 (확대)", available_sido)

cfg = METRIC_CONFIG[metric_name]
ratio_col = cfg["ratio_col"]
count_col = cfg["count_col"]

# ----------------------------------------------------------------------------
# 5. 선택한 연도의 시군구 데이터 + 경계 데이터 합치기
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
# 6. 지표 카드 3장 (전국 기준 - 시도 선택과 무관하게 항상 전국 값)
# ----------------------------------------------------------------------------
nation_total = year_df["전체인구"].sum()
nation_count = year_df[count_col].sum()
nation_ratio = nation_count / nation_total * 100 if nation_total else np.nan

row_max = year_df.loc[year_df[ratio_col].idxmax()]
row_min = year_df.loc[year_df[ratio_col].idxmin()]

card1, card2, card3 = st.columns(3)
with card1:
    st.metric(f"전국 {metric_name.split(' ')[0]}", f"{nation_ratio:.1f}%")
with card2:
    st.metric(
        "가장 높은 시군구",
        f"{row_max['시군구']} · {row_max[ratio_col]:.1f}%",
        row_max["시도"],
        delta_color="off",
    )
with card3:
    st.metric(
        "가장 낮은 시군구",
        f"{row_min['시군구']} · {row_min[ratio_col]:.1f}%",
        row_min["시도"],
        delta_color="off",
    )

# ----------------------------------------------------------------------------
# 7. 지도 그리기
# ----------------------------------------------------------------------------
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
fig.update_traces(marker_line_color="white", marker_line_width=0.5)
fig.update_layout(
    margin={"r": 0, "t": 10, "l": 0, "b": 0},
    legend_title_text="구간",
    height=650,
)

st.plotly_chart(fig, use_container_width=True)

# 데이터가 없어 회색으로 표시된 지역 안내
missing_in_view = view_df[view_df["비율"].isna()]
if not missing_in_view.empty:
    names = ", ".join(missing_in_view["시도"] + " " + missing_in_view["시군구"])
    st.info(
        f"⚠️ {selected_year}년에는 다음 지역의 코드가 경계 데이터와 맞지 않아 "
        f"회색(데이터 없음)으로 표시됩니다: {names}"
    )

# ----------------------------------------------------------------------------
# 8. 상위 10 / 하위 10 표
# ----------------------------------------------------------------------------
st.subheader(f"{metric_name} 상위·하위 지역 ({selected_year}년, 전국 기준)")

display_df = year_df[["시도", "시군구", ratio_col]].rename(columns={ratio_col: metric_name}).copy()
display_df[metric_name] = display_df[metric_name].round(1)

top10 = display_df.sort_values(metric_name, ascending=False).head(10).reset_index(drop=True)
bottom10 = display_df.sort_values(metric_name, ascending=True).head(10).reset_index(drop=True)
top10.index = top10.index + 1
bottom10.index = bottom10.index + 1

col_left, col_right = st.columns(2)
with col_left:
    st.markdown(f"**🔺 {metric_name} 높은 지역 TOP 10**")
    st.dataframe(top10, use_container_width=True)
with col_right:
    st.markdown(f"**🔻 {metric_name} 낮은 지역 TOP 10**")
    st.dataframe(bottom10, use_container_width=True)
