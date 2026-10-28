## Download

| Platform | File |
|---|---|
| **macOS — Apple Silicon** (M1/M2/M3/M4) | `NetWatcher-<version>-arm64.dmg` |
| **macOS — Intel** | `NetWatcher-<version>-x64.dmg` |
| **Windows 10/11** — installer | `NetWatcher-Setup-<version>.exe` |
| **Windows 10/11** — portable (no install) | `NetWatcher-<version>-windows-portable.zip` |

`SHA256SUMS.txt` lists the checksum of every file.

## First launch

Net Watcher is free and open source, so the builds are **not signed with a paid Apple / Microsoft certificate**.
Your system will warn you the first time — this is expected.

**macOS**
1. Open the DMG and drag **Net Watcher** into **Applications**.
2. Open it once. When macOS says it can't verify the developer, click **Done**.
3. Go to **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to Net Watcher, then confirm.

   *Alternative (Terminal):* `xattr -dr com.apple.quarantine "/Applications/Net Watcher.app"`

**Windows**
When SmartScreen shows "Windows protected your PC", click **More info → Run anyway**.

You only need to do this once. If you prefer, you can always [build it from source](https://github.com/niruvai/net-connection-monitor#quick-start-from-source).
