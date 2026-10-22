# AniCat-v2

> 穩定、快速、可續傳的 Anime1 命令列下載器。

AniCat-v2 是一個專注於 Anime1 下載體驗的 CLI 工具。它可以把單集、分類、季度或多個 URL 解析成乾淨的本機 MP4 檔案，並提供併發下載、`.part` 續傳、Rich 多任務進度列、串流中斷重試與安全檔名處理。


## 特色

- **支援單集與季度下載**：可輸入 `anime1.me` / `anime1.pw` 單集 URL、分類/季度 URL，也支援多 URL 批次下載。

- **依動畫名稱分資料夾**：不論是分類/季度 URL 還是單集 URL，都會下載到 `<輸出資料夾>/<動畫名稱>/` 底下，避免所有集數都堆在同一層。分類/季度 URL 直接從頁面的 `h1.page-title` 解析動畫名稱；單集 URL 則會嘗試從頁面的「全集連結」找到所屬分類頁面再解析名稱，找不到該連結時退而使用該集標題（並去除結尾的集數方括號，例如 `Demo Anime [12]` -> `Demo Anime`）。

- **併發下載**：用 `--concurrency` 控制同時下載數，整季下載更有效率。

- **Rich 多任務進度列**：顯示整體下載量、速度、完成集數，以及目前下載中的單檔進度。

- **續傳與不殘留暫存檔**：同一次執行中，串流中斷或憑證過期都會從 `.mp4.part` 暫存檔接續。下載中斷（Ctrl-C、終止訊號）或失敗時，預設會停止所有下載、關閉檔案並刪除該集的 `.part`，不會留下佔用空間的暫存檔；需要跨次續傳時再加 `--keep-partial`。

- **重跑整季很便宜**：已下載完成的集數只會做一次頁面請求（用來得知檔名）就跳過，不會再去索取用不到的串流憑證。每週追新番時重跑同一個分類 URL 幾乎不會有額外等待。

- **串流中斷重試**：使用 Range request 重新接續，並驗證 `Content-Range`。

- **403 自動復原**：CDN 的簽章憑證（`e`/`p`/`h` cookie）過期而回 403 時，會自動重新解析該集取得新憑證，並從 `.part` 既有的位元組位置接續下載，而不是整集重來或直接失敗。

- **支援來源**

    | 來源 | 單集 URL | 分類 / 季度 URL | 狀態 |
    |---|---|---|---|
    | `anime1.me` | `https://anime1.me/15651` | `https://anime1.me/category/...` | 支援 |
    | `anime1.pw` | `https://anime1.pw/349` | `https://anime1.pw/?cat=60`、`https://anime1.pw/<slug>` | 支援 |
    | `anime1.cc` | HLS / m3u8 | HLS / m3u8 | 尚未支援 |
    | `anime1.in` | HLS / m3u8 | HLS / m3u8 | 尚未支援 |


## 安裝方式

### A. 從本 fork 安裝（推薦，需要 `git`）

```bash
python3 -m pip install "git+https://github.com/alec-kana/AniCat-v2.git@main"
anicat --help
```

### B. 手機 / 無 git 環境安裝（例如 iOS a-shell）

a-shell 等行動裝置終端機通常沒有內建 `git`，上面的 `git+https://...` 安裝方式會失敗。改用下載 tarball 的方式安裝即可：

```bash
python3 -m pip install https://github.com/alec-kana/AniCat-v2/archive/refs/heads/main.tar.gz
anicat --help
```

### C. 本機開發安裝

- 下載專案
    
    ```bash
    git clone https://github.com/alec-kana/AniCat-v2.git
    cd AniCat-v2
    ```

- 安裝套件

    ```bash
    # 使用 Poetry
    poetry install
    poetry run anicat --help

    # 使用一般 Python 環境
    python3 -m pip install .
    anicat --help
    ```

## 更新方式

依照原本使用的安裝方式挑選對應指令：

- **方式 A / B（跟隨 main 分支安裝）**：main 分支更新後版本號通常不會跟著變，單純重新執行安裝指令 pip 會判斷「已安裝相同版本」而略過，因此更新時務必加上 `--force-reinstall`（並建議加 `--no-cache-dir`，避免用到 pip 快取的舊內容）：

    ```bash
    # 方式 A（git+ 安裝）
    python3 -m pip install --upgrade --force-reinstall --no-cache-dir "git+https://github.com/alec-kana/AniCat-v2.git@main"

    # 方式 B（tarball 安裝）
    python3 -m pip install --upgrade --force-reinstall --no-cache-dir https://github.com/alec-kana/AniCat-v2/archive/refs/heads/main.tar.gz
    ```

- **方式 C（本機開發安裝）**：先拉取最新程式碼，再重新安裝：

    ```bash
    git pull
    poetry install          # 或：python3 -m pip install --upgrade --force-reinstall .
    ```

更新完成後可用 `anicat --version` 確認版本號。

## 使用方法

```bash
anicat URL [URL ...] [OPTIONS]
anicat search KEYWORD
```

### 範例

0. 先搜尋再下載（不必自己去網站找 URL）：

    ```bash
    anicat search 碧藍之海
    ```

    ```text
     Title                        Episodes · Season                   URL
     ─────────────────────────────────────────────────────────────────────────────────────
     GRAND BLUE 碧藍之海 第三季   連載中(07) · 2026 夏                https://anime1.me/?cat=1935
     GRAND BLUE 碧藍之海 第二季   1-12 · 2025 夏 · 悠哈璃羽           https://anime1.me/?cat=1708
     碧藍之海                     1-12 · 2018 夏 · 悠哈璃羽&西農YUI   https://anime1.me/?cat=388

    + 3 result(s)
    ```

    URL 欄位固定寬度，終端機再窄也不會被裁切，可以直接複製貼上。

    把印出的網址直接餵回 `anicat` 即可下載整季。

1. 單集下載：

    ```bash
    anicat https://anime1.me/12345
    ```

2. 分類 / 季度下載：

    ```bash
    anicat https://anime1.me/category/your-category-slug
    anicat https://anime1.me/?cat=1935
    anicat https://anime1.pw/your-category-slug
    ```

3. 多 URL 批次下載：

    ```bash
    anicat https://anime1.me/12345 https://anime1.me/67890
    anicat https://anime1.me/12345,https://anime1.me/67890
    ```

4. 只下載分類 / 季度中的部分集數：

    ```bash
    anicat https://anime1.me/category/your-category-slug --episodes 15-17
    anicat https://anime1.me/category/your-category-slug --episodes 1,3,5-8
    ```

### 常用參數

| 參數 | 說明 | 預設值 |
|---|---|---|
| `-o`, `--output DIR` | 指定輸出資料夾（每部動畫會依 `h1.page-title` 解析出的名稱各自建立子資料夾） | `./anime1` |
| `-e`, `--episodes SPEC` | 只下載分類/季度 URL 中指定的集數，例如 `15-17` 或 `1,3,5-8`；直接輸入的單集 URL 不受此篩選影響。若指定的集數在該分類找不到，會印出警告訊息 | 不限制 |
| `-c`, `--concurrency N` | 併發下載數。若某來源開始回 403，這是第一個該調低的參數 | `3` |
| `--no-pacing` | 一次關掉所有節奏延遲（會覆蓋下面四個參數）。最快，但也最像機器人 | `False` |
| `--timeout SECONDS` | HTTP 讀取逾時秒數 | `30` |
| `--connect-timeout SECONDS` | HTTP 連線逾時秒數 | `10` |
| `--retries N` | HTTP 與串流中斷重試次數 | `3` |
| `--chunk-size BYTES` | 下載分塊大小 | `524288` |
| `--min-delay SECONDS` | 同一個 worker 下載完一集後，抓下一集前的最短隨機等待 | `0.5` |
| `--max-delay SECONDS` | 同上的最長隨機等待 | `2` |
| `--stagger-start SECONDS` | 每個 worker 第一個請求前的最大隨機等待，避免整批同時開連線 | `2` |
| `--host-interval SECONDS` | 所有 worker 對同一主機的最小請求間隔 | `0.5` |
| `--resolve-attempts N` | 遇到 403 後重新解析該集、換取新簽章憑證的次數 | `3` |
| `--retry-budget SECONDS` | 單集全部復原嘗試的總時間上限 | `600` |
| `--circuit-breaker-threshold N` | 同一主機連續幾次 403 後暫停所有 worker，`0` 為關閉 | `5` |
| `--circuit-breaker-cooldown SECONDS` | 熔斷後的暫停時間 | `60` |
| `--overwrite` | 覆寫已完成的同名檔案 | `False` |
| `--no-resume` | 不沿用既有 `.part` 暫存檔 | `False` |
| `--keep-partial` | 保留中斷或失敗集數的 `.part` 暫存檔，下次執行可接續。預設會刪除，並一併清掉輸出資料夾內先前遺留的 `.part`（本次沒用到的動畫資料夾只清 30 分鐘以上未寫入的）。也可設定環境變數 `ANICAT_KEEP_PARTIAL=1` | `False` |
| `--no-progress` | 關閉進度列 | `False` |
| `--plain-progress` | 強制使用逐行純文字進度，取代 Rich 進度列（見下方 a-shell 說明） | `False` |
| `-v`, `--verbose` | 顯示診斷 log；`-vv` 顯示 HTTP retry/debug 細節 | `False` |
| `-q`, `--quiet` | 只保留錯誤等級 log，下載摘要仍會輸出 | `False` |
| `-V`, `--version` | 顯示版本後離開 | - |

完整參數：
```bash
anicat --help
anicat search --help
```

### `anicat search`

| 參數 | 說明 |
|---|---|
| `KEYWORD` | 比對動畫標題的子字串，不分大小寫，也不分簡體 / 繁體 |
| `-v`, `--verbose` | 顯示診斷 log |
| `-q`, `--quiet` | 只保留錯誤等級 log |

搜尋來源是 Anime1 的目錄索引 `animelist.json`，即時抓取不做快取。找不到相符項目時 exit code 為 `1`。

可以直接輸入簡體中文，例如 `anicat search 咒术回战` 會找到「咒術迴戰」。比對時關鍵字與標題都會先轉成同一種字體（OpenCC 詞庫），所以「裏 / 裡」、「回 / 迴」這類繁體異體字也能對上；結果仍以 Anime1 原本的繁體標題顯示。不過這只處理字體轉換，台灣譯名本身不同的作品（例如「间谍过家家」在 Anime1 是「間諜家家酒」）仍需用台灣譯名搜尋。

這和 Anime1 首頁表格的「搜尋」框不同：網站會把關鍵字以空白拆開、逐一比對標題、集數、年份、季節與字幕組欄位；`anicat search` 目前只比對標題中的連續子字串。

省略 `KEYWORD` 時會互動提問（與 `anicat` 省略 URL 時的行為一致）：

```text
$ anicat search
? Search keyword：碧藍之海
```

在管線或 CI 等非互動環境下不會卡住，直接以 exit code `2` 回報。

### 在 a-shell 等行動終端機上的進度顯示

Rich 的進度列只有在偵測到「可以就地更新畫面的終端機」時才會即時重繪；否則就會整段延後到下載全部結束才一次印出。AniCat-v2 會嘗試自動偵測並在偵測不到的情況下改用逐行印出的純文字進度。但部分手機終端機 App（例如 a-shell）會回報自己是相容的終端機，實際上卻不會即時重繪 Rich 的畫面，導致自動偵測誤判、畫面仍卡在初始的 `0/N` 不動，直到結束才整批輸出。

遇到這種情況，請直接加上 `--plain-progress` 強制使用純文字進度（不依賴終端機自動偵測），畫面就會在每個檔案開始下載，以及之後每隔約 1 秒印出一行進度：

```bash
anicat https://anime1.me/category/your-category-slug --plain-progress
```

如果不想看到任何進度輸出，可改用 `--no-progress` 關閉。

如果每次都要打 `--plain-progress` 太麻煩，可以改設定環境變數 `ANICAT_PLAIN_PROGRESS=1`，之後不加旗標也會預設開啟純文字進度：

```bash
export ANICAT_PLAIN_PROGRESS=1
anicat https://anime1.me/category/your-category-slug
```

a-shell 每次開新視窗都會自動執行 `~/Documents/.profile`（檔案不存在則略過，需自行建立），執行以下指令寫入一次即可長期生效，之後開新視窗都不用再手動打：

```bash
echo 'export ANICAT_PLAIN_PROGRESS=1' >> ~/Documents/.profile
```

### 遇到 403 下載失敗時

Anime1 的 CDN 會用兩種完全不同的機制回 403，AniCat-v2 會分開處理、也會在訊息裡分開講：

1. **簽章憑證過期**：影片網址帶的簽章 cookie 有時效，長片或慢速連線很容易在下載中途過期。這種情況會自動重新解析該集、換到新的憑證，再從已下載的位元組數接續，不需要任何處理。用 `--resolve-attempts` 調整嘗試次數。

2. **被反機器人保護擋下**：這時重試同一個請求沒有意義，訊息會直接寫 `blocked by anti-bot protection`。可以降低 `--concurrency`、把 `--min-delay` / `--max-delay` 調大，或稍後再試。若同一主機連續被擋，熔斷器會自動暫停所有 worker 一段時間，避免越撞越久。

避免同時併發的主要機制是 `--host-interval`（所有 worker 對同一主機的最小請求間隔），每集之間的 0.5~2 秒隨機等待只是額外打散節奏，因此刻意設得很短。每個 worker 開跑前也會隨機錯開最多 2 秒。整體額外成本大約是每集 2 秒。若你確定來源沒有限制、想要最快速度：

```bash
anicat https://anime1.me/category/your-category-slug --no-pacing
```

想知道 403 到底是哪一種，加 `-v` 會印出回應狀態與 `server` / `cf-ray` 等診斷 header，以及該請求有沒有帶 Referer 和 cookie（只印 cookie 名稱，不會印簽章內容）。

### 中斷下載與儲存空間

按下 Ctrl-C，或程式收到 `SIGTERM` / `SIGHUP` 時，AniCat-v2 會：

1. 不再開始任何排隊中的集數；
2. 讓正在下載的集數在下一個資料區塊後停止，關閉網路串流與 `.part` 檔案；
3. 等所有下載執行緒都結束後才把控制權交回終端機（再按一次 Ctrl-C 也會繼續等待收尾），並以 exit code `130` 結束；
4. 刪除未完成集數的 `.part`，最後印出刪除了幾個暫存檔、釋放多少空間。

這點在 a-shell 這類「Python 跑在 App 程序裡」的環境特別重要：以前中斷後，背景執行緒可能繼續寫入並一直開著檔案，即使在「檔案」App 刪掉影片，空間也要等 a-shell 完全關閉才會釋放。

若程式被強制結束（例如 iOS 在背景直接終止 a-shell），來不及收尾的 `.part` 會在下一次下載結束（或被中斷）時清掉，不必是同一部動畫：本次下載的資料夾會全部清除，輸出資料夾內其他動畫資料夾則清掉 30 分鐘以上未再寫入的 `.part`，避免誤刪另一個同時執行中的下載。想保留暫存檔、下次接續大檔案時，請加 `--keep-partial`。

## 進階說明

### Python API

除了 CLI，AniCat-v2 也提供 typed package API：

```python
from pathlib import Path

from anicat import AniCatService, DownloadOptions

options = DownloadOptions(output_dir=Path("./anime1"))
service = AniCatService(options)

episode_jobs = service.collect_episode_urls(["https://anime1.me/15651"])
reports = service.download_many(episode_jobs)
```

搜尋目錄索引：

```python
from anicat import Anime1Client
from anicat.catalog import fetch_catalog, search_catalog

with Anime1Client() as client:
    matches = search_catalog(fetch_catalog(client), "碧藍之海")

for entry in matches:
    print(entry.title, entry.url)
```

### Exit Codes

| Code | 意義 |
|---|---|
| `0` | 全部下載成功，或目標檔案已存在而略過 |
| `1` | 至少一個 URL 失敗、沒有找到任何集數，或搜尋沒有相符項目 |
| `2` | CLI 使用方式或參數錯誤，例如沒有輸入 URL |
| `130` | 下載被中斷（Ctrl-C、`SIGTERM` 或 `SIGHUP`），未完成的下載已停止並清除暫存檔 |

## 貢獻

歡迎任何形式的貢獻！請先閱讀 [CONTRIBUTING.md](CONTRIBUTING.md) 以了解專案規範與流程。

## License

本專案採用 GPL-3.0 License，詳見 [LICENSE](LICENSE) 文件。
