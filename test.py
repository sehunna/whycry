from google import genai
from config import GEMINI_API_KEY

def list_available_models():
    if not GEMINI_API_KEY:
        print("API 키가 설정되지 않았습니다.")
        return
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("사용 가능한 모델 목록 조회를 시도합니다...")
    try:
        models = client.models.list()
        print("\n--- 가용한 generateContent 모델 목록 ---")
        for m in models:
            if hasattr(m, 'supported_actions') and 'generateContent' in m.supported_actions:
                print(f"Name: {m.name} | DisplayName: {m.display_name}")
    except Exception as e:
        print(f"모델 조회 중 에러 발생: {e}")

if __name__ == "__main__":
    list_available_models()