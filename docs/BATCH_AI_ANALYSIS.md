# Batch AI Analysis - 批次 AI 分析工具

## 1. 設計理念

### 1.1 解決問題

在處理大量 Jira 問題時，工程師需要逐一分析每個問題的根因，這過程耗時且容易遺漏重要資訊。傳統方式需要：
- 手動打開每個 Jira 票據
- 閱讀問題描述、附件日誌
- 搜尋相關歷史問題
- 複製分析結果到 Jira Comment

### 1.2 設計目標

- **批次處理**：一次載入大量 Jira Issues，同時分析
- **自動化**：自動下載附件、解析壓縮檔、提取關鍵日誌
- **多 AI 支援**：支援 OpenAI、RTK LLM、DeepSeek 三種 AI 引擎
- **預覽後更新**：先預覽 AI 分析結果，確認後再寫入 Jira
- **靈活輸入**：支援 Saved Filter ID、JQL 查詢或單一 Jira Key
- **多模組掃描**：掃描 54+ 個錯誤模組，自動匹配根因規則 (需額外下載)

### 1.3 準確度說明

> **注意**：啟用多模組錯誤模式掃描會增加分析時間，但大幅提升準確率

| 模式 | 分析速度 | 準確率 | 說明 |
|------|----------|--------|------|
| 快速模式 | 快 | 中 | 只篩選 error/warning/exception 關鍵字 |
| 多模組掃描 | 慢 | 高 | 掃描 54+ 模組的 2600+ 條規則，自動匹配 Owner、Priority |

**為什麼多模組掃描更準確？**
- 每個錯誤會對應到正確的 Module 和 Owner
- 可取得該問題的 Priority 等級
- 自動擷取 ±20 行上下文給 AI 分析
- 可看到 Rule 的 Comment 說明

### 1.4 核心功能

| 功能 | 說明 |
|------|------|
| 問題載入 | 從 Jira Filter 或 JQL 批量載入問題 |
| 附件分析 | 自動下載 .txt, .log, .zip, .tar, .tgz 等檔案，保留資料夾結構 |
| AI 分析 | 支援三種 AI 工具，產出根因分析報告 |
| 結果預覽 | 在 UI 展開查看完整分析內容，支援全頁檢視 |
| 批量更新 | 勾選後批量寫入 Jira Comment |
| 模式篩選 | 可限定只比對 Android_TV_General.json 規則 |
| 分析優先級 | logcat/bugreport 為主，rtd_xx log 為輔，同資料夾文件相關聯 |

---

## 2. 安裝指南

### 2.1 環境需求

- Python 3.8+
- PostgreSQL 15+ (需啟用 pgvector 擴展)
- 網路存取 Jira 伺服器

### 2.2 安裝步驟

```bash
# 1. 複製專案 (選擇一種方式)

# HTTPS (需要輸入 GitHub 帳號密碼)
git clone https://github.com/waynechang930/jira-insight.git
# 或 SSH (需要設定 SSH Key)
git clone git@github.com:waynechang930/jira-insight.git

cd jira-insight

# 2. 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. 安裝依賴
pip install -r requirements.txt

# 4. 設定環境變數
cp .env.example .env
# 編輯 .env 填入你的設定 (特別是 JIRA_COOKIE)

# 5. 初始化資料庫 (可選)
python init_db.py

# 6. 啟動服務
python app.py
```

### 2.3 環境變數 (.env)

```bash
# Database Config
DB_NAME=jira_db
DB_USER=jira_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Jira Config
JIRA_DOMAIN=https://your-jira-server.com/
JIRA_USER=your_username
JIRA_PASSWORD=your_password
JIRA_API_TOKEN=your_api_token
JIRA_JQL=project = YOUR_PROJECT AND status in (Resolved, Closed)

# 2FA Session Cookie (for Jira Cloud with 2FA enabled - see 2.4)
JIRA_COOKIES=<paste browser cookies here>

# AI Config
USE_RTK_LLM=Y
OPENAI_API_KEY=sk-xxxxx
RTK_LLM_API_KEY=your_rtk_key
DEEPSEEK_LLM_API_KEY=sk-xxxxx
SHOW_KEYWORD_COMPARE_STATUS=Y  # 顯示錯誤模式比對進度
```

### 2.4 Jira Cloud 2FA 認證設定

若 Jira 啟用 2FA，需使用瀏覽器 Cookie 來下載附件：

**最簡單取得 Cookie 的方法：**

1. **登入 Jira**（完成 2FA 驗證）
2. **打開開發者工具** (F12)
3. **切換到 Application 標籤**
4. **左側展開** Cookies > 點選你的 Jira 網域（如 `vendorjira.realtek.com`）
5. **點擊右側表格的任一列**（確保整個表格被選取）
6. **按 Ctrl + A 全選**，再 **Ctrl + C 複製**
7. **貼到 .env 檔案**（環境變數名稱必須是 `JIRA_COOKIE`，值直接貼上）：
   ```
   JIRA_COOKIE=CURRENTSERVER	JiraSoftware	vendorjira.realtek.com	/	Session	25		✓		Medium	
   DEVICEDETAILS	Mozilla/5.0 (Windows NT 10.0: Win64: x64) AppleWebKit/537.36...
   JSESSIONID	013EE3796D22B9CFA33A0CD347FA6220	vendorjira.realtek.com	/	Session	42	✓	✓		Medium	
   Jira_2FASessionVerified	l7CkfNkfMGZHFfZXNyByFA==	vendorjira.realtek.com	/	2026-04-27T04:26:15.332Z	47	✓		Medium	
   Jira_rememberMyLogin	k6vBTQ7vQfqeXtF5Y1Zx+NCQi53AdEymRBI00R34oi+EyXfhXTUXfSXUGcRx4er3hLL2/1QmeOtFyuJOGNxoUa+ReR/VG1ibOfKiArm+EXMnlJk6AaNhZazyYvbWTRmftB2r3opFhUEvja7qoGQ3HA==	vendorjira.realtek.com	/	2026-04-27T04:26:15.332Z	172	✓		Medium	
   atlassian.xsrf.token	BWBF-1PEU-O5AK-RBNK_3df6453e5279b3304454499602718364cb4853fd_lin	vendorjira.realtek.com	/	Session	84	✓	None		Medium	
   seraph.rememberme.cookie	117184%3A992dc63a7a747df9b9ca5735ee3849c4dbd90752	vendorjira.realtek.com	/	2026-04-27T04:26:02.985Z	73	✓	✓		Medium
   ```

   > ⚠️ **重點**：貼上後確保變數名稱是 `JIRA_COOKIE=`，值是從瀏覽器複製的整個表格內容

**程式會自動解析以下必要的 Cookie：**
- `Jira_2FASessionVerified`
- `atlassian.xsrf.token`
- `seraph.rememberme.cookie`
- `Jira_rememberMyLogin`

**注意**：
- Cookie 有期限，約 2 週後需重新取得
- 貼上後重啟 Flask 服務
- 建議使用 Chrome 瀏覽器複製 Cookie

### 2.5 下載錯誤模式檔案 (機密資料，內部專用)

> **⚠️ 重要**：此資料為內部機密，請勿上傳至公開 GitHub！

`errorlogpattern_keyword/` 目錄包含 54+ 模組的錯誤關鍵字規則，用於精準匹配問題根因。此資料夾已加入 `.gitignore`，不會同步到 GitHub。

**下載方式（需在公司內網）：**

```bash
# 方法 1: 使用 wget/curl 從 Gerrit 下載
# 訪問 https://mm2sd.rtkbf.com/gerrit/plugins/gitiles/realtek/errorlogpattern/+/refs/heads/realtek/master/
# 下載 keyword_tv006 目錄內容

# 方法 2: 直接從公司內網複製
# 從 \\file_server\shared\errorlogpattern_keyword\ 複製到專案目錄
```

**放置位置：**
```
jira-insight/
├── errorlogpattern_keyword/   ← 放在這裡
│   ├── bootcode.json
│   ├── Kernel.json
│   ├── vdec.json
│   └── ... (54+ 個模組)
├── app.py
├── templates/
└── ...
```

**驗證是否正確載入：**
啟動 app.py 後，分析日誌時會顯示：
```
[ErrorPattern] Loading 54 pattern files...
[ErrorPattern] Total patterns loaded: 2623
```

### 2.6 啟動服務

```bash
python app.py
```

服務啟動後，訪問：http://localhost:5000

---

## 3. 使用說明

### 3.1 介面總覽

系統提供三個主要標籤頁：

1. **Single Issue Analysis** - 單一問題分析
2. **Batch AI Analysis** - 批次 AI 分析
3. **Project Scan** - 專案掃描
   - 根據選定的 AI 工具自動選擇對應的 Embedding 模型
   - OpenAI → 雲端 Embedding API
   - RTK/DeepSeek → RTK Embedding API (embedding-chattek-qwen)
   - 掃描專案中所有未解決的問題
   - 與歷史資料庫比對，找出相似度 ≥80% 的歷史問題

### 3.2 Batch AI Analysis 操作流程

#### Step 1: 選擇 AI 工具與語言

- **AI Tool**: OpenAI / RTK LLM / DeepSeek (用於 AI 分析)
- **Output Language**: English / 繁體中文
- **Max File Size**: 篩選過大的附件（預設 50MB，可選 10/100/200/500MB 或無限制）

> **注意**：Embedding（向量搜尋）與 AI 分析使用不同的模型：
> - **AI 分析**：使用選定的 AI 工具 (OpenAI/RTK/DeepSeek) 進行複雜的根因分析
> - **向量搜尋**：
>   - OpenAI → 雲端 Embedding API (text-embedding-3-small)
>   - RTK/DeepSeek → RTK Embedding API (embedding-chattek-qwen)

#### Step 2: 輸入查詢條件

選擇輸入類型：
- **Saved Filter ID**: 輸入 Jira Filter ID (如 18907)
- **JQL Query**: 輸入自訂 JQL 條件
- **Jira Key**: 輸入單一 Jira 問題編號 (如 RK51FAN14-1522)

#### Step 3: 載入問題

點擊「Load Issues」按鈕，系統會從 Jira 載入符合條件的問題列表。

#### Step 4: 過濾與排序

- **Filter by Status**: 全部 / 已分析 / 未分析 / 已更新 / 未更新
- **Sort by**: 建立日期 (新→舊) / 建立日期 (舊→新) / Jira ID

#### Step 5: 設定分析選項

- **只比對 Android_TV_General.json**: 勾選後限定只使用 Android_TV_General.json 中的規則進行錯誤模式匹配
- **AI 分析優先級**: logcat/bugreport 為主、rtd_xx log 為輔、同資料夾文件視為相關聯

#### Step 6: 分析問題

- **個別分析**: 點擊每個問題右側的「分析」按鈕
- **批量分析**: 點擊「Analyze All」分析全部問題

系統會自動：
1. 取得 Jira 問題內容
2. 下載所有附件
3. 解析壓縮檔 (.zip, .tar, .tgz, .gz)，保留資料夾結構
4. 提取關鍵日誌 (Error, Warning, Exception)
5. 比對錯誤模式（支援 54+ 模組的 2600+ 規則）
6. 呼叫 AI 分析並產出報告

#### Step 7: 展開結果

點擊「展開」或「全頁檢視」按鈕查看完整的 AI 分析內容。
Pattern Match Summary 表格格式：Index | Pattern | Priority | Owner | Source File | Matched Content | Relevance

#### Step 8: 更新到 Jira

#### Step 6: 展開結果

點擊「展開」按鈕查看完整的 AI 分析內容。

#### Step 7: 更新到 Jira

1. 勾選要更新的問題 (或使用「Select All」)
2. 點擊「Update Selected」
3. 系統會將分析結果（含 Pattern Match Summary 表格與 AI 分析報告）以 Jira Wiki 格式寫入每個問題的 Comment

---

## 4. 功能詳解

### 4.1 附件處理

支援的檔案格式：
- 文字檔: `.txt`, `.log`
- 壓縮檔: `.zip`, `.tar`, `.tgz`, `.tar.gz`, `.gz`, `.rar`

**RAR 檔案支援** (需要安裝 unrar):
- 安裝命令: `sudo apt install unrar` (Linux) 或 `brew install unrar` (Mac)
- 未安裝時會跳過 RAR 檔案並顯示安裝提示

**智慧日誌提取**:
系統會自動過濾出包含以下關鍵字的日誌行：
- `error`, `exception`, `fail`, `warning`, `crash`, `stack`

**資料夾結構保留**:
壓縮檔解壓後的檔案會保留原始資料夾路徑（如 `folder1/folder2/file.txt`），而非僅使用檔名。同一資料夾內的檔案視為相關聯，避免跨資料夾拼湊分析。

### 4.2 AI 分析輸出格式

AI 分析報告包含：

1. **Root Cause Analysis** - 根因分析
2. **Key Error Logs** - 關鍵錯誤日誌 (含檔案來源)
3. **Suggested Fix** - 建議修復步驟

### 4.3 Jira Comment 格式

系統會自動將 Markdown 轉換為 Jira Wiki 格式：
- 標題 `#` → `h1.`
- 粗體 `**` → `*`
- 連結 `[text](url)` → `[text|url]`
- 程式碼塊 ``` → `{code}`

---

## 5. API 端點

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/batch_load_issues` | POST | 從 Filter/JQL 載入問題 |
| `/api/batch_analyze` | POST | AI 分析單一問題 |
| `/api/update_jira_comment` | POST | 更新分析結果到 Jira |

---

## 6. 常見問題

### Q1: 分析時出現認證錯誤

請確認 `.env` 中的 `JIRA_USER` 和 `JIRA_PASSWORD` 正確，且有權限存取指定的 Filter/JQL。

### Q2: 壓縮檔下載失敗

系統會檢查檔案魔數 (Magic Bytes) 確保檔案完整性。若檔案已損壞，會略過該檔案。

### Q3: AI 分析結果不理想

可以嘗試切換不同的 AI 工具 (OpenAI/RTK/DeepSeek)，或調整輸出語言。

### Q4: 如何大批量更新？

使用「Select All」勾選全部問題，一次點擊「Update Selected」即可批量寫入 Jira Comment。

### Q5: 附件下載出現 2FA / 認證錯誤

這是因為 Jira Cloud 啟用了兩步驟驗證 (2FA)。請參考章節 2.4 設定 Cookie：
1. 登入 Jira 完成 2FA 驗證
2. 用 Chrome DevTools 複製 Cookie
3. 貼到 .env 的 JIRA_COOKIE 欄位
4. 重啟 Flask

### Q6: Cookie 需要多久更新一次？

通常約 2 週。若發現附件下載失敗，請重新取得 Cookie。

---

## 7. Embedding 模型比較

### 7.1 嵌入式模型

| 模型 | 維度 | 速度 | 說明 |
|------|------|------|------|
| OpenAI (text-embedding-3-small) | 1536 | 快 | 雲端 API，需 API Key |
| RTK (embedding-chattek-qwen) | 2560→1536 | 快 | 內部 API，需 RTK_LLM_API_KEY |
| TF-IDF fallback | 1536 | 快 | 無 API Key 時的備用方案 |

**說明：**
- RTK Embedding 返回 2560 維，自動截斷為 1536 維以匹配資料庫
- RTK/DeepSeek 選擇時，自動使用 RTK Embedding API
- 如無 API Key，系統會使用 TF-IDF fallback（準確率較低）

---

## 8. 技術架構

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Web UI     │────▶│  Flask API  │────▶│  Jira API   │
│ (Bootstrap) │     │  (Python)   │     │  (REST)     │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  AI Service │
                    │ (OpenAI/    │
                    │  RTK/DeepSeek)│
                    └─────────────┘
```

---

## 8. 版本紀錄

### v1.1.0 (2026-04-14)
**Commit**: `bcd7f86` - Add multi-module error pattern matching for accurate root cause analysis

新增功能：
- 多模組錯誤模式掃描（54+ 模組，2600+ 規則）
- 自動匹配 Owner、Priority、Comment
- 顯示 ±20 行上下文
- 修正 Jira Wiki Markup 語法

### v1.2.0 (2026-04-15)
**Commit**: `b8c8397` - Fix: use correct embedding model based on AI tool selection

新增功能：
- 附件日期排序與篩選
- 可勾選特定日期進行分析
- 未勾選時自動分析最新2個日期的附件
- Token 數量檢查（196608上限）
- 顯示可讀的 Markdown 格式結果
- 已分析檔案標註綠色
- **分離 Embedding 與 AI 分析模型**：
  - AI 分析：使用選定的 AI 工具
  - 向量搜尋：OpenAI 用雲端 API，RTK/DeepSeek 用 RTK Embedding API
- Project Scan 根據選定的 AI 工具自動選擇對應的 Embedding

### v1.2.1 (2026-04-15)
**Commit**: (最新)

新增功能：
- RTK/DeepSeek 選擇時自動使用 RTK Embedding API (embedding-chattek-qwen)
- RTK Embedding 自動維度截斷 (2560→1536) 匹配資料庫
- 移除 sentence-transformers 依賴（改用 RTK API）
- Project Scan 使用正確的 Embedding 模型（從 Single Issue Analysis 選擇）

### v1.2.2 (2026-04-17)
**Commit**: `2338cdf`

新增功能：
- 新增單一 Jira Key 輸入功能，可直接輸入問題編號進行分析（如 RK51FAN14-1522）
- Input Type 下拉選單增加「Jira Key」選項

### v1.2.3 (2026-04-20)
**Commit**: `1a5decd`

新增功能：
- 錯誤模式比對進度顯示 (`SHOW_KEYWORD_COMPARE_STATUS` 環境變數)
- 檔案大小限制篩選器（預設 50MB，可選擇 10/100/200/500MB 或無限制）
- 自動 Token 截斷（維持 25k 上限，避免超過 30k TPM 限制）
- AI 分析結果增加信心指數（50%, 60%, 70%... 等百分比）
- AI 分析結果增加結構化摘要表格（Root Cause / Impact / Priority / Owner / Suggested Team）

### v1.2.4 (2026-04-21)
**Commit**: `342da83` - feat: improve analysis approach, pattern match table, and file folder tracking

新增功能：
- 分析優先級指令：logcat/bugreport 為主、rtd_xx log 為輔、同資料夾文件相關聯
- Pattern Match Summary 表格格式更新（7 欄：Index | Pattern | Priority | Owner | Source File | Matched Content | Relevance）
- 詳細模式資訊顯示：Keywords, Owner, Source, Comment, Log File, Matched Content
- 「只比對 Android_TV_General.json」勾選框：限定只使用 Android_TV_General.json 規則
- 壓縮檔保留資料夾結構（相對路徑追蹤）
- AI 報告 SUMMARY FORMAT 增加 Pattern Match Summary Table 要求
- 分析優先級（Relevance）：P1=高, P2=中, P3/P4=低

---
### v1.2.5 (2026-04-21)
**Commit**: (WIP) - Add RAR archive support for log extraction

新增功能：
- 支援 RAR 檔案解壓縮分析 (`.rar`)
- 新增 RAR magic bytes 驗證 (`Rar!\x1a\x07`)
- 需要安裝 `unrar` 系統工具：`sudo apt install unrar`
- 未安裝 unrar 時顯示安裝提示

---

## 9. 授權與感謝

本工具使用以下開源專案：
- Flask - Web Framework
- Bootstrap 5 - UI Framework
- Font Awesome - Icons
- OpenAI - GPT Models
- pgvector - 向量搜尋