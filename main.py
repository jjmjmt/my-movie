import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz

# 1. 페이지 기본 설정 및 제목 출력
st.set_page_config(page_title="어제 박스오피스", layout="wide")
st.title("🎬 어제 박스오피스 리포트")

# 2. 한국 시간(KST) 기준으로 '어제' 날짜 자동 계산
try:
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    yesterday_kst = now_kst - timedelta(days=1)
    target_date = yesterday_kst.strftime('%Y%m%d')
    target_date_formatted = yesterday_kst.strftime('%Y년 %m월 %d일')
except Exception as e:
    st.error("날짜를 계산하는 중 오류가 발생했습니다.")
    st.stop()

st.subheader(def_date := f"📅 조회 기준일: {target_date_formatted}")

# 3. KOBIS API 호출 함수 (스트림릿 캐시 적용: 1시간 동안 결과 기억)
# ttl=3600 설정을 통해 동일한 날짜의 반복 요청 시 API를 다시 부르지 않고 캐시를 사용합니다.
@st.cache_data(ttl=3600)
def fetch_box_office(api_key, date_str):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": date_str}
    
    try:
        response = requests.get(url, timeout=10)
        # HTTP 상태 코드가 200이 아니면 예외 발생
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

# 4. 스트림릿 Secrets에서 API 키 불러오기
if "KOBIS_KEY" not in st.secrets:
    st.error("🚨 [인증 오류] Streamlit Cloud의 Secrets에 'KOBIS_KEY'가 설정되지 않았습니다.")
    st.markdown("""
    **확인 방법:**
    1. 스트림릿 클라우드 대시보드로 이동합니다.
    2. 해당 앱의 **Settings > Secrets** 메뉴를 엽니다.
    3. 아래와 같이 입력하고 저장하세요:
    ```toml
    KOBIS_KEY = "발급받은_KOBIS_인증키"
    ```
    """)
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# 5. 데이터 가져오기 실행
with st.spinner("영화진흥위원회에서 데이터를 가져오는 중입니다..."):
    data = fetch_box_office(api_key, target_date)

# 6. 에러 처리 및 결과 검증 안내문
error_guide = """
**🛠️ 아래 내용을 확인해 주세요:**
1. **API 인증키 확인**: 스트림릿 Secrets에 입력한 `KOBIS_KEY`가 올바른지, 만료되지 않았는지 확인해 주세요.
2. **네트워크 상태**: 영화진흥위원회(KOBIS) 서버의 일시적인 장애이거나 네트워크 연결 문제일 수 있습니다.
3. **집계 시간 확인**: 한국 시간으로 어제 데이터가 아직 완전히 집계되지 않았을 수 있습니다. 잠시 후 다시 시도해 주세요.
"""

if data is None:
    st.error("🚨 API 요청에 실패했습니다. (네트워크 오류 또는 서버 응답 없음)")
    st.markdown(error_guide)
    st.stop()

# 영화진흥위원회는 인증키가 틀려도 200 OK와 함께 faultInfo를 반환합니다.
if "faultInfo" in data:
    st.error(f"🚨 API 서버에서 오류를 반환했습니다. (오류 메시지: {data['faultInfo'].get('message', '알 수 없음')})")
    st.markdown(error_guide)
    st.stop()

boxoffice_result = data.get("boxOfficeResult", {})
movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

if not movie_list:
    st.warning("⚠️ 조회된 영화 목록이 비어 있습니다.")
    st.markdown(error_guide)
    st.stop()

# 7. 데이터 프레임 변환 및 전처리 (문자열 숫자를 실제 숫자로 변환)
df = pd.DataFrame(movie_list)

# 필요한 열 형변환 (정렬 및 그래프 시각화 목적)
df['rank'] = pd.to_numeric(df['rank'])
df['audiCnt'] = pd.to_numeric(df['audiCnt'])
df['audiAcc'] = pd.to_numeric(df['audiAcc'])
df['scrnCnt'] = pd.to_numeric(df['scrnCnt'])

# 순위 기준으로 오름차순 정렬
df = df.sort_values(by='rank').reset_index(drop=True)

# 8. 1위 영화 주요 지표 카드 출력 (3장)
top_movie = df.iloc[0]
st.markdown(f"### 🏆 오늘의 1위 영화: **{top_movie['movieNm']}**")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="어제 관객수", value=f"{top_movie['audiCnt']:,} 명")
with col2:
    st.metric(label="누적 관객수", value=f"{top_movie['audiAcc']:,} 명")
with col3:
    st.metric(label="확보 스크린수", value=f"{top_movie['scrnCnt']:,} 개")

st.markdown("---")

# 9. 상위 5편 막대그래프 시각화 (시각화를 위해 데이터 가공)
st.write("📊 **관객수 상위 5편 비교**")
df_top5 = df.head(5)[['movieNm', 'audiCnt']].copy()
# 스트림릿 그래프용 인덱스 설정
df_top5 = df_top5.set_index('movieNm')

# 세로 막대그래프 출력
st.bar_chart(df_top5)

st.markdown("---")

# 10. 전체 박스오피스 순위 표(Table) 출력
st.write("📋 **전체 순위 표**")

# 화면에 보여줄 열만 선택하고 보기 좋은 이름으로 변경
df_display = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
df_display.columns = ['순위', '영화명', '개봉일', '관객수', '누적관객', '스크린수']

# 숫자에 쉼표(,)를 넣어 가독성을 높인 포맷 적용
st.dataframe(
    df_display.style.format({
        '순위': '{:d}위',
        '관객수': '{:,.0f}명',
        '누적관객': '{:,.0f}명',
        '스크린수': '{:,.0f}개'
    }),
    use_container_width=True
)
