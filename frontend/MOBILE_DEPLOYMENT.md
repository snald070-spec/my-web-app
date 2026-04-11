# Mobile Deployment (Prototype -> Play Store Ready)

This project supports an installable mobile flow with Capacitor.

## 0) Configure API URL for mobile

Create `frontend/.env` from `frontend/.env.example` and set `VITE_API_BASE_URL`.

Examples:
- Android emulator (debug only): `VITE_API_BASE_URL=http://10.0.2.2:8000`
- Real device in local QA (debug only): `VITE_API_BASE_URL=http://YOUR_PC_LAN_IP:8000`
- Production/Play release: `VITE_API_BASE_URL=https://api.your-domain.com`

Important:
- Run backend with host open to LAN when testing on a real device.
- Backend CORS already includes Capacitor origins.
- Production build requires HTTPS API endpoint.

## 1) Build and sync web assets into Android project

```bash
cd frontend
npm run mobile:build
```

What it does:
- Builds React app into `dist`
- Syncs the built assets into `android/app/src/main/assets/public`

## 2) Open Android Studio

```bash
npm run mobile:open
```

Then in Android Studio:
- Let Gradle sync complete
- Select a device or emulator
- Run app for testing

## 3) Create release artifact

In Android Studio:
- Build > Generate Signed Bundle / APK
- Choose either:
  - Android App Bundle (`.aab`) for Play Console
  - APK for internal distribution

CLI alternative:

```bash
cd frontend/android
./gradlew :app:bundleRelease
```

Windows PowerShell:

```powershell
cd frontend/android
.\gradlew.bat :app:bundleRelease
```

This project is configured to sign release artifacts from:
- `frontend/android/keystore.properties`
- `frontend/android/app/upload-keystore.jks`

Important:
- Keep `upload-keystore.jks` and the passwords in `keystore.properties` backed up securely.
- If you lose this upload key, future Play updates are blocked until key reset process is completed.

If build fails with JAVA_HOME message:
- Install JDK 17 (recommended for Android toolchain)
- Set `JAVA_HOME` to JDK install path
- Re-open terminal and run build again

If build fails with SDK location not found:
- Install Android SDK (Android Studio > SDK Manager)
- Create `frontend/android/local.properties` with:

```properties
sdk.dir=C:\\Users\\<YOUR_USER>\\AppData\\Local\\Android\\Sdk
```
- Re-run `:app:bundleRelease`

## 4) Security baseline checklist (Play release)

- [ ] Release build is signed with upload key (not debug keystore)
- [ ] `minifyEnabled=true`, `shrinkResources=true` enabled for release
- [ ] `android:allowBackup="false"` configured
- [ ] `android:dataExtractionRules` configured to exclude app data
- [ ] `android:usesCleartextTraffic="false"` in main manifest
- [ ] Debug-only cleartext exceptions limited to localhost/10.0.2.2
- [ ] API endpoint for production uses HTTPS only
- [ ] WebView debugging is disabled for release build
- [ ] No hardcoded secrets in source, `.env`, or assets
- [ ] `google-services.json` or other credential files are not accidentally leaked

## 5) Play Console policy checklist

- [ ] Privacy Policy URL prepared and publicly accessible
- [ ] Data safety form completed (collection, sharing, retention)
- [ ] Target API level meets current Play requirement
- [ ] App signing by Google Play enabled (recommended)
- [ ] Account deletion flow/policy prepared if account creation exists
- [ ] Export compliance and content rating completed

## 6) QA validation checklist

- Install and launch from home screen icon
- Login and role-based screen transitions work
- Network calls to backend API are reachable from device network
- Offline fallback does not break login state
- Temporary password and user-management flows work on touch UI
- Session expiry/401 flow logs user out correctly
- First-login password change policy is enforced

## Notes

- For production release, keep debug-only endpoints and debug network config out of release package.
- PWA and Capacitor can coexist: PWA for fast web install tests, Capacitor for store/internal app packaging.
