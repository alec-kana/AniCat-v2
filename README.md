# AniCat-v2

> 穩定、快速、可續傳的 Anime1 命令列下載器。

AniCat-v2 是一個專注於 Anime1 下載體驗的 CLI 工具。它可以把單集、分類、季度或多個 URL 解析成乾淨的本機 MP4 檔案，並提供併發下載、`.part` 續傳、Rich 多任務進度列、串流中斷重試與安全檔名處理。


## 特色

- **支援單集與季度下載**：可輸入 `anime1.me` / `anime1.pw` 單集 URL、分類/季度 URL，也支援多 URL 批次下載。

- **依動畫名稱分資料夾**：透過分類/季度 URL 下載時，會從頁面的 `h1.page-title` 解析動畫名稱，並將該部動畫的集數下載到 `<輸出資料夾>/<動畫名稱>/` 底下，避免所有集數都堆在同一層。

- **併發下載**：用 `--concurrency` 控制同時下載數，整季下載更有效率。

- **Rich 多任務進度列**：顯示整體下載量、速度、完成集數，以及目前下載中的單檔進度。

- **預設支援續傳**：預設沿用 `.mp4.part` 暫存檔接續下載。

- **串流中斷重試**：使用 Range request 重新接續，並驗證 `Content-Range`。

- **支援來源**

    | 來源 | 單集 URL | 分類 / 季度 URL | 狀態 |
    |---|---|---|---|
    | `anime1.me` | `https://anime1.me/15651` | `https://anime1.me/category/...` | 支援 |
    | `anime1.pw` | `https://anime1.pw/349` | `https://anime1.pw/?cat=60`、`https://anime1.pw/<slug>` | 支援 |
    | `anime1.cc` | HLS / m3u8 | HLS / m3u8 | 尚未支援 |
    | `anime1.in` | HLS / m3u8 | HLS / m3u8 | 尚未支援 |


## 安裝方式

### A. GitHub Release 安裝（推薦）

```bash
python3 -m pip install "git+https://github.com/alec-kana/AniCat-v2.git@v0.2.0"
anicat --help
```

### B. 本機開發安裝

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

## 使用方法

```bash
anicat URL [URL ...] [OPTIONS]
```

### 範例

1. 單集下載：

    ```bash
    anicat https://anime1.me/12345
    ```

2. 分類 / 季度下載：

    ```bash
    anicat https://anime1.me/category/your-category-slug
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
| `-c`, `--concurrency N` | 併發下載數 | `3` |
| `--timeout SECONDS` | HTTP 讀取逾時秒數 | `30` |
| `--connect-timeout SECONDS` | HTTP 連線逾時秒數 | `10` |
| `--retries N` | HTTP 與串流中斷重試次數 | `3` |
| `--chunk-size BYTES` | 下載分塊大小 | `524288` |
| `--overwrite` | 覆寫已完成的同名檔案 | `False` |
| `--no-resume` | 不沿用既有 `.part` 暫存檔 | `False` |
| `--no-progress` | 關閉進度列 | `False` |
| `-v`, `--verbose` | 顯示診斷 log；`-vv` 顯示 HTTP retry/debug 細節 | `False` |
| `-q`, `--quiet` | 只保留錯誤等級 log，下載摘要仍會輸出 | `False` |
| `-V`, `--version` | 顯示版本後離開 | - |

完整參數：
```bash
anicat --help
```

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

### Exit Codes

| Code | 意義 |
|---|---|
| `0` | 全部下載成功，或目標檔案已存在而略過 |
| `1` | 至少一個 URL 失敗，或沒有找到任何集數 |
| `2` | CLI 使用方式或參數錯誤，例如沒有輸入 URL |

## 貢獻

歡迎任何形式的貢獻！請先閱讀 [CONTRIBUTING.md](CONTRIBUTING.md) 以了解專案規範與流程。

## License

本專案採用 GPL-3.0 License，詳見 [LICENSE](LICENSE) 文件。
