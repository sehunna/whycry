# Implementation Plan: WhyCry (아기 울음 분석 서비스) - 설계 확정안

이 서비스는 아기가 울 때 촬영한 10~15초 분량의 영상을 분석하여 아기의 행동(비디오)과 울음소리(오디오), 그리고 부모가 입력한 추가 정보(수유 시간, 기저귀 상태, 체온, 수면 시간 등)를 종합적으로 결합하여 아기가 우는 원인을 확률로 추론하고 맞춤형 대응 방안을 제공하는 서비스입니다.

---

## Technical Decisions (확정된 설계 방향)

1.  **개발 언어 및 환경**: **Python 3.10+**
    *   비디오에서 오디오를 추출하는 라이브러리(`ffmpeg` 또는 `moviepy`)와 Gemini API용 공식 SDK(`google-genai`)를 활용해 가볍고 효율적인 파이프라인을 구축합니다.
2.  **오디오 분석**: **Gemini Multimodal API 직접 활용**
    *   추출된 아기 울음소리 오디오 파일(WAV/MP3)을 Gemini API에 주입하여, 오디오의 주파수 대역, 템포, 톤(날카로움, 칭얼거림 등)을 자연어 및 구조화된 데이터로 직접 분석합니다.
3.  **종합 분석 및 스코어링**: **하이브리드 (가중치 룰 + LLM)**
    *   비디오/오디오 분석 결과와 부모의 컨텍스트 입력을 바탕으로 정의된 가중치 규칙(Score Rule)에 따라 1차 물리 점수를 계산합니다.
    *   계산된 스코어 테이블과 상세 관찰 내용을 프롬프트에 담아 Gemini LLM에 전달하여 최종 확률 분배 및 부모를 위한 케어 가이드를 얻습니다.

---

## Proposed Data Schema (데이터 구조 및 스키마)

사용자께서 제안해 주신 스키마를 바탕으로, 비디오 분석 모듈과 오디오 분석 모듈이 관찰 영역을 명확히 나누어 처리한 뒤 `analysis` 모듈에서 이를 종합할 수 있도록 스키마를 고도화하였습니다.

### 1. [video](file:///c:/project/whycry/video) 모듈 출력 스키마 (Video Observation)
비디오 파일에서 시각적으로 관찰된 아기의 움직임과 표정을 정량화합니다.
```json
{
  "hand_to_mouth": true,         // 손을 입으로 가져가는 행동 여부
  "mouth_movement": true,        // 빠는 듯한 입 움직임 여부
  "eye_closing": "low",          // 눈 감음 강도 ("none", "low", "moderate", "high")
  "facial_grimace": true,        // 얼굴 찡그림 여부
  "body_squirming": true,        // 몸을 비틀거나 꿈틀거림 여부
  "leg_pull_to_belly": "possible", // 다리를 배 쪽으로 끌어당김 여부 ("no", "possible", "evident")
  "back_arching": "no",          // 등 활처럼 휘기 여부 ("no", "possible", "evident")
  "movement_level": "active",    // 전반적인 움직임 수준 ("calm", "active", "hyperactive")
  "face_visible": true,          // 얼굴이 잘 보이는지 여부
  "upper_body_visible": true,    // 상반신이 잘 보이는지 여부
  "visible_red_flags": []        // 긴급 대처가 필요한 시각적 징후 (예: "cyanosis", "seizure_like" 등, 평소엔 빈 배열)
}
```

### 2. [audio](file:///c:/project/whycry/audio) 모듈 출력 스키마 (Audio Observation)
추출된 오디오 파일에서 울음소리의 성격을 분석합니다.
```json
{
  "cry_present": true,           // 울음소리 존재 여부
  "cry_intensity": "moderate",   // 울음 강도 ("low", "moderate", "high")
  "cry_pattern": "intermittent", // 울음 패턴 ("intermittent", "continuous", "whimpering", "sudden_intense")
  "audio_clear": true,           // 음질이 깨끗하고 분석 가능한지 여부
  "estimated_emotion": "frustrated" // 울음소리 톤 기반 추정 감정
}
```

### 3. 사용자 컨텍스트 데이터 (Parent Context)
부모가 앱을 통해 입력하는 맥락 정보입니다.
```json
{
  "age_days": 38,
  "last_feeding_minutes_ago": 165,
  "last_diaper_change_minutes_ago": 80,
  "last_sleep_ended_minutes_ago": 45,
  "burped_after_last_feeding": false,
  "temperature_celsius": null
}
```

---

## 스코어링 알고리즘 (Scoring Logic)

각 스코어는 제안해 주신 룰을 구체적인 수치 가중치로 세분화하였습니다. 점수는 각 원인 카테고리별로 계산되며, 분석 모듈이 최종 LLM에 이 스코어 카드를 해석 단서로 제공합니다.

### 1. 배고픔 점수 (`hunger_score`)
*   `last_feeding_minutes_ago >= 150` (마지막 수유 후 2시간 반 경과) : **+40점**
*   `last_feeding_minutes_ago >= 120` (마지막 수유 후 2시간 경과) : **+20점**
*   `hand_to_mouth == true` (손을 입으로 가져감) : **+20점**
*   `mouth_movement == true` (입을 오물거림) : **+15점**
*   `cry_pattern == "intermittent"` (간헐적인 울음소리) : **+15점**
*   `last_feeding_minutes_ago <= 60` (최근 1시간 내 수유 완료) : **-50점 (감점)**

### 2. 가스/트림 필요 점수 (`gas_or_burp_score`)
*   `body_squirming == true` (몸을 비틀거림) : **+15점**
*   `leg_pull_to_belly`가 `possible`이면 **+15점**, `evident`이면 **+25점** (다리를 배로 끌어당김)
*   `facial_grimace == true` (얼굴 찌푸림) : **+15점**
*   `burped_after_last_feeding == false` (수유 후 트림 안 함) : **+25점**
*   `last_feeding_minutes_ago <= 60` (수유 후 1시간 이내 울음 발생) : **+20점**

### 3. 졸림 점수 (`sleepy_score`)
*   `eye_closing`이 `moderate`이면 **+15점**, `high`이면 **+30점** (눈을 자주 감음)
*   `movement_level == "calm"` (움직임 적음) : **+15점**
*   `last_sleep_ended_minutes_ago >= 120` (잠에서 깬 지 2시간 이상 경과) : **+30점**
*   `cry_pattern == "whimpering"` (칭얼거리는 울음) : **+25점**

### 4. 기저귀 점수 (`diaper_score`)
*   `last_diaper_change_minutes_ago >= 180` (기저귀 간 지 3시간 이상 경과) : **+40점**
*   `last_diaper_change_minutes_ago >= 120` (기저귀 간 지 2시간 이상 경과) : **+20점**
*   `body_squirming == true` (불편하여 몸을 꼼지락거림) : **+15점**
*   `hunger_score < 40` (배고픔 점수가 낮아 배고픈 게 아닐 가능성이 높음) : **+20점**
*   *(추가 제안)* 부모가 기저귀 상태를 명시적으로 '젖음' 또는 '대변'으로 입력 시 : **즉시 +80점 부여**

### 5. 아픔/기타 불편함 점수 (`pain_or_discomfort_score`)
*   `temperature_celsius >= 37.5` (미열) : **+30점**, `temperature_celsius >= 38.0` (고열) : **+60점**
*   `back_arching`이 `possible`이면 **+15점**, `evident`이면 **+30점** (신체 통증이나 산통 징후)
*   `cry_pattern == "sudden_intense"` (갑작스럽고 격렬한 울음) : **+30점**

---

## Proposed Architecture (서비스 모듈 구조)

```
whycry/
├── main.py              # 엔드투엔드 파이프라인 실행 및 오케스트레이터
├── config.py            # API 키 관리 및 공통 설정
├── video/
│   ├── __init__.py
│   └── video_analyzer.py # Gemini Video Understanding API를 통한 행동 정보 추출 (JSON)
├── audio/
│   ├── __init__.py
│   ├── audio_extractor.py # MoviePy/FFmpeg를 이용해 영상에서 오디오 추출 (WAV)
│   └── audio_analyzer.py # Gemini Multimodal API를 통한 울음소리 분석 (JSON)
└── analysis/
    ├── __init__.py
    ├── scorer.py        # 1차 가중치 스코어 연산 모듈
    └── reasoner.py      # LLM을 활용한 종합 추론 및 대응 가이드 생성
```

---

## Verification Plan (검증 계획)

### 1단계: 단위 테스트 및 API 연동 확인
- `video/video_analyzer.py`: 샘플 10초 비디오로 Gemini API가 구조화된 비디오 분석 결과를 올바르게 리턴하는지 확인.
- `audio/audio_extractor.py`: 비디오 파일에서 성공적으로 `.wav` 오디오를 분리하는지 확인.
- `audio/audio_analyzer.py`: 분리된 `.wav` 파일로 Gemini API가 울음소리 스키마 형태로 분석 결과를 리턴하는지 확인.

### 2단계: 스코어링 및 최종 추론 테스트
- `analysis/scorer.py`: 가상의 입력 상황(예: 수유 165분 전, 손가락 빎 등)을 넣었을 때 점수가 의도대로 산출되는지 테스트 케이스 검증.
- `analysis/reasoner.py`: 스코어 결과 데이터를 프롬프트로 생성하여 Gemini LLM이 적합한 확률 및 따뜻한 조언 텍스트를 출력하는지 확인.

### 3단계: 통합 검증 (`main.py`)
- 실제 테스트 비디오 파일과 사용자 입력 데이터를 모킹하여 E2E로 구동하여 종합 리포트를 도출하는지 전체 프로세스 점검.
