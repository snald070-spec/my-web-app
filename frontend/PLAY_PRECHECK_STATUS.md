# Play Precheck Status (2026-04-11)

## Automated checks (completed)
- [x] Release AAB exists
  - `frontend/android/app/build/outputs/bundle/release/app-release.aab`
- [x] AAB is signed with upload key alias `upload`
- [x] Signing config is wired in Gradle (`release` config active)
- [x] Manifest hardening is enabled
  - `allowBackup=false`
  - `usesCleartextTraffic=false` (main)
  - `dataExtractionRules` configured
- [x] Release obfuscation/resource shrinking enabled
  - `minifyEnabled=true`
  - `shrinkResources=true`
- [x] Runtime permissions declared in main manifest
  - INTERNET only

## Signing fingerprints (upload key)
- SHA1: 6C:C8:B1:6B:8C:2F:70:C5:7E:2B:F4:9D:E1:CD:14:9E:25:81:7F:F0
- SHA256: F4:DA:1F:52:3D:F7:63:17:54:6E:98:3D:D4:13:9D:3A:88:D2:0C:1B:0A:11:FA:60:13:1E:FC:D8:71:DF:CD:41

## Artifact hash
- app-release.aab SHA256
  - C00E1A0FA6ADC8EC5BA5CF8FCBB5D2C7827933079CDC22041177AA06175732BB

## Manual checks (Play Console)
- [ ] Privacy Policy URL 입력
- [ ] Data safety 항목 제출
- [ ] 앱 액세스/로그인 필요 여부 설명
- [ ] 콘텐츠 등급 설문
- [ ] 내부 테스트 트랙 업로드 및 테스터 지정

## Operational caution
- Keep these files backed up securely:
  - `frontend/android/keystore.properties`
  - `frontend/android/app/upload-keystore.jks`
- If upload key is lost, future app updates are blocked until key reset is approved by Play.
