## Installation

### macOS

1. Download the **`-macos.zip`** file below, unzip it, and drag **ScenicSound Manager.app** into your Applications folder.
2. Install [VLC](https://www.videolan.org/) if you don't already have it — the app uses it for audio playback (it will prompt you with a download link if it's missing).
3. **First launch:** macOS will refuse to open the app because it isn't code-signed yet. Open **System Settings → Privacy & Security**, scroll down, and click **"Open Anyway"**, then confirm. You only have to do this once.
   - On macOS Sonoma (14) or earlier you can instead right-click the app and choose **Open**.

### Windows (beta)

1. Download the **`-windows.zip`** file below. Right-click it, choose **Extract All…**, then open the extracted **ScenicSound Manager** folder and run **ScenicSound Manager.exe**. Keep the `.exe` next to its `_internal` folder — to put the app somewhere else, move the whole **ScenicSound Manager** folder.
2. Install the **64-bit** version of [VLC](https://www.videolan.org/vlc/download-windows.html) if you don't already have it — the 32-bit version won't work with this app (it will prompt you with a download link if it can't find VLC).
3. **First launch:** Windows SmartScreen will warn that the app is unrecognized because it isn't code-signed yet. Click **More info**, then **Run anyway**. You only have to do this once.

**Upgrading from an older version?** Back up your library first (**File → Back Up Database…**) so you can roll back to the old version if anything goes wrong, then **quit the app** before replacing it (the app in Applications on macOS; the whole **ScenicSound Manager** folder on Windows). The app also snapshots your database automatically before upgrading its format, but your own backup is the sure thing.

## Feedback

Found a bug or have a suggestion? Please use the
[feedback form](https://forms.gle/QyTAhJCRd18NvHNn6) — takes a minute, no
account needed. (If you're a GitHub user, opening an issue works too.)

Or come chat: the [ScenicSound Manager Discord](https://discord.gg/xj8X4VBF4N)
is the place for questions, ideas, and beta discussion.

## Stream Deck plugin (optional)

Have an Elgato Stream Deck? The [ScenicSound Manager Stream Deck plugin](https://github.com/fzachman/SSMStreamdeckPlugin/releases) gives you physical buttons for scenes, playlists, and soundboard sounds. Grab the newest release from that page and make sure remote control is enabled in the app (Settings… → Enable remote control — on by default).
