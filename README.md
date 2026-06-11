# 👶 WhyCry - 아기 울음 분석 및 개인화 케어 AI 솔루션

WhyCry는 아기의 미세한 행동(시각적 관찰)과 울음소리(음향적 특징)를 멀티모달 AI 엔진(Gemini 2.5 Flash)으로 종합 분석하여, 6대 울음 원인(배고픔, 배앓이, 졸림, 기저귀, 안아주기, 아픔)의 확률 분포를 추론하고 즉각적인 대처 방안 및 의학적 안내를 제공하는 소아과 전문 가이드 솔루션입니다.

특히, 아기의 울음이 단 하나의 독립된 원인이 아니라 **"배앓이와 안아주기 요구가 겹친 복합적인 상황"**임을 감안하여, **"다중 행동 피드백 및 소프트 업데이트(Soft Update) 학습 규칙"**을 적용합니다.

---

## 📺 서비스 시연 영상
아래 이미지를 클릭하면 YouTube Shorts로 연결되어 시연 영상을 시청하실 수 있습니다.

[![WhyCry 서비스 시연 영상](https://img.youtube.com/vi/nUhNjahfrB8/maxresdefault.jpg)](https://www.youtube.com/shorts/nUhNjahfrB8)

🔗 [YouTube에서 시연 영상 보기](https://www.youtube.com/shorts/nUhNjahfrB8)

---

## 🛠️ 주요 핵심 기능
1. **멀티모달 통합 분석**: 비디오 프레임과 추출된 오디오 데이터를 병렬 처리하여 시각/청각적 특징을 동시에 정밀 추론합니다.
2. **복합 개인화 (KNN + Few-shot)**: 부모가 제출한 피드백을 기반으로, 현재와 가장 유사한 과거 대처 전례 최대 3개를 추출하여 Gemini API의 Few-shot 상황에 주입하여 추론을 고도화합니다.
3. **로컬 무손실 파일 핸들링**: Windows OS 환경에서 발생할 수 있는 비디오/오디오 추출 및 인코딩 시의 파일 락(Lock) 충돌 및 오류에 대비한 완벽한 안전 예외 회복(Fallback) 설계를 갖추고 있습니다.
4. **HTML 단독 데모 기동**: API 키 노출 없이 로컬 웹브라우저(`file://`) 상에서 직접 구글 API로 멀티모달 업로드를 테스트해볼 수 있는 단일 완성형 HTML 데모 파일(`why_cry_demo.html`)을 포함합니다.

---

## 🔑 환경변수 설정
어플리케이션 구동을 위해서는 Gemini API 키가 반드시 필요합니다.

1. 프로젝트 루트 디렉터리에 `.env` 파일을 생성합니다.
2. 아래와 같이 필수 환경변수를 등록합니다. (혹은 루트의 `.env.example` 파일을 복사해 이름을 `.env`로 바꾸고 편집하여 사용하세요.)

```env
# Gemini API Key (구글 AI 스튜디오에서 발급 가능)
GEMINI_API_KEY=your_gemini_api_key_here

# 사용할 Gemini AI 모델명
GEMINI_MODEL=gemini-2.5-flash
```

---

## 🚀 설치 및 시작 방법

### 1. 가상환경 및 종속성 패키지 설치
Python 3.10 이상 환경을 권장합니다.

```bash
# 종속성 패키지 설치
pip install -r requirements.txt
```
*(만약 `requirements.txt`가 없거나 패키지가 누락된 경우 `streamlit`, `google-genai`, `requests`, `python-dotenv`, `moviepy`, `pandas` 패키지를 설치해 주십시오.)*

### 2. 웹 서비스(Streamlit) 구동
```bash
streamlit run app.py
```
* 웹브라우저 창이 열리며 아기 프로필 입력 및 동영상 업로드를 통한 종합 분석을 시작할 수 있습니다.

### 3. API 단독 업로드 테스트 실행 (디버그용)
```bash
python test_upload_api.py
```
* 로컬의 테스트용 비디오 파일을 직접 Gemini File API로 수동 조립된 `multipart/related` 규격에 맞춰 업로드해보는 검증 스크립트입니다.

---

## 📁 프로젝트 폴더 구조
* `app.py`: Streamlit 기반 웹 어플리케이션 메인 엔트리
* `config.py`: 환경 변수 및 공통 설정 관리 모듈
* `video/`: 비디오 다운사이징 및 시각 관찰 분석 엔진
* `audio/`: 오디오 추출 및 울음 주파수/패턴 분석 엔진
* `analysis/`: KNN 개인화 연동(`personalizer.py`) 및 최종 리포트 작성용 종합 의사결정 추론 모듈
* `why_cry_demo.html`: 서버가 필요 없는 단독 구동용 HTML5 웹 데모
