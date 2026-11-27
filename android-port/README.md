# 終極 LF2 Android 建置前置

Android 測試版以 OpenLF2 1.2.0（`6942db7`）為基底，目標為 `arm64-v8a`。取用已發布的 iOS 好友房版（`ultimate-lf2-ios-friend-rooms-45970422869-1`）中的共用腳本與遊戲資料，並加入相同的素材相容補丁與中繼主機名稱解析。

Android App 識別碼為 `io.github.retrogamehub.lf2ultimate.network`，可與原版 Android OpenLF2 並存。Android 啟動時使用 `--no-jit`，使連線識別計算的 JIT 設定與目前 iOS 版一致。Android 與 iOS 共用好友房及 Quick Match 所用的 Railway 入口。兩端實機互連仍需在 APK 產出後驗證。安裝器相關行為沿用 OpenLF2 的首次啟動流程。

前置工作由 GitHub Actions 編譯 Android ARM64 原生程式，並將共用素材、JNI 程式庫、SDL Java 和資源放入 Gradle 所需的目錄。它會上傳 Gradle 工程及其輸入檔的壓縮檔，並停在組裝 APK 前。

收到打包指示後，可在有 JDK 17、Android SDK 35 和 Gradle 8.13 的環境解開上述壓縮檔並執行下列命令。此步驟使用上游的測試簽章設定。

```sh
gradle --no-daemon -p android assembleDebug
```

產物路徑為 `android/app/build/outputs/apk/debug/app-debug.apk`。
