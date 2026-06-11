import os

# 필요시 .env 파일을 읽기 위해 python-dotenv가 설치되어 있다면 로드합니다.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 비디오 및 오디오 분석을 수행할 Gemini 모델을 지정합니다.
# gemini-1.5-flash 모델은 멀티모달 분석(비디오, 오디오) 및 구조화된 출력을 지원하며 빠르고 경제적입니다.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not GEMINI_API_KEY:
    print("[WARNING] GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다. .env 파일이나 시스템 환경 변수에 설정해 주세요.")
