import os
import psycopg2
import openai
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# 1. System Settings & Environment Variables
# ==========================================
DB_DSN = f"dbname={os.getenv('DB_NAME')} user={os.getenv('DB_USER')} password={os.getenv('DB_PASSWORD')} host={os.getenv('DB_HOST')} port={os.getenv('DB_PORT')}"

# API Keys and Toggles
USE_RTK_LLM = os.getenv("USE_RTK_LLM", "N").upper()
RTK_LLM_API_KEY = os.getenv("RTK_LLM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ==========================================
# 2. AI Analysis Prompt (Fully English)
# ==========================================
GOOGLE_IMPROVEMENT_PROMPT = """
# Role Definition
You are a Senior Technical Product Manager and Android System Expert.
Your task is to review the following list of recent Jira issues from our database and identify items that "require Google's assistance to resolve, fix (bugs), or improve."

# Context
These issues may cover Google-related technologies such as Android OS, Framework, Google TV, GMS (Google Mobile Services), Chromecast, Widevine, etc.
Please strictly exclude pure internal App logic errors or third-party hardware issues unrelated to Google.
Look for characteristics like:
1. Involves Android OS, Framework, Google TV, GMS, Chromecast, Widevine, etc.
2. Shows low-level crashes, memory leaks, or Hardware Abstraction Layer (HAL) anomalies.
3. Engineers mention phrases implying "out of our hands," "waiting for upstream fix," or "system limitation" in the resolution/description.

# Input Data
<issues>
{issue_list}
</issues>

# Instructions
1. Filter & Categorize: Select issues from the list above that are clearly related to the Google system level or require a patch/API support from Google.
2. Priority Sorting: Categorize them into High, Medium, and Low priority based on severity (e.g., system crash, core UX impact, security issue).
3. Summarize & Output: Group similar types of issues together and output in Markdown format. **You MUST strictly sort them from Highest to Lowest priority.**

# Output Format
Please use the following Markdown format (Write the report entirely in English):

## 🔴 High Priority - Severely impacts UX or system stability
* **[Summarized Core Issue Name]**
  * **Related Jira IDs**: [List the Jira Keys]
  * **Issue Description & Impact**: [Brief description]
  * **Specific Request for Google**: [e.g., Need a bug fix in Android Framework, or expose a specific API]

## 🟡 Medium Priority - Functional anomaly but has a workaround or non-core feature
(Same format as above)

## 🟢 Low Priority - UI/UX tweaks or future feature requests
(Same format as above)

# Constraints
1. **CRITICAL: DO NOT repeat the same issue multiple times.** Every issue must be listed exactly ONCE.
2. Group identical or highly similar issues together under a single bullet point by combining their Jira IDs.
3. If you have no more unique issues to list, stop generating immediately.

---
If there are absolutely no issues requiring Google's assistance in the provided data, simply reply exactly with: "No system-level issues requiring Google's assistance were found in this batch."
"""

# ==========================================
# 3. Database Functions
# ==========================================
def get_db_connection():
    return psycopg2.connect(DB_DSN)

def fetch_recent_issues(limit=2000):
    print("[Step 2] Connecting to PostgreSQL database...")
    start_db_time = time.time()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print(f"[Step 3] Executing SQL query to fetch up to {limit} Google-related issues...")
        
        # PostgreSQL case-insensitive regex match (~*)
        sql = """
        SELECT jira_key, summary, resolution 
        FROM jira_issues 
        WHERE summary ~* 'google|framework|android|gms|chromecast|widevine|hal|os|system'
           OR resolution ~* 'google|framework|android|gms|chromecast|widevine|hal|os|system'
        ORDER BY id DESC 
        LIMIT %s;
        """
        
        cursor.execute(sql, (limit,))
        raw_results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        db_elapsed = time.time() - start_db_time
        print(f"         -> Database query completed in {db_elapsed:.2f} seconds.")
        print(f"         -> Fetched {len(raw_results)} raw records from DB.")
        
        # ---------------------------------------------------------
        # NEW: Deduplicate the results based on jira_key
        # ---------------------------------------------------------
        unique_issues = []
        seen_keys = set()
        
        for row in raw_results:
            jira_key = row[0]
            if jira_key not in seen_keys:
                unique_issues.append(row)
                seen_keys.add(jira_key)
                
        duplicates_removed = len(raw_results) - len(unique_issues)
        if duplicates_removed > 0:
            print(f"         -> [INFO] Removed {duplicates_removed} duplicate records.")
            
        return unique_issues
    
    except Exception as e:
        print(f"[ERROR] Database operation failed: {e}")
        return []

# ==========================================
# 4. Main Execution Logic
# ==========================================
def generate_report():
    overall_start_time = time.time()
    print("==================================================")
    print("[Step 1] Initializing process and checking environment variables...")
    
    # ---------------------------------------------------------
    # Setup LLM Client based on Environment Variables
    # ---------------------------------------------------------
    if USE_RTK_LLM == 'Y':
        if not RTK_LLM_API_KEY:
            print("[ERROR] RTK_LLM_API_KEY not found. Process aborted.")
            return
        print("         -> [INFO] Configured to use RTK Internal LLM API.")
        client = openai.OpenAI(
            base_url="https://devops.realtek.com/realgpt-api/openai-compatible/v1",
            api_key=RTK_LLM_API_KEY
        )
        target_model = "expert" #fast/medium/expert
    else:
        if not OPENAI_API_KEY:
            print("[ERROR] OPENAI_API_KEY not found. Process aborted.")
            return
        print("         -> [INFO] Configured to use standard OpenAI API.")
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        target_model = "gpt-4o"

    # Fetch data (De-duplicated)
    issues = fetch_recent_issues(limit=2000)
    
    if not issues:
        print("[WARNING] No related Jira issues found in database. Process aborted.")
        return

    print(f"         -> Successfully retrieved {len(issues)} UNIQUE records after filtering.")
    print("[Step 4] Processing issues in batches of 100 to prevent AI attention loss...")

    all_reports = []
    batch_size = 100
    
    for i in range(0, len(issues), batch_size):
        batch_issues = issues[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        print(f"\n         -> Formatting and analyzing Batch {batch_num} (Records {i+1} to {i+len(batch_issues)})...")
        
        issue_list_text = ""
        for row in batch_issues:
            jira_key = row[0]
            summary = row[1]
            resolution = row[2] if row[2] else "Unresolved"
            issue_list_text += f"- ID: {jira_key} | Summary: {summary} | Resolution: {resolution[:300]}\n"

        try:
            batch_start_time = time.time()
            print(f"            Streaming response from {target_model}...\n")
            print("-" * 50)
            
            # Send streaming request to LLM (with penalty parameters to avoid looping)
            stream = client.chat.completions.create(
                model=target_model, 
                messages=[
                    {"role": "system", "content": "You are a sharp Android OS system expert. DO NOT repeat the same content."},
                    {"role": "user", "content": GOOGLE_IMPROVEMENT_PROMPT.format(issue_list=issue_list_text)}
                ],
                temperature=0.4,       # Slightly increased to break loops
                frequency_penalty=1.2, # Penalize repeating exactly the same words
                presence_penalty=0.6,  # Encourage moving to new topics
                stream=True
            )
            
            batch_result = ""
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    print(content, end="", flush=True)
                    batch_result += content
            
            print("\n" + "-" * 50)
            
            batch_elapsed = time.time() - batch_start_time
            print(f"            [Batch {batch_num} Done in {batch_elapsed:.2f}s]")
            
            # Check if the AI found anything relevant in this batch
            if "No system-level issues requiring Google's assistance were found" not in batch_result:
                all_reports.append(f"### Findings from Batch {batch_num}:\n" + batch_result)
                
        except Exception as e:
            print(f"\n[ERROR] LLM API failed on batch {batch_num}: {e}")
            
        # Sleep to prevent hitting rate limits (TPM)
        if i + batch_size < len(issues):
            print("         ⏳ Sleeping for 5 seconds to respect API rate limits...")
            time.sleep(5)

    # Compile the final report
    print("\n[Step 5] Compiling final report...")
    output_filename = "google_improvement_report.md"
    
    with open(output_filename, "w", encoding="utf-8") as f:
        if all_reports:
            f.write("# Potential Improvements & Issues for Google Support\n\n")
            f.write("\n\n---\n\n".join(all_reports))
            print(f"[Step 6] Potential issues found! Report saved successfully to '{output_filename}'")
        else:
            f.write("After a strict batch scan of the recent records, no issues requiring Google's assistance or related to the underlying system were found.")
            print(f"[Step 6] Scan complete. No system-level issues requiring Google's assistance were found.")

    total_time = time.time() - overall_start_time
    print("==================================================")
    print(f"[SUCCESS] All tasks completed in {total_time:.2f} seconds.")

if __name__ == "__main__":
    generate_report()