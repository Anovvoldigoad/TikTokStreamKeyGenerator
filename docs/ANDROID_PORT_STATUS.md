# Android APK port — verification status

Target branch: `port/android-qt-parity`. The Windows/Linux/macOS application
remains the behavioral reference. **No functional Android APK is claimed yet.**

## Preserved code
- Stream, account and device profile logic remain in the original Python code.
- Hosted signing continues to use RapidAPI. It is **not** an entitlement bypass.
- Chat, LIVE management, campaigns, violations, appeals and dual-layout
  code paths are unchanged, not yet validated on Android.
- App-private storage is used for cookie files, RapidAPI settings and logs;
  do not commit `cookies*.json`, `config.json` or signer secrets.
- The Android entrypoint uses API signing, never unpublished development code.
- The UI window minimum size and launch behavior are adapted for the handset.
- Qt-generated Buildozer configuration is patched to include the app's Python
  dependencies rather than the Qt/shiboken-only default.

## Known blockers — all required before a parity release
1. CI stages a Git-blob-pinned 16-KiB-compatible Android ARM64 FFmpeg ELF as
   libffmpeg_exec.so and configures Qt/Buildozer to package it. Verify the
   real APK installs/extracts the binary and can run RTMP listen/push on-device.
   ELF/ABI audit alone does not establish runtime compatibility.
2. The desktop child-Python relay now has an Android-managed thread path using
   the same SEI signer/injector. Offline stop tests are present; live FFmpeg
   subprocess lifecycle and simultaneous dual streams need device validation.
3. Android cookie/thumbnail selectors now use Qt's SAF content-URI-aware QFile
   then copy into private storage. Offline size/format tests PASS only if CI
   confirms; test real on-device picker URI access and persistence.
4. Check the Qt Fluent interface in portrait and landscape with the soft
   keyboard, font scaling and system back navigation.
5. Keep heartbeats, proxy and chat running through Android background/Doze
   lifecycle via an appropriate foreground service and notification.
6. Test login/import, device registration, signer's rate limits, account
   eligibility, room creation/resume/end, proxy SEI, client ingestion and
   dual-layout with a consenting, eligible account.
7. Verify CI produces a real APK and run it on Android 16 arm64, including
   installation, network requests, stream data, sleep/wake and LIVE teardown.

**Do not distribute an APK as functionally equivalent until every item above
is actually verified.** No Android permission, build artifact, or QR screen
alone establishes live-stream parity.
