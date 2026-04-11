# 최종장: 프로토타입 배포 및 설치 안내 (Android)

작성일: 2026-04-11

## 1) 배포 파일
- 주변인 직접 설치용 APK:
  - 경로: C:/Users/sksky/OneDrive/문서/draw_phase2_backend/frontend/android/app/build/outputs/apk/release/app-release.apk
  - 크기: 1,125,386 bytes
  - SHA256: 872747A8B03068A8BBAEA8481777E99BDF75DC0474FA9BD3BB69FB99E7BD87C7
- Play 업로드용 AAB:
  - 경로: C:/Users/sksky/OneDrive/문서/draw_phase2_backend/frontend/android/app/build/outputs/bundle/release/app-release.aab
  - 크기: 1,569,356 bytes
  - SHA256: C00E1A0FA6ADC8EC5BA5CF8FCBB5D2C7827933079CDC22041177AA06175732BB

## 2) 주변인 테스트 배포 방법 (APK)
1. app-release.apk 파일을 테스트 참여자에게 전달합니다.
2. 테스트 참여자 기기에서 파일을 열고 설치를 진행합니다.
3. 설치 차단 시 기기 설정에서 해당 경로의 설치 허용(알 수 없는 앱 설치 허용)을 켭니다.
4. 설치 후 로그인 계정으로 앱 실행을 확인합니다.

## 3) Play 내부 테스트 배포 방법 (AAB)
1. Play Console 내부 테스트 트랙에서 app-release.aab 업로드
2. 릴리즈 노트 입력
3. 심사용 계정 정보 입력
4. 데이터 세이프티/개인정보처리방침 URL 점검 후 게시

## 4) 설치 검증 체크리스트
- 앱 설치 성공
- 첫 실행 성공
- 로그인 성공
- 출석/리그/회비 화면 진입 성공
- 관리자 계정 기능(해당 시) 동작 확인

## 5) 파일 무결성 검증
배포받은 파일의 SHA256이 위 값과 일치하는지 확인하면 변조 여부를 점검할 수 있습니다.
