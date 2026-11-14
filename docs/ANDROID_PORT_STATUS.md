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

## Known blockers — all required before a parity release
1. Package and execute 16-KiB-compatible Android arm64 FFmpeg, including
   RTMP listen and push, FLV, H.264/HEVC bitstream filters, and network TLS.
2. Replace the desktop child-Python `--sei-proxy` launch with a managed
   Android-compatible proxy runtime, retaining frame signing, restart,
   cleanup, typed errors and both simultaneous dual-layout streams.
3. Implement Android Storage Access Framework file import for cookies and
   thumbnail selections; verify persistence and file URI permissions.
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
