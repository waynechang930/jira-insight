# 程式碼向量知識庫建設計畫

## 1. 總體架構

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              系統架構                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐ │
│  │   Code Base     │       │   離線建立工具    │       │   向量資料庫     │ │
│  │   (原始碼)       │──────▶│  (code_indexer)  │──────▶│   (pgvector)    │ │
│  └──────────────────┘       └──────────────────┘       └──────────────────┘ │
│           │                                                     │            │
│           │                        ┌──────────────────────────┘            │
│           │                        │                                         │
│           │                        ▼                                         │
│  ┌────────┴────────┐       ┌──────────────────┐       ┌──────────────────┐ │
│  │  第三頁: 搜尋   │◀──────│  Batch Analysis  │◀──────│  Jira Issue     │ │
│  │  程式碼建議    │       │  + Code Search   │       │                  │ │
│  └─────────────────┘       └──────────────────┘       └──────────────────┘ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 功能模組

### 2.1 離線程式碼建立工具 (`code_indexer.py`)

| 功能 | 說明 |
|------|------|
| **輸入** | 本地程式碼目錄路徑 |
| **掃描** | 遞迴掃描指定副檔名 (.c, .h, .cpp, .py, .java, .js, .go, .rs) |
| **萃取** | 提取變數定義、函式原型、struct、enum、#define、註解 |
| **向量化** | 使用 OpenAI API 產生 embedding |
| **儲存** | 存入 pgvector 資料庫 |
| **離線** | 可在無網路環境執行（需預先下載 embedding 模型） |

**萃取的程式碼單位：**

| 類型 | 範例 | 用途 |
|------|------|------|
| 變數定義 | `int g_video_mode;` | 搜尋全域變數 |
| 函式定義 | `void rtk_hdmi_init(void);` | 搜尋函式位置 |
| Struct 定義 | `struct rtk_hdmi_ops { ... };` | 搜尋資料結構 |
| Enum 定義 | `enum HDMI_STATE { ... };` | 搜尋狀態列舉 |
| #define | `#define HDMI_MAX_WIDTH 3840` | 搜尋巨集常數 |
| 註解 | `/* HDMI driver initialization */` | 搜尋說明文件 |

**資料表設計：**

```sql
CREATE TABLE code_embeddings (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(512),
    line_number INT,
    code_type VARCHAR(32),      -- variable, function, struct, enum, define, comment
    code_content TEXT,           -- 原始程式碼
    code_context TEXT,           -- 周圍 5 行上下文
    language VARCHAR(16),        -- c, python, java, etc.
    embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 建立向量索引 (HNSW)
CREATE INDEX code_embedding_idx ON code_embeddings
USING hnsw (embedding vector_cosine_ops);
```

---

### 2.2 搜尋 API (`app.py` 新增)

| Endpoint | Method | 說明 |
|----------|--------|------|
| `/api/code_search` | POST | 根據關鍵字搜尋程式碼 |
| `/api/code_indexer_status` | GET | 取得索引狀態 |

**Request:**
```json
{
    "query": "HDMI init error",
    "top_k": 10,
    "code_type": "function"  // optional filter
}
```

**Response:**
```json
{
    "results": [
        {
            "file_path": "drivers/video/rtk_hdmi.c",
            "line_number": 123,
            "code_type": "function",
            "code_content": "int rtk_hdmi_init(struct device *dev)",
            "code_context": "...",
            "similarity": 0.92
        }
    ]
}
```

---

### 2.3 第三頁：程式碼知識庫

| 功能 | 說明 |
|------|------|
| **搜尋_bar** | 輸入關鍵字搜尋程式碼 |
| **結果顯示** | 顯示檔案路徑、行號、程式碼內容、相似度 |
| **篩選器** | 按語言、類型（函式/變數/結構）篩選 |
| **連結** | 點擊開啟檔案或複製路徑 |

---

### 2.4 Batch Analysis 整合

**流程：**

```
1. 使用者分析 Jira Issue
       │
       ▼
2. AI 產生根因分析結果
       │
       ▼
3. 自動提取關鍵字（如 "HDMI init", "CMA memory"）
       │
       ▼
4. 搜尋程式碼知識庫
       │
       ▼
5. 回傳相關程式碼建議
       │
       ▼
6. 顯示在分析結果中
```

**在分析結果中呈現：**

```
=== 程式碼建議 ===

[1] HDMI 初始化函式
    檔案: drivers/video/rtk_hdmi.c:123
    程式碼: int rtk_hdmi_init(struct device *dev)
    相似度: 92%

    上下文:
    ```c
    int rtk_hdmi_init(struct device *dev)
    {
        struct rtk_hdmi_priv *priv;
        priv = devm_kzalloc(...);
        ...
    }
    ```
```

---

## 3. 暫存檔管理

| 方案 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| **A. 每次刪除** | 分析後刪除 `attachments/` | 節省空間 | 無法复看 |
| **B. 留存目錄** | 保留 `attachments/{issue_key}/` | 可复看 | 佔用空間 |
| **C. 存資料庫** | 將分析結果存入 DB | 方便搜尋 | 增加 DB 負擔 |

**建議：預設方案 A，可設定開關**

```python
# 環境變數控制
KEEP_ATTACHMENTS=False  # True = 留存
```

---

## 4. 實作順序

| 階段 | 順序 | 項目 | 預估天數 |
|------|------|------|----------|
| **Phase 1** | 1 | 離線程式碼建立工具 (`code_indexer.py`) | 1 |
| | 2 | 資料庫表設計與初始化 | 0.5 |
| **Phase 2** | 3 | 搜尋 API (`/api/code_search`) | 0.5 |
| | 4 | 第三頁 UI 搜尋介面 | 1 |
| **Phase 3** | 5 | Batch Analysis 整合自動建議 | 1 |
| | 6 | 暫存檔管理優化 | 0.5 |
| **Phase 4** | 7 | 測試與文件更新 | 1 |

**總預估：5.5 天**

---

## 5. 環境變數新增

```bash
# Code Indexer Config
CODE_BASE_PATH=/path/to/your/codebase
CODE_FILE_EXTENSIONS=.c,.h,.cpp,.py,.java

# Search Config
CODE_SEARCH_ENABLED=Y
CODE_SEARCH_TOP_K=10
```

---

## 6. 使用流程

### 6.1 離線建立知識庫（一次）

```bash
# 1. 設定環境變數
export CODE_BASE_PATH=/path/to/realtek/bootcode

# 2. 執行建立工具
python code_indexer.py

# 輸出:
# [CodeIndexer] Scanning /path/to/realtek/bootcode...
# [CodeIndexer] Found 15,234 code items
# [CodeIndexer] Generating embeddings: 100/15234...
# [CodeIndexer] Stored 15,234 embeddings to database
```

### 6.2 日常使用

```bash
# 1. 啟動服務
python app.py

# 2. 開啟網頁
#    - 第一頁：單一問題分析
#    - 第二頁：批次 AI 分析 (含程式碼建議)
#    - 第三頁：程式碼知識庫搜尋
```

---

## 7. 技術細節

### 7.1 程式碼萃取正則表達式

```python
# C/C++ 函式定義
function_pattern = r'^(?:static\s+)?(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{?'

# 變數定義
variable_pattern = r'^(?:static\s+)?(?:\w+\s+)+(\w+)\s*=\s*'

# #define
define_pattern = r'^#define\s+(\w+)\s+(.+)'

# struct/struct
struct_pattern = r'^struct\s+(\w+)\s*\{'
```

### 7.2 向量化優化

- 批次處理：每次 100 個項目
- 快取機制：已索引的檔案 Skip
- 並行處理：多執行緒下載

---

## 8. 預期效益

| 項目 | 效益 |
|------|------|
| **根因定位** | 快速找到相關程式碼位置 |
| **修改建議** | 參考類似問題的修改方式 |
| **知識傳遞** | 新人可快速了解系統架構 |
| **重複問題** | 統計高頻發生的程式碼模組 |