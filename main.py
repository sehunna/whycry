import sys
import os
import json
import datetime
from video.video_analyzer import analyze_video
from audio.audio_extractor import extract_audio
from audio.audio_analyzer import analyze_audio
from analysis.scorer import calculate_scores
from analysis.reasoner import reason_cry_cause

def main():
    if len(sys.argv) < 2:
        print("사용법: python main.py <영상_파일_경로>")
        print("예시: python main.py sample_baby_cry.mp4")
        sys.exit(1)

    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(f"[오류] 지정한 영상 파일을 찾을 수 없습니다: {video_path}")
        sys.exit(1)

    # 0. info.json (부모 입력 컨텍스트) 로드
    info_path = "info.json"
    if not os.path.exists(info_path):
        print(f"[오류] '{info_path}' 파일이 존재하지 않습니다. 테스트용 아기 정보 컨텍스트 파일이 필요합니다.")
        sys.exit(1)
        
    with open(info_path, "r", encoding="utf-8") as f:
        try:
            context = json.load(f)
        except Exception as e:
            print(f"[오류] '{info_path}' JSON 파싱 실패: {e}")
            sys.exit(1)

    print(f"\n===== [WhyCry] 아기 울음 분석 파이프라인 시작 (영상: {video_path}) =====")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 영상에서 오디오(WAV) 추출
    base_name, _ = os.path.splitext(video_path)
    audio_path = f"{base_name}.wav"
    try:
        extract_audio(video_path, audio_path)
    except Exception as e:
        print(f"[오류] 오디오 추출 과정에서 에러가 발생했습니다: {e}")
        sys.exit(1)

    # 2. 비디오 분석 (Gemini API)
    print("\n--- 1단계: 비디오 시각 정보 분석 중 (Gemini API) ---")
    try:
        video_obs = analyze_video(video_path)
        print("[Success] 비디오 시각 정보 추출 완료.")
    except Exception as e:
        print(f"[오류] 비디오 분석 과정에서 에러가 발생했습니다: {e}")
        if os.path.exists(audio_path):
            os.remove(audio_path)
        sys.exit(1)

    # 3. 오디오 분석 (Gemini API)
    print("\n--- 2단계: 오디오 음성 정보 분석 중 (Gemini API) ---")
    try:
        audio_obs = analyze_audio(audio_path)
        print("[Success] 오디오 울음소리 패턴 추출 완료.")
    except Exception as e:
        print(f"[오류] 오디오 분석 과정에서 에러가 발생했습니다: {e}")
        sys.exit(1)
    finally:
        # 추출한 임시 오디오 파일 삭제
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                print("[Main] 로컬 임시 오디오 파일(.wav) 삭제 완료.")
            except Exception as delete_err:
                print(f"[경고] 로컬 임시 오디오 파일 삭제 실패: {delete_err}")

    # 4. 가중치 점수 계산
    print("\n--- 3단계: 가중치 스코어 점수 계산 ---")
    scores = calculate_scores(video_obs, audio_obs, context)
    print(f"[계산된 점수 테이블]\n{json.dumps(scores, indent=2)}")

    # 5. 최종 종합 추론 (Gemini LLM)
    print("\n--- 4단계: 종합 원인 추론 및 가이드 생성 중 (Gemini API) ---")
    try:
        analysis_result = reason_cry_cause(scores, video_obs, audio_obs, context)
        print("[Success] 종합 추론 보고서 생성 성공.")
    except Exception as e:
        print(f"[오류] 최종 추론 과정에서 에러가 발생했습니다: {e}")
        sys.exit(1)

    # 6. 콘솔 출력
    print("\n==================================================")
    print("                 [최종 분석 보고서]                ")
    print("==================================================")
    print(f"가장 유력한 원인: {analysis_result.get('primary_reason')}")
    print("\n[원인별 확률]")
    probs = analysis_result.get("probabilities", {})
    for cause, prob in probs.items():
        print(f" - {cause.upper()}: {prob * 100:.1f}%")
    
    print("\n[추론 근거 상세]")
    print(analysis_result.get("reasoning_details"))

    print("\n[권장 행동 지침 (우선순위순)]")
    for action in analysis_result.get("care_actions", []):
        print(f" {action.get('priority')}. {action.get('title')}")
        print(f"    - 설명: {action.get('description')}")

    print("\n[의학적 주의 및 경고 사항]")
    print(analysis_result.get("warning_or_red_flags"))
    print("==================================================")

    # 7. output.log에 분석 이력 누적
    log_file_path = "output.log"
    print(f"\n[Log] 분석 로그를 '{log_file_path}'에 기록 및 누적합니다.")
    
    log_entry = {
        "timestamp": timestamp,
        "video_file": video_path,
        "parent_context": context,
        "video_observation": video_obs,
        "audio_observation": audio_obs,
        "calculated_scores": scores,
        "comprehensive_analysis": analysis_result
    }

    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"=== ANALYSIS RUN AT {timestamp} FOR {video_path} ===\n")
        log_file.write(json.dumps(log_entry, indent=2, ensure_ascii=False))
        log_file.write("\n======================================================================\n\n")

    print("[Main] 모든 프로세스가 정상적으로 완료되었습니다.")

if __name__ == "__main__":
    main()
