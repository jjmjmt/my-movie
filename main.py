import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz

# 1. 페이지 기본 설정 및 제목
st.set_page_config(page_title="어제 박스오피스", layout="wide")
st.title("🎬 어제 일일 박스오피스 순위")

# 2. 한국 시간 기준으로 '어제' 날짜 구하기 (배포 서버의 시차 문제 해결)
try:
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    yesterday_kst = now_kst - timedelta(days=1)
    target_date = yesterday_kst.strftime('%Y%m%d')
    target_date_formatted = yesterday_kst.strftime('%Y년 %m월 %d일')
except Exception as e:
    st.error(f"날짜를 계산하는 중 오류가 발생했습니다: {e}")
    st.stop()

st.subheader(f"📅 조회 기준일: {target_date_formatted}")

# 3. Streamlit Secret에서 API 키 불러오기 (보안 유지)
if "KOBIS_KEY" not in st.secrets:
    st.error("🔑 Streamlit Cloud의 Secrets 설정에서 'KOBIS_KEY'를 추가해 주세요.")
    st.info("💡 **확인 방법:** Streamlit 대시보드 -> App Settings -> Secrets에 `KOBIS_KEY = '발급받은키'` 형태로 입력해야 합니다.")
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# 4. API 데이터 호출 및 캐싱 설정 (동일 날짜 재호출 방지, TTL: 1시간 = 3600초)
@st.cache_data(ttl=3600)
def fetch_box_office(key, date):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": key, "targetDt": date}
    
    try:
        response = requests.get(url, timeout=10)
        # HTTP 연결 실패나 서버 에러 대응
        if response.status_code != 200:
            return {"error_type": "http", "code": response.status_code}
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error_type": "request", "message": str(e)}

# 데이터 가져오기 실행
data = fetch_box_office(api_key, target_date)

# 5. 에러 및 예외 상황 처리 (faultInfo 또는 데이터 누락)
if not data:
    st.error("❌ 영화진흥위원회 API로부터 응답을 받지 못했습니다.")
    st.info("💡 **확인 내용:** 네트워크 상태를 확인하거나 잠시 후 다시 시도해 주세요.")
    st.stop()

# HTTP 에러 케이스 처리
if isinstance(data, dict) and "error_type" in data:
    st.error(f"❌ API 요청 실패 (HTTP 상태 코드: {data.get('code', 'Unknown')})")
    st.info("💡 **확인 내용:** 요청 주소가 정확한지, 또는 영화진흥위원회 서버 상태에 문제가 없는지 확인해 주세요.")
    st.stop()

# API는 성공(200)했으나 내부 인증키 오류 등으로 faultInfo가 반환된 경우
if "faultInfo" in data:
    error_msg = data["faultInfo"].get("message", "알 수 없는 오류")
    st.error(f"❌ KOBIS API 오류가 발생했습니다: {error_msg}")
    st.info("💡 **확인 내용:** Streamlit Secrets에 등록된 `KOBIS_KEY`가 올바르게 발급받은 키인지 다시 확인해 주세요.")
    st.stop()

# 정상 구조 파싱
boxoffice_result = data.get("boxOfficeResult", {})
movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

# 영화 목록이 비어 있는 경우 (아직 집계가 안 끝났거나 날짜 오류 등)
if not movie_list:
    st.warning("⚠️ 어제 날짜의 박스오피스 데이터가 아직 비어 있습니다.")
    st.info("💡 **확인 내용:** 영화진흥위원회(KOBIS)에서 해당 날짜의 최종 정산·집계가 아직 진행 중일 수 있습니다. 잠시 후 새로고침해 주세요.")
    st.stop()

# 6. 데이터프레임 변환 및 데이터 정제 (문자열 -> 숫자형 변환)
df = pd.DataFrame(movie_list)

# 분석 및 그래프 표현을 위해 문자열 형태의 숫자를 정수형(numeric)으로 변환
df['rank'] = pd.to_numeric(df['rank'])
df['audiCnt'] = pd.to_numeric(df['audiCnt'])
df['audiAcc'] = pd.to_numeric(df['audiAcc'])
df['scrnCnt'] = pd.to_numeric(df['scrnCnt'])

# 순위 순서대로 확실하게 오름차순 정렬
df = df.sort_values(by='rank').reset_index(drop=True)

# 7. 화면 구현: 1위 영화 지표 카드 세 장 (상단 배치)
top_movie = df.iloc[0]

st.markdown("---")
st.markdown(f"### 🥇 오늘의 1위 영화: **{top_movie['movieNm']}**")

# 세 장의 카드를 가로로 분할 배치
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="🎬 당일 관객수", value=f"{top_movie['audiCnt']:,} 명")
with col2:
    st.metric(label="🍿 누적 관객수", value=f"{top_movie['audiAcc']:,} 명")
with col3:
    st.metric(label="🖥️ 스크린수", value=f"{top_movie['scrnCnt']:,} 개")

st.markdown("---")

# 8. 화면 구현: 관객수 상위 5편 막대그래프 & 전체 순위 표 (좌우 레이아웃 배치)
left_col, right_col = st.columns([1, 1])

with left_col:
    st.markdown("### 📊 관객수 상위 5편 영화")
    # 상위 5편만 추출
    df_top5 = df.head(5).copy()
    # 내장형 막대그래프 출력
    st.bar_chart(
        data=df_top5,
        x="movieNm",
        y="audiCnt",
        color="#ff4b4b",
        use_container_width=True
    )

with right_col:
    st.markdown("### 📋 전체 박스오피스 순위 목록")
    
    # 출력용 데이터프레임 생성 및 열 이름 한글 변경
    view_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
    view_df.columns = ['순위', '영화명', '개봉일', '당일 관객수', '누적 관객수', '스크린수']
    
    # 천 단위 콤마(,) 포맷팅 적용
    formatted_df = view_df.style.format({
        '당일 관객수': '{:,.0f}',
        '누적 관객수': '{:,.0f}',
        '스크린수': '{:,.0f}'
    })
    
    # 깔끔한 표(DataFrame) 형태로 출력
    st.dataframe(formatted_df, use_container_width=True, hide_index=True)
