# fin-aily-us

미국 주식 뉴스와 기업 공시를 **AI가 투자자 관점의 핵심 인사이트로 정제**해주는 웹 서비스.
쏟아지는 영어 뉴스와 수백 페이지짜리 SEC 공시를 대신 읽고, 투자 판단에 필요한 내용만 한국어로 요약해준다.

**🌐 바로 써보기**

| | URL |
|---|---|
| 서비스 (Frontend) | https://fin-aily-us.vercel.app |
| API (Backend) | https://fin-aily-us-437915204376.asia-northeast1.run.app |

---

## 무엇을 할 수 있나요?

### 📰 Ticker Brief — 종목 뉴스 즉시 요약
티커(예: `AAPL`, `TSLA`)를 검색하면 최신 뉴스를 모아 AI가 **핵심 불렛 포인트**로 정리해준다.
뉴스 흐름이 긍정적인지 부정적인지를 수치로 보여주는 **Sentiment Score**도 함께 제공한다.

### 🌊 Market Pulse — 오늘의 시장 한눈에
검색 없이 접속만 하면, 지금 시장에서 가장 뜨거운 경제 이슈를 AI가 요약해 보여준다.

### 🔬 Deep Lab — 애널리스트 수준의 심층 리서치
티커 하나만 입력하면, AI가 그 기업의 **SEC 공시(10-K/10-Q)를 직접 읽고** 애널리스트 리포트를 써준다.
아래에서 자세히 설명한다.

---

## 🔬 Deep Research 자세히 보기

증권사 애널리스트 리포트 한 편을 쓰려면 수백 페이지의 사업보고서를 읽고, 재무제표를 뜯어보고,
경쟁사·밸류에이션까지 비교해야 한다. Deep Research는 이 과정을 **AI 파이프라인으로 자동화**한 기능이다.

### 어떻게 동작하나요?

1. **공시 수집** — 미국 증권거래위원회(SEC)의 공식 데이터베이스 EDGAR에서 해당 기업의 최신 10-K(연간)·10-Q(분기) 공시와 재무 데이터를 가져온다.
2. **나눠서 읽기 (Map)** — 대용량 공시를 섹션별로 쪼개, 여러 개의 AI 요약을 **동시에 병렬로** 처리한다.
3. **합쳐서 리포트로 (Reduce)** — 요약된 조각들을 하나의 리포트로 합성한다. 목차·표·출처가 포함된 완성된 문서가 나온다.
4. **교차 검증** — 앞선 분석 결과를 종합해 Executive Summary와 최종 평가를 마지막에 작성하고, 근거가 부족한 항목은 "데이터 한계"로 솔직하게 표시한다.

> 이런 방식을 **Map-Reduce LLM 파이프라인**이라고 부른다. 큰 문서를 잘게 나눠 병렬로 처리(Map)한 뒤 하나로 합치는(Reduce) 구조라, 방대한 공시도 빠르고 일관되게 분석할 수 있다.

### 리포트에 담기는 10가지 분석

| # | 섹션 | 다루는 내용 |
|---|---|---|
| 1 | Executive Summary | 사업 개요, 투자 논거, 강세·약세 요인 종합 |
| 2 | Business Structure | 사업 구조와 경영진 내러티브의 변화 |
| 3 | Financial Quality | 매출·마진 추세와 이익의 질 |
| 4 | Filing Delta | 작년 대비 공시 내용이 어떻게 바뀌었는지 |
| 5 | Competitive Landscape | 경쟁 구도와 고객 집중도 리스크 |
| 6 | Capital Allocation | 자본을 어디에 어떻게 쓰는가 (등급 평가) |
| 7 | Earnings & Guidance | 실적 발표·가이던스의 신뢰도와 반복 주제 |
| 8 | Consensus & Valuation | 애널리스트 컨센서스와 밸류에이션 시나리오 |
| 9 | Technical & Risks | 기술적 분석과 단기·장기 리스크 |
| 10 | Variant Perception | 시장과 다른 관점, 최종 평점, 모니터링 KPI |

### 사용 방법

1. 홈에서 **Deep Lab** 탭 선택 → 티커 검색
2. 리서치 페이지(`/stock/{symbol}/research`)로 이동하면 생성이 시작된다
3. 리포트 작성은 백그라운드에서 진행되며, 화면이 진행 상태를 실시간으로 보여준다 (**약 2~4분** 소요)
4. 완성된 리포트는 **7일(168시간) 동안 캐시**되어, 같은 종목을 다시 열면 즉시 표시된다

> ℹ️ 현재는 **개인 사용 모드**로, 로그인 없이 누구나 조회·생성할 수 있다.
> (사용자별 로그인·한도 기능은 추후 재도입 예정 — [이슈 #8](https://github.com/jonas-jun/fin-aily-us/issues/8)에 문서화)

> ⚠️ 생성된 리포트는 AI가 공시를 자동 분석한 결과로, **투자 참고용 정보이며 투자 자문이나 매매 권유가 아니다.**

---

## 🛠️ 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | FastAPI, Python 3.13 |
| AI 분석 | Google Gemini |
| 뉴스 수집 | yfinance, feedparser (RSS) |
| 공시 데이터 | SEC EDGAR |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| 배포 | Backend: Google Cloud Run · Frontend: Vercel |

관련 프로젝트: [fin-aily-kr](https://github.com/jonas-jun/fin-aily-kr) — 한국 상장 종목 버전 (네이버 증권 + Gemini)

---

<details>
<summary><b>👨‍💻 개발자용: 로컬 실행 가이드</b> (클릭해서 펼치기)</summary>

### 사전 요구사항
- Python 3.11+, Node.js 18+
- [Gemini API 키](https://aistudio.google.com/app/apikey)
- [Supabase 프로젝트](https://supabase.com)

뉴스 API와 심층 리서치 API는 **하나의 FastAPI 앱**으로 통합되어 있다. 백엔드(8000) + 프론트엔드(3000) 두 프로세스만 띄우면 전체 기능이 동작한다.

### 1. Supabase 설정
1. Supabase 대시보드에서 새 프로젝트 생성
2. **Project Settings > API** 에서 `URL`, `service_role key` 복사
3. **SQL Editor** 에서 마이그레이션을 순서대로 실행:
   - `backend/migrations/001_initial_schema.sql`
   - `backend/migrations/002_research.sql`
   - `backend/migrations/003_summary_articles.sql`

### 2. Backend
```bash
cd backend
cp .env.example .env        # API 키·Supabase 정보·EDGAR_USER_AGENT 등 입력
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Swagger UI: `http://localhost:8000/docs` (`.env`에 `DEBUG=true` 필요)

### 3. Frontend
```bash
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL 입력
npm install
npm run dev
```
브라우저에서 `http://localhost:3000` 접속.

### 환경변수

**Backend (`backend/.env`)**
```
GEMINI_API_KEY=your-gemini-api-key
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
APP_ENV=development
DEBUG=true
CORS_ORIGINS=["http://localhost:3000"]

# Deep Research (심층 리서치)
EDGAR_USER_AGENT=fin-aily-us deep-research your-email@example.com
DEEP_RESEARCH_CACHE_DIR=.cache
DEEP_RESEARCH_OUTPUT_DIR=reports
RESEARCH_REPORT_TTL_HOURS=168
RESEARCH_JOB_TIMEOUT_MINUTES=15
RESEARCH_API_USE_LLM=true
RESEARCH_API_RUN_QA=false
```

**Frontend (`frontend/.env.local`)**
```
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```
백엔드 연동은 `NEXT_PUBLIC_API_URL` 하나면 충분하다 (**`/v1` 경로 포함**). 브리핑·심층 리서치 모두 같은 백엔드를 사용한다.

### API

모든 엔드포인트는 하나의 backend(포트 8000)에서 제공된다.

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/v1/news/{symbol}` | 종목 최신 뉴스 수집 + AI 요약 |
| `GET` | `/v1/news/market-pulse` | 시장 전체 뉴스 AI 요약 |
| `GET` | `/v1/tickers/search?q={쿼리}` | 티커·종목명 자동완성 (Rate Limit: 30회/분) |
| `POST` | `/v1/research/{symbol}` | 심층 리서치 잡 시작 (`?force=true`로 강제 재생성, Rate Limit: 5회/분/IP) |
| `GET` | `/v1/research/{symbol}` | 최신 완료 리포트 조회 |
| `GET` | `/v1/research/jobs/{job_id}` | 잡 상태·완료 리포트 폴링 |

> 개인 사용 모드로 `/v1/research/*`는 인증 없이 열려 있다. 인증 로직(`get_current_user`)은 `backend/app/dependencies.py`에 보존되어 있어, 필요 시 각 라우터에 `Depends`로 다시 연결할 수 있다.

### 배포
- **Frontend**: Vercel — main 브랜치 push 시 자동 배포. `NEXT_PUBLIC_API_URL`에 Cloud Run URL + `/v1` 설정 (값 변경 시 Redeploy 필요)
- **Backend**: Google Cloud Run — `--no-cpu-throttling`(응답 반환 후에도 백그라운드 리서치 잡이 CPU를 계속 사용)과 `--min-instances 1`(유휴 시 인스턴스 회수로 잡이 중단되는 것 방지) 플래그가 필수. 상세 절차는 `working/cloudrun.md` 참조

</details>
