# Changelog

## 0.3.1 - 2026-08-06

### Changed

- 已下載過的集數現在只做一次頁面請求就跳過，不再多打一次 stream API 索取用不到的簽章憑證。重跑整季抓新集數時，每個已存在的檔案省下一次請求與相應的主機間隔等待。
- 集數解析拆成兩階段（`episode_page` 解析頁面身分、`resolve_stream` 取得串流），`Anime1Extractor.episode()` 行為不變。

## 0.3.0 - 2026-08-06

### Added

- 支援 `anime1.pw` 單集、`?cat=` 分類頁與 slug 分類頁下載；此來源直接解析頁面 MP4 source，沿用現有 Range 續傳下載流程。
- 所有請求都會帶上與目標 URL 一致的 `Referer` / `Origin` / `Sec-Fetch-*`（依瀏覽器預設的 `strict-origin-when-cross-origin` referrer policy 推導）；CDN 影片請求以該集頁面為來源，修正 hotlink 保護直接回 403 的問題。
- 403 分類與自動復原：簽章憑證過期時會重新解析該集取得新憑證，並從 `.part` 既有位元組接續；被反機器人保護擋下時改為長時間退避，並回報可行動的訊息而非泛用錯誤。
- 隨機化請求節奏：worker 起跑錯開、每集之間隨機間隔、所有 worker 共用的單一主機最小請求間隔，以及帶 jitter 的重試退避。
- 遵守 `429`/`403` 回應的 `Retry-After` header（有上限保護）。
- 單一主機連續 403 熔斷器，跳脫後暫停所有 worker 冷卻。
- 新增 CLI 參數：`--no-pacing`、`--min-delay`、`--max-delay`、`--stagger-start`、`--host-interval`、`--resolve-attempts`、`--retry-budget`、`--circuit-breaker-threshold`、`--circuit-breaker-cooldown`。
- 公開 API 新增 `AccessDeniedError`，帶有 status code、回應 header 與 `bot_mitigation` 分類。
- 請求被拒時會記錄診斷資訊（狀態碼、`server`/`cf-ray` 等 header、是否帶 Referer 與 cookie 名稱），但不記錄任何簽章值。

### Changed

- `anime1.pw` 頁面解析改用 GET 抓取 HTML，避免依賴 WordPress / Cloudflare 對 POST 頁面請求的相容行為。
- direct video parser 會優先選擇 `video/mp4` source；若頁面提供多個 source 會記錄 warning。
- 重試退避由固定的指數改為 full jitter，避免可辨識的機械式重試節奏。
- `anicat --version` 改為讀取已安裝套件的 metadata，不再是寫死的字串，避免與 `pyproject.toml` 不同步（先前固定顯示 `0.1.0`）。

### Fixed

- 分類頁 HTML 無法解析出 episode link 時改為回報 `ParseError`，避免 selector 失效時 silent 回傳 0 集。
- 下載中發生的 `FetchError` 現在會被 downloader 的續傳重試路徑接住；先前因為 `FetchError` 不是 `requests.RequestException`，這條重試路徑對 client 端錯誤形同虛設。
- 403 不再以完全相同、且已被拒絕的請求盲目重試耗盡 retry 次數。

## 0.1.0 - 2026-05-24

### Added

- 採用 `src/` layout 與 `anicat` CLI entry point。
- 支援單集、季度、多 URL 下載。
- 支援併發下載、`.part` 續傳、原子寫入與安全檔名。
- 支援 Rich 多任務進度列、`--verbose/-v`、`--quiet/-q`。
- 支援 `-V/--version` 顯示 CLI 版本。
- 支援 `--connect-timeout` 分別控制連線與讀取逾時。
- 支援 stream 中斷後 Range retry，並使用 `If-Range` / `Content-Range` 保護 append 正確性。
- 支援 server 忽略 Range request 時重置單檔進度，不讓總進度倒退。
- 提供 typed Python API：`from anicat import AniCatService, DownloadOptions`。
- 新增 Anime1 integration smoke test scaffold，預設略過，手動以 `ANICAT_RUN_INTEGRATION=1` 啟用。

### Changed

- 以 Poetry 管理 package 與 dev tooling。
- 統一專案預設值與常數來源，降低 magic numbers。
- 併發下載改為每個 worker thread 重用一個 HTTP client/session，降低 connection pool 浪費。
- 強化 Anime1 `Set-Cookie` fallback parser，支援 comma-joined header 與 `expires` 內含逗號的情境。
- 移除 `lxml` 必要依賴，改用 BeautifulSoup 的標準 `html.parser` fallback，降低 Windows 安裝失敗機率。
- README 改為繁體中文產品導向文件。

### Quality

- 加入 Ruff format/check、Pyright standard、unittest、compileall、Poetry check。
- 加入 GitHub Actions Python 3.12 / 3.13 matrix 與 Poetry cache。
- 加入 pre-commit local hooks，與 CI 品質門檻保持一致。
