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
- **靈活輸入**：支援 Saved Filter ID 或 JQL 查詢

### 1.3 核心功能

| 功能 | 說明 |
|------|------|
| 問題載入 | 從 Jira Filter 或 JQL 批量載入問題 |
| 附件分析 | 自動下載 .txt, .log, .zip, .tar, .tgz 等檔案 |
| AI 分析 | 支援三種 AI 工具，產出根因分析報告 |
| 結果預覽 | 在 UI 展開查看完整分析內容 |
| 批量更新 | 勾選後批量寫入 Jira Comment |

---

## 2. 安裝指南

### 2.1 環境需求

- Python 3.8+
- PostgreSQL 15+ (需啟用 pgvector 擴展)
- 網路存取 Jira 伺服器

### 2.2 安裝步驟

```bash
# 1. 複製專案
git clone <repo-url>
cd Jira_Insight_claude_code

# 2. 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. 安裝依賴
pip install -r requirements.txt

# 4. 設定環境變數
cp .env.example .env
# 編輯 .env 填入你的設定

# 5. 初始化資料庫
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

# AI Config
USE_RTK_LLM=Y
OPENAI_API_KEY=sk-xxxxx
RTK_LLM_API_KEY=your_rtk_key
DEEPSEEK_LLM_API_KEY=sk-xxxxx
```

### 2.4 啟動服務

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

### 3.2 Batch AI Analysis 操作流程

#### Step 1: 選擇 AI 工具與語言

- **AI Tool**: OpenAI / RTK LLM / DeepSeek
- **Output Language**: English / 繁體中文

#### Step 2: 輸入查詢條件

選擇輸入類型：
- **Saved Filter ID**: 輸入 Jira Filter ID (如 18907)
- **JQL Query**: 輸入自訂 JQL 條件

#### Step 3: 載入問題

點擊「Load Issues」按鈕，系統會從 Jira 載入符合條件的問題列表。

#### Step 4: 過濾與排序

- **Filter by Status**: 全部 / 已分析 / 未分析 / 已更新 / 未更新
- **Sort by**: 建立日期 (新→舊) / 建立日期 (舊→新) / Jira ID

#### Step 5: 分析問題

- **個別分析**: 點擊每個問題右側的「分析」按鈕
- **批量分析**: 點擊「Analyze All」分析全部問題

系統會自動：
1. 取得 Jira 問題內容
2. 下載所有附件
3. 解析壓縮檔 (.zip, .tar, .tgz, .gz)
4. 提取關鍵日誌 (Error, Warning, Exception)
5. 呼叫 AI 分析並產出報告

#### Step 6: 展開結果

點擊「展開」按鈕查看完整的 AI 分析內容。

#### Step 7: 更新到 Jira

1. 勾選要更新的問題 (或使用「Select All」)
2. 點擊「Update Selected」
3. 系統會將分析結果以 Jira Wiki 格式寫入每個問題的 Comment

---

## 4. 功能詳解

### 4.1 附件處理

支援的檔案格式：
- 文字檔: `.txt`, `.log`
- 壓縮檔: `.zip`, `.tar`, `.tgz`, `.tar.gz`, `.gz`

**智慧日誌提取**:
系統會自動過濾出包含以下關鍵字的日誌行：
- `error`, `exception`, `fail`, `warning`, `crash`, `stack`

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

---

## 7. 技術架構

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

## 8. 授權與感謝

本工具使用以下開源專案：
- Flask - Web Framework
- Bootstrap 5 - UI Framework
- Font Awesome - Icons
- OpenAI - GPT Models
- pgvector - 向量搜尋