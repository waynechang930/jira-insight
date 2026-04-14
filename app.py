import os
import requests
import psycopg2
from pgvector.psycopg2 import register_vector
import openai
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
import markdown
import json
import zipfile
import tarfile
import io
import re
import shutil
import base64
import time
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

app = Flask(__name__)

# --- Configuration ---
# Database Connection String
DB_DSN = f"dbname={os.getenv('DB_NAME')} user={os.getenv('DB_USER')} password={os.getenv('DB_PASSWORD')} host={os.getenv('DB_HOST')} port={os.getenv('DB_PORT')}"

# Jira Configuration
# Ensure no trailing slash in base URL to avoid double slashes like //browse/...
JIRA_BASE_URL = os.getenv("JIRA_DOMAIN", "").rstrip('/')
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN") # Personal Access Token (PAT)

# System OpenAI Key (Used for embedding search if user doesn't provide one)
SYSTEM_OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# Additional LLM Config
RTK_LLM_API_KEY = os.getenv("RTK_LLM_API_KEY")
DEEPSEEK_LLM_API_KEY = os.getenv("DEEPSEEK_LLM_API_KEY")
USE_RTK_LLM = os.getenv("USE_RTK_LLM", "N").upper()

# Jira Basic Auth (for API calls - more reliable than Bearer token)
JIRA_USER = os.getenv("JIRA_USER", "")
JIRA_PASSWORD = os.getenv("JIRA_PASSWORD", "")  # Use password, not API token
JIRA_COOKIES_RAW = os.getenv("JIRA_COOKIES", os.getenv("JIRA_COOKIE", ""))  # Raw cookies from browser

# Extract needed cookies from raw string
def get_jira_cookies():
    """Parse cookies and return needed ones for attachment download"""
    if not JIRA_COOKIES_RAW:
        return ""

    needed = ['Jira_2FASessionVerified', 'atlassian.xsrf.token', 'seraph.rememberme.cookie', 'Jira_rememberMyLogin']

    # Parse cookie string - handle both formats:
    # 1. "key1=value1; key2=value2" (semicolon separated)
    # 2. Tab-separated format from Chrome DevTools
    cookies = {}

    # Try semicolon format first
    if ';' in JIRA_COOKIES_RAW and '\t' not in JIRA_COOKIES_RAW:
        for part in JIRA_COOKIES_RAW.split(';'):
            part = part.strip()
            if '=' in part:
                key, value = part.split('=', 1)
                cookies[key.strip()] = value.strip()
    else:
        # Tab-separated format (from Chrome DevTools export)
        lines = JIRA_COOKIES_RAW.strip().split('\n')
        for line in lines:
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[0].strip()
                value = parts[1].strip()
                if name:
                    cookies[name] = value

    # Build cookie header with needed cookies
    result = []
    for name in needed:
        if name in cookies:
            result.append(f"{name}={cookies[name]}")

    print(f"[Cookie] Parsed cookies: {result}")
    return "; ".join(result)

JIRA_COOKIES = ""  # Will be set by get_jira_cookies() at runtime

def get_jira_auth():
    """Get HTTPBasicAuth for Jira"""
    return HTTPBasicAuth(JIRA_USER, JIRA_PASSWORD)

# Attachment storage path
ATTACHMENTS_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attachments")

# Error log pattern keyword directory
ERROR_PATTERN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "errorlogpattern_keyword")

# Cache for loaded error patterns
_error_patterns_cache = None


def load_all_error_patterns():
    """Load all error patterns from JSON files in errorlogpattern_keyword directory"""
    global _error_patterns_cache
    if _error_patterns_cache is not None:
        return _error_patterns_cache

    patterns = []
    if not os.path.exists(ERROR_PATTERN_DIR):
        print(f"[ErrorPattern] Directory not found: {ERROR_PATTERN_DIR}")
        return patterns

    json_files = [f for f in os.listdir(ERROR_PATTERN_DIR) if f.endswith('.json')]
    print(f"[ErrorPattern] Loading {len(json_files)} pattern files...")

    for json_file in json_files:
        file_path = os.path.join(ERROR_PATTERN_DIR, json_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                module_name = json_file.replace('.json', '')
                for rule in rules:
                    rule['_source_file'] = module_name
                patterns.extend(rules)
                print(f"[ErrorPattern] Loaded {len(rules)} rules from {json_file}")
        except Exception as e:
            print(f"[ErrorPattern] Error loading {json_file}: {e}")

    _error_patterns_cache = patterns
    print(f"[ErrorPattern] Total patterns loaded: {len(patterns)}")
    return patterns


def scan_log_with_patterns(content, patterns, context_lines=20):
    """
    Scan log content against error patterns and return matching rules with context.

    Args:
        content: Full log content (string)
        patterns: List of error pattern rules from JSON
        context_lines: Number of lines before/after match to include (default 20)

    Returns:
        List of matches, each containing:
        - rule: The matched rule dict
        - matched_line: The line that matched
        - context: ±context_lines lines around the match
        - line_number: Line number where match was found
    """
    matches = []
    lines = content.split('\n')

    for rule in patterns:
        keywords = rule.get('Keywords', '')
        if not keywords:
            continue

        # Parse keywords - split by && for AND logic
        keyword_list = [k.strip() for k in keywords.split('&&') if k.strip()]

        if not keyword_list:
            continue

        # Search for all keywords (AND logic)
        for line_num, line in enumerate(lines, start=1):
            line_lower = line.lower()
            # Check if ALL keywords are present (case-insensitive)
            if all(kw.lower() in line_lower for kw in keyword_list):
                # Get context lines (±20 lines)
                start_idx = max(0, line_num - context_lines - 1)
                end_idx = min(len(lines), line_num + context_lines)

                context = '\n'.join(lines[start_idx:end_idx])

                matches.append({
                    'rule': rule,
                    'matched_line': line.strip(),
                    'context': context,
                    'line_number': line_num
                })

                # Only report first match per rule to avoid duplicates
                break

    return matches

# AI Analysis Prompt (English)
AI_ANALYSIS_PROMPT = """
# Role Definition
You are a Senior Technical Support Analyst and Expert Debugger. Your goal is to analyze a new issue reported by a customer and provide a solution based on similar historical resolved cases from the Jira system.

# Context
We have retrieved relevant historical Jira tickets that are semantically similar to the new issue. You must use these historical records to diagnose the new issue.

# Input Data
1. **New Issue Report**:
<new_issue>
{new_issue_content}
</new_issue>

2. **Historical Reference (Retrieved Context)**:
<history>
{retrieved_chunks}
</history>

# Instructions
Analyze the <new_issue> by comparing it with the <history>. Follow these steps:
1. **Correlation Analysis**: Identify which historical issue is most relevant to the new issue. Look for matching error logs, stack traces, component names, or problem descriptions.
2. **Root Cause Inference**: Based on the resolution of the historical issues, explain the likely root cause of the new issue.
3. **Solution Synthesis**: Provide a step-by-step solution or debugging guide.
4. **Patch Verification**: If the historical data contains a specific "Patch Link" or "Commit ID", you MUST include it. If no patch is mentioned, DO NOT invent one.

# Output Format
Please structure your response in the following Markdown format:

## Root Cause Analysis
[Explain the technical cause here.]

## Suggested Solutions
[Step-by-step guide to fix or debug the issue.]

## References
* **Most Relevant Jira ID**: [List the Issue Keys]
* **Key Patch/Commit**: [Link or Commit ID if available; otherwise write "None"]
* **Confidence Level**: [Low/Medium/High]

# Constraints
* Be concise and professional.
* If the historical context is irrelevant to the new issue, state clearly: "No similar cases found in the historical database."
* Do NOT hallucinate technical details or URLs. Only use information present in the <history>.
"""

def get_db_connection():
    """Establish connection to PostgreSQL and register vector type."""
    conn = psycopg2.connect(DB_DSN)
    register_vector(conn)
    return conn

def get_jira_content(issue_key):
    """
    Fetch target issue content from Jira API v2 (Data Center compatible).
    Returns a tuple: (Full Context String, Summary)
    """
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}"
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, auth=get_jira_auth(), timeout=10)
        if response.status_code == 200:
            data = response.json()
            fields = data.get('fields', {})
            summary = fields.get('summary', '')
            description = fields.get('description', '') or ''
            # Combine summary and description for context
            return f"Issue: {summary}. Description: {description[:2000]}", summary
        return None, None
    except Exception as e:
        print(f"Jira Connection Error: {e}")
        return None, None

def get_open_issues_by_project(project_key, limit=50):
    """
    Fetch unresolved issues from a specific project.
    First verifies the project exists, then searches with fallback JQL.
    """
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    headers = {"Content-Type": "application/json"}
    auth = get_jira_auth()

    # First, verify the project exists
    project_url = f"{JIRA_BASE_URL}/rest/api/2/project/{project_key}"
    try:
        proj_response = requests.get(project_url, headers=headers, auth=auth, timeout=10)
        if proj_response.status_code != 200:
            print(f"[ProjectScan] Project '{project_key}' validation failed: {proj_response.status_code}")
            return None  # Return None to indicate project not found
        print(f"[ProjectScan] Project '{project_key}' validated successfully")
    except Exception as e:
        print(f"[ProjectScan] Connection error validating project: {e}")
        return None

    # JQL: Exclude all resolved/closed/done statuses
    jql = f'project = "{project_key}" AND status NOT IN ("Done", "Resolved", "Closed", "Fixed") ORDER BY created DESC'

    params = {
        "jql": jql,
        "maxResults": limit,
        "fields": "summary,description,status"
    }

    try:
        response = requests.get(url, headers=headers, params=params, auth=auth, timeout=30)
        if response.status_code == 200:
            issues = response.json().get('issues', [])
            print(f"[ProjectScan] Found {len(issues)} open issues for project '{project_key}'")
            return issues
        print(f"[ProjectScan] Search failed: {response.status_code} {response.text}")
        return []
    except Exception as e:
        print(f"[ProjectScan] Search connection error: {e}")
        return []

def generate_embedding(text, api_key):
    """Generate embedding vector using OpenAI."""
    client = openai.OpenAI(api_key=api_key)
    text = text.replace("\n", " ")
    if not text or not text.strip():
        return [0.0] * 1536 
    return client.embeddings.create(input=[text], model="text-embedding-3-small").data[0].embedding

def search_db(query_vector, exclude_key, top_k=5):
    """Search the vector database for similar issues."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = """
    SELECT jira_key, summary, resolution, metadata, 1 - (embedding <=> %s::vector) as similarity
    FROM jira_issues
    WHERE jira_key != %s
    ORDER BY similarity DESC
    LIMIT %s;
    """
    cursor.execute(sql, (query_vector, exclude_key, top_k))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

# NOTE: Removed 'analyze_issue_with_history' as it was used for batch analysis. 
# We will use api_analyze for on-demand analysis.

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html', jira_base_url=JIRA_BASE_URL)

@app.route('/api/search', methods=['POST'])
def api_search():
    """Handle the 'Compare Analysis' request (Single Issue)."""
    data = request.json
    jira_id = data.get('jira_id')
    
    if not jira_id:
        return jsonify({"error": "Jira ID is required"}), 400

    issue_text, issue_summary = get_jira_content(jira_id)
    if not issue_text:
        return jsonify({"error": "Jira Issue not found or connection failed"}), 404

    try:
        vector = generate_embedding(issue_text, SYSTEM_OPENAI_KEY)
    except Exception as e:
        return jsonify({"error": f"Failed to generate embedding: {str(e)}"}), 500

    results = search_db(vector, jira_id)
    
    formatted_results = []
    for row in results:
        jira_key = row[0]
        summary = row[1]
        resolution = row[2] if row[2] else "N/A"
        score = row[4]
        
        formatted_results.append({
            "key": jira_key,
            "summary": summary,
            "resolution": resolution[:200] + "..." if len(resolution) > 200 else resolution,
            "score": round(score * 100, 2),
            "link": f"{JIRA_BASE_URL}/browse/{jira_key}"
        })
        
    return jsonify({
        "target_summary": issue_summary,
        "results": formatted_results
    })

@app.route('/api/scan_project', methods=['POST'])
def api_scan_project():
    """
    Handle 'Project Scan': Find unresolved issues, match with history (Similarity >= 80%).
    DOES NOT perform AI Analysis automatically.
    """
    data = request.json
    project_key = data.get('project_key')
    
    if not project_key:
        return jsonify({"error": "Project Key is required"}), 400

    open_issues = get_open_issues_by_project(project_key, limit=100)

    # Check if project exists
    if open_issues is None:
        return jsonify({"error": f"Project '{project_key}' does not exist or is not accessible"}), 400

    if not open_issues:
        return jsonify({"message": "No unresolved issues found or Jira connection failed.", "matches": []})

    matched_results = []

    try:
        for issue in open_issues:
            key = issue['key']
            fields = issue['fields']
            summary = fields.get('summary', '')
            description = fields.get('description', '') or ''
            
            issue_text = f"Issue: {summary}. Description: {description[:1000]}"
            
            # Generate Embedding
            vector = generate_embedding(issue_text, SYSTEM_OPENAI_KEY)
            
            # Search DB (Top 1 match is enough for screening)
            db_results = search_db(vector, key, top_k=1)
            
            if db_results:
                top_match = db_results[0]
                similarity = top_match[4] 
                
                # FILTER: Score >= 80% (0.8)
                if similarity >= 0.80:
                    matched_results.append({
                        "open_issue_key": key,
                        "open_issue_summary": summary,
                        "open_issue_link": f"{JIRA_BASE_URL}/browse/{key}",
                        "match_key": top_match[0],
                        "match_summary": top_match[1],
                        "match_score": round(similarity * 100, 2),
                        "match_link": f"{JIRA_BASE_URL}/browse/{top_match[0]}"
                    })
                    
    except Exception as e:
        print(f"Error during project scan: {e}")
        return jsonify({"error": f"Scan failed: {str(e)}"}), 500

    return jsonify({
        "project": project_key,
        "scanned_count": len(open_issues),
        "matches": matched_results
    })

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """
    Handle the 'AI Analysis' request.
    Now supports analyzing a specific historical match if provided in payload.
    """
    data = request.json
    jira_id = data.get('jira_id')
    ai_tool = data.get('ai_tool', 'openai')  # openai, rtk, deepseek

    # 1. Fetch content
    issue_text, _ = get_jira_content(jira_id)
    if not issue_text:
        return jsonify({"error": "Jira Issue not found"}), 404

    # 2. Generate Embedding (always use OpenAI for embedding)
    vector = generate_embedding(issue_text, SYSTEM_OPENAI_KEY)

    # 3. Get Top 3 Context
    results = search_db(vector, jira_id, top_k=3)

    # 4. Build Context String for LLM
    retrieved_chunks = ""
    for row in results:
        key = row[0]
        summary = row[1]
        resolution = row[2]
        meta = row[3]
        patch_info = f"Patch: {meta.get('patch_link', 'None')}" if meta else ""

        retrieved_chunks += f"--- Historical Issue: {key} ---\nSummary: {summary}\nResolution: {resolution}\n{patch_info}\n\n"

    # 5. Call LLM with selected tool
    try:
        ai_result = call_ai_with_tool(
            AI_ANALYSIS_PROMPT.format(
                new_issue_content=issue_text,
                retrieved_chunks=retrieved_chunks
            ),
            ai_tool
        )
        html_content = markdown.markdown(ai_result)

        return jsonify({"ai_result": html_content})

    except Exception as e:
        return jsonify({"error": f"AI Analysis Failed: {str(e)}"}), 500

# ========== Batch Analysis APIs ==========

@app.route('/api/batch_load_issues', methods=['POST'])
def api_batch_load_issues():
    """Load issues from Jira Filter or JQL"""
    data = request.json
    issue_type = data.get('type')  # 'filter' or 'jql'
    filter_id = data.get('filter_id')
    jql = data.get('jql')

    if issue_type == 'filter' and not filter_id:
        return jsonify({"error": "Filter ID is required"}), 400
    if issue_type == 'jql' and not jql:
        return jsonify({"error": "JQL is required"}), 400

    # Build JQL
    if issue_type == 'filter':
        search_jql = f"filter={filter_id}"
    else:
        search_jql = jql

    # Fetch issues from Jira
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    headers = {"Content-Type": "application/json"}
    params = {
        "jql": search_jql,
        "maxResults": 100,
        "fields": "summary,description,status,attachment,created"
    }

    try:
        response = requests.get(url, headers=headers, auth=get_jira_auth(), params=params, timeout=30)
        print(f"Jira API Response - Status: {response.status_code}")
        print(f"Response Text: {response.text[:500] if response.text else 'Empty'}")
        if response.status_code != 200:
            return jsonify({"error": f"Jira API error: {response.status_code} - {response.text[:200]}"}), 500

        if not response.text or not response.text.strip():
            return jsonify({"error": "Empty response from Jira API"}), 500

        issues_data = response.json().get('issues', [])
        issues = []

        for issue in issues_data:
            fields = issue.get('fields', {})
            # Get attachments info
            attachments = fields.get('attachment', [])
            attachment_list = []
            for att in attachments:
                attachment_list.append({
                    "id": att.get('id'),
                    "filename": att.get('filename'),
                    "size": att.get('size'),
                    "mimeType": att.get('mimeType'),
                    "content": att.get('content')  # Download URL
                })

            issues.append({
                "key": issue.get('key'),
                "summary": fields.get('summary', ''),
                "description": fields.get('description', '') or '',
                "status": fields.get('status', {}).get('name', 'Unknown'),
                "created": fields.get('created', ''),
                "link": f"{JIRA_BASE_URL}/browse/{issue.get('key')}",
                "attachments": attachment_list
            })

        return jsonify({"issues": issues})

    except Exception as e:
        return jsonify({"error": f"Failed to load issues: {str(e)}"}), 500


@app.route('/api/batch_get_attachment_dates', methods=['POST'])
def api_batch_get_attachment_dates():
    """Get unique attachment dates for an issue"""
    data = request.json
    issue_key = data.get('issue_key')

    if not issue_key:
        return jsonify({"error": "Issue key is required"}), 400

    try:
        # Get attachment info with dates
        attachments = get_attachments_info(issue_key)

        # Group by date and count
        date_counts = {}
        for att in attachments:
            d = att.get('date', '')
            if d:
                date_counts[d] = date_counts.get(d, 0) + 1

        # Convert to list with count and sorted by date descending
        dates_list = [{'date': d, 'count': c} for d, c in date_counts.items()]
        dates_list.sort(key=lambda x: x['date'], reverse=True)

        return jsonify({
            'dates': dates_list,
            'total_attachments': len(attachments)
        })
    except Exception as e:
        return jsonify({"error": f"Failed to get attachment dates: {str(e)}"}), 500


def count_tokens(text):
    """Estimate token count (rough approximation: ~4 chars per token)"""
    return len(text) // 4


@app.route('/api/batch_analyze', methods=['POST'])
def api_batch_analyze():
    """Analyze a single issue with attachments using AI"""
    data = request.json
    issue_key = data.get('issue_key')
    ai_tool = data.get('ai_tool', 'openai')  # openai, rtk, deepseek
    output_language = data.get('output_language', 'en')  # en or zh
    selected_dates = data.get('selected_dates', None)  # List of dates to analyze

    if not issue_key:
        return jsonify({"error": "Issue key is required"}), 400

    # Get issue details
    issue_text, _ = get_jira_content(issue_key)
    if not issue_text:
        return jsonify({"error": "Failed to fetch issue from Jira"}), 404

    # Download and analyze attachments (with date filter)
    attachment_texts, analyzed_dates, analyzed_files = download_and_analyze_attachments(issue_key, selected_dates)

    # Load error patterns from JSON files
    error_patterns = load_all_error_patterns()

    # Build analysis prompt with pattern matching results
    attachment_content = ""
    pattern_matches_summary = []

    if attachment_texts and error_patterns:
        attachment_content = "\n\n=== ATTACHMENT ANALYSIS (Error Pattern Matching) ===\n"

        for att_name, att_text in attachment_texts:
            # Scan log against all error patterns
            matches = scan_log_with_patterns(att_text, error_patterns, context_lines=20)

            if matches:
                attachment_content += f"\n--- File: {att_name} ---\n"

                for match in matches:
                    rule = match['rule']
                    matched_line = match['matched_line']
                    context = match['context']
                    line_num = match['line_number']

                    # Format matched rule info
                    source_file = rule.get('_source_file', 'Unknown')
                    rule_info = f"""
### [Rule #{rule.get('Index', '?')}] {rule.get('Module', 'Unknown')} - 来源: {source_file}.json
- **Keywords**: {rule.get('Keywords', '')}
- **Owner**: {rule.get('Owner', 'N/A')}
- **Extra Info**: {rule.get('Extra Info', '')}
- **Priority**: {rule.get('Priority', 'N/A')}
- **Comment**: {rule.get('Comment', '')}

**Matched Line** (Line {line_num}):
```
{matched_line}
```

**Context** (±20 lines):
```
{context}
```
"""
                    attachment_content += rule_info + "\n"

                    # Add to summary for reporting
                    pattern_matches_summary.append({
                        'file': att_name,
                        'module': rule.get('Module', 'Unknown'),
                        'source_file': rule.get('_source_file', 'Unknown'),
                        'owner': rule.get('Owner', 'N/A'),
                        'priority': rule.get('Priority', 'N/A'),
                        'comment': rule.get('Comment', ''),
                        'keywords': rule.get('Keywords', ''),
                        'matched_line': matched_line[:200],
                        'line_number': line_num
                    })
            else:
                # No pattern matched, include generic key log lines as fallback
                log_lines = []
                for line in att_text.split('\n'):
                    lower_line = line.lower()
                    if any(kw in lower_line for kw in ['error', 'exception', 'fail', 'warning', 'crash']):
                        log_lines.append(line)
                log_excerpt = '\n'.join(log_lines[:30])
                if log_excerpt:
                    attachment_content += f"\n--- File: {att_name} (No pattern matched, key logs) ---\n{log_excerpt[:1500]}\n"

    # Add pattern match summary at the end
    if pattern_matches_summary:
        attachment_content += "\n\n=== PATTERN MATCH SUMMARY ===\n"
        for i, m in enumerate(pattern_matches_summary, 1):
            attachment_content += f"""
{i}. [{m['module']}] 来源: {m['source_file']}.json | Priority={m['priority']} | {m['comment']}
   - Keywords: {m['keywords']}
   - Owner: {m['owner']}
   - File: {m['file']} Line: {m['line_number']}
   - Match: {m['matched_line'][:100]}...
"""

    # Language instruction
    if output_language == 'en':
        lang_instruction = "Provide the response in English."
    elif output_language == 'zh-CN':
        lang_instruction = "请用简体中文回复。"
    else:
        lang_instruction = "請用繁體中文回覆。"

    analysis_prompt = f"""You are a Senior Technical Support Analyst. Analyze this Jira issue and provide:

1. Root Cause Analysis (root cause of the issue)
2. Key Error Logs (extract important log snippets WITH file source)
3. Suggested Fix (step-by-step solution)

IMPORTANT: When analyzing logs, include the FILE SOURCE and LINE NUMBER if available.

Issue Details:
{issue_text}
{attachment_content}

{lang_instruction}

Format your response clearly with headers."""

    # Check token count before calling AI
    MAX_TOKENS = 196608
    estimated_tokens = count_tokens(analysis_prompt)
    token_warning = None

    if estimated_tokens > MAX_TOKENS:
        token_warning = f"Warning: Estimated token count ({estimated_tokens:,}) exceeds limit ({MAX_TOKENS:,}). Please select fewer dates or reduce attachment size."

    # Call AI
    try:
        ai_result = call_ai_with_tool(analysis_prompt, ai_tool)
        # Get original attachment info from issue
        url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}?fields=attachment"
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.get(url, headers=headers, auth=get_jira_auth(), timeout=30)
            original_attachments = []
            if response.status_code == 200:
                atts = response.json().get('fields', {}).get('attachment', [])
                original_attachments = [{"id": a.get('id'), "filename": a.get('filename')} for a in atts]
        except:
            original_attachments = []

        analyzed_names = [n for n, _ in attachment_texts]
        return jsonify({
            "analysis": ai_result,
            "attachments": original_attachments,
            "analyzed_files": analyzed_names,
            "analyzed_dates": analyzed_dates,
            "token_warning": token_warning,
            "estimated_tokens": estimated_tokens
        })
    except Exception as e:
        return jsonify({"error": f"AI Analysis failed: {str(e)}"}), 500


@app.route('/api/update_jira_comment', methods=['POST'])
def api_update_jira_comment():
    """Update Jira issue with analysis as a comment"""
    data = request.json
    issue_key = data.get('issue_key')
    analysis = data.get('analysis')

    if not issue_key or not analysis:
        return jsonify({"error": "Issue key and analysis are required"}), 400

    # Use Basic Auth for comments
    if not JIRA_USER or not JIRA_PASSWORD:
        return jsonify({"error": "JIRA_USER and JIRA_PASSWORD not configured"}), 500

    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/comment"
    auth = HTTPBasicAuth(JIRA_USER, JIRA_PASSWORD)
    headers = {
        "Content-Type": "application/json"
    }

    # Convert analysis to Jira wiki format
    jira_format = convert_to_jira_wiki(analysis)

    # Format comment (without "AI Analysis Report" header)
    comment_body = {
        "body": jira_format + "\n\n---\n_由 Jira Insight AI 分析產生_"
    }

    try:
        response = requests.post(url, auth=auth, headers=headers, json=comment_body, timeout=30)
        if response.status_code == 201:
            return jsonify({"success": True, "message": "Comment added successfully"})
        else:
            return jsonify({"error": f"Jira API error: {response.status_code} - {response.text[:200]}"}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to update Jira: {str(e)}"}), 500


def call_ai_with_tool(prompt, tool='openai'):
    """Call AI with selected tool"""
    if tool == 'rtk':
        client = openai.OpenAI(
            base_url="https://devops.realtek.com/realgpt-api/openai-compatible/v1",
            api_key=RTK_LLM_API_KEY or ""
        )
        model = "expert"
    elif tool == 'deepseek':
        client = openai.OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=DEEPSEEK_LLM_API_KEY or ""
        )
        model = "deepseek-chat"
    else:  # openai
        client = openai.OpenAI(api_key=SYSTEM_OPENAI_KEY)
        model = "gpt-4o"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a senior technical support analyst."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content


def get_attachments_info(issue_key):
    """Get attachment info including dates"""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}?fields=attachment"
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, auth=get_jira_auth(), timeout=30)
        if response.status_code != 200:
            return []

        attachments = response.json().get('fields', {}).get('attachment', [])
        result = []

        for att in attachments:
            filename = att.get('filename', '')
            att_id = att.get('id', '')
            created = att.get('created', '')  # Format: 2024-01-15T10:30:00.000+0800

            # Extract date part only (YYYY-MM-DD)
            date_part = created.split('T')[0] if created else ''

            # Check if it's a text/log file or archive
            is_valid = (filename.endswith('.txt') or filename.endswith('.log') or
                       filename.endswith('.zip') or filename.endswith('.tar') or
                       filename.endswith('.tgz') or filename.endswith('.tar.gz') or
                       filename.endswith('.gz'))

            if is_valid and date_part:
                result.append({
                    'id': att_id,
                    'filename': filename,
                    'date': date_part,
                    'created': created
                })

        return result
    except Exception as e:
        print(f"Error getting attachments info: {e}")
        return []


def download_and_analyze_attachments(issue_key, selected_dates=None):
    """
    Download attachments, extract archives, and analyze txt files

    Args:
        issue_key: Jira issue key
        selected_dates: List of date strings (YYYY-MM-DD) to filter. If None, analyze top 2 latest.
    """
    # Create attachment directory
    att_dir = os.path.join(ATTACHMENTS_BASE_DIR, issue_key)
    os.makedirs(att_dir, exist_ok=True)

    # Get issue attachments with dates
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}?fields=attachment"
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, auth=get_jira_auth(), timeout=30)
        if response.status_code != 200:
            return [], []

        all_attachments = response.json().get('fields', {}).get('attachment', [])

        # Filter attachments by date
        attachments_to_download = []
        attachment_info = []

        for att in all_attachments:
            filename = att.get('filename', '')
            created = att.get('created', '')
            date_part = created.split('T')[0] if created else ''

            # Check if it's a text/log file or archive
            is_valid = (filename.endswith('.txt') or filename.endswith('.log') or
                       filename.endswith('.zip') or filename.endswith('.tar') or
                       filename.endswith('.tgz') or filename.endswith('.tar.gz') or
                       filename.endswith('.gz'))

            if is_valid and date_part:
                attachment_info.append({
                    'id': att.get('id'),
                    'filename': filename,
                    'date': date_part,
                    'created': created
                })

        # Determine which dates to analyze
        if selected_dates and len(selected_dates) > 0:
            # Filter to selected dates
            dates_to_analyze = selected_dates
            print(f"[Attachment] Using user-selected dates: {dates_to_analyze}")
        else:
            # Auto-select top 2 latest dates
            date_counts = {}
            for att in attachment_info:
                d = att['date']
                date_counts[d] = date_counts.get(d, 0) + 1

            # Sort by date descending (newest first)
            sorted_dates = sorted(date_counts.keys(), reverse=True)
            dates_to_analyze = sorted_dates[:2]  # Top 2 latest dates
            print(f"[Attachment] Auto-selected top 2 latest dates: {dates_to_analyze}")

        # Filter attachments to download
        attachments_to_download = [att for att in attachment_info if att['date'] in dates_to_analyze]

        print(f"[Attachment] Found {len(all_attachments)} total attachments, will analyze {len(attachments_to_download)} from dates: {dates_to_analyze}")

        txt_contents = []
        analyzed_files = []

        for att in attachments_to_download:
            filename = att.get('filename', '')
            att_id = att.get('id', '')

            # Get download URL from original attachment data
            original_att = next((a for a in all_attachments if a.get('id') == att_id), {})
            download_url = original_att.get('content', '')
            mime_type = original_att.get('mimeType', '')

            if not download_url and not att_id:
                continue

            # Use the content URL from attachment metadata (prefer REST API, fallback to web URL)
            if att_id:
                # First try REST API (doesn't work for this Jira)
                # Try using the content URL directly from metadata
                if download_url:
                    # content URL is already set from att.get('content')
                    print(f"[Attachment] Using content URL: {download_url}")
            elif download_url.startswith('/'):
                # Convert relative URL to full URL
                download_url = JIRA_BASE_URL.rstrip('/') + download_url
                print(f"[Attachment] Converted relative URL to: {download_url}")
            else:
                print(f"[Attachment] Downloading: {filename} from {download_url}")

            # Download file - use cookies if available (for 2FA), otherwise use auth
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                }

                cookies = get_jira_cookies()
                if cookies:
                    # Use cookies from browser (2FA verified session)
                    headers["Cookie"] = cookies
                    file_response = requests.get(download_url, headers=headers, timeout=60)
                else:
                    # Fallback to basic auth
                    session = requests.Session()
                    session.auth = get_jira_auth()
                    file_response = session.get(download_url, headers=headers, timeout=60)
                if file_response.status_code != 200:
                    print(f"Failed to download {filename}: HTTP {file_response.status_code}")
                    continue

                # Check if we got an HTML error page instead of actual file
                content_type = file_response.headers.get('Content-Type', '')
                content_length = file_response.headers.get('Content-Length', 'unknown')
                print(f"[Attachment] Response - Status: {file_response.status_code}, Type: {content_type}, Size: {content_length}")

                if 'text/html' in content_type:
                    print(f"Got HTML instead of file for {filename}")
                    # Print first 200 chars of response for debugging
                    print(f"[Attachment] Response preview: {file_response.text[:200]}")
                    continue

                local_path = os.path.join(att_dir, filename)
                with open(local_path, 'wb') as f:
                    f.write(file_response.content)

                # Check if it's a text file or archive
                if filename.endswith('.txt') or filename.endswith('.log'):
                    try:
                        text = file_response.content.decode('utf-8', errors='ignore')
                        txt_contents.append((filename, text))
                        print(f"[Attachment] Added direct file: {filename}")
                    except:
                        pass
                elif is_archive(filename):
                    # Validate archive before extracting
                    if not is_valid_archive(local_path):
                        print(f"Skipping invalid archive: {filename}")
                        continue
                    # Extract archive and find txt files
                    extracted = extract_archive(local_path, att_dir)
                    for txt_file in extracted:
                        try:
                            with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                txt_contents.append((os.path.basename(txt_file), content))
                                print(f"[Attachment] Added file from archive: {os.path.basename(txt_file)}")
                        except:
                            pass

            except Exception as e:
                print(f"Error downloading {filename}: {e}")
                continue

        # Clean up attachments directory after analysis
        try:
            shutil.rmtree(att_dir)
        except:
            pass

        # Track analyzed files
        analyzed_files = [name for name, _ in txt_contents]

        print(f"[Attachment] Total files analyzed: {len(txt_contents)}")
        print(f"[Attachment] Analyzed dates: {dates_to_analyze}")
        print(f"[Attachment] Analyzed files: {analyzed_files}")
        return txt_contents, dates_to_analyze, analyzed_files

    except Exception as e:
        print(f"Error in download_and_analyze_attachments: {e}")
        # Clean up on error
        try:
            shutil.rmtree(att_dir)
        except:
            pass
        return [], [], []


def is_archive(filename):
    """Check if file is a supported archive by extension"""
    archive_exts = ['.zip', '.tar', '.tgz', '.tar.gz', '.7z', '.rar', '.gz']
    return any(filename.lower().endswith(ext) for ext in archive_exts)


def is_valid_archive(file_path):
    """Check if file is actually a valid archive by reading magic bytes"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)

            # ZIP: PK (0x50 0x4B)
            if header[:2] == b'PK':
                return True

            # GZIP: 0x1f 0x8b
            if header[:2] == b'\x1f\x8b':
                return True

            # TAR: ustar at offset 257
            if len(header) >= 265 and b'ustar' in header[257:]:
                return True

        return False
    except:
        return False


def download_and_analyze_attachments_safe(issue_key, selected_dates=None):
    """Wrapper with error handling for attachment download"""
    try:
        return download_and_analyze_attachments(issue_key, selected_dates)
    except Exception as e:
        print(f"Error in attachment download for {issue_key}: {e}")
        return [], [], []


def convert_to_jira_wiki(text):
    """Convert markdown-like text to Jira wiki format"""
    if not text:
        return text

    # Remove HTML tags
    import re
    text = re.sub(r'<[^>]+>', '', text)

    # Convert headers (reduce level: ### -> h2., ## -> h2., # -> h1.)
    text = re.sub(r'^#### (.+)$', r'h3. \1', text, flags=re.MULTILINE)
    text = re.sub(r'^### (.+)$', r'h3. \1', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'h2. \1', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'h1. \1', text, flags=re.MULTILINE)

    # Convert text styles
    # Bold: **text** -> *text*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    # Italic: *text* or _text_ -> _text_
    text = re.sub(r'(?<![\*\w])\*(?!\*)(.+?)\*(?!\*)', r'_\1_', text)
    # Strikethrough: ~~text~~ -> -text-
    text = re.sub(r'~~(.+?)~~', r'-\1-', text)
    # Underline: ++text++ -> +text+
    text = re.sub(r'\+\+(.+?)\+\+', r'+\1+', text)

    # Convert code blocks - use {noformat} for large blocks (logs)
    # First handle multiline code blocks
    text = re.sub(r'```(\w*)\n(.+?)```', r'{noformat}\n\2\n{noformat}', text, flags=re.DOTALL)
    # Then handle inline code
    text = re.sub(r'`(.+?)`', r'{{\1}}', text)

    # Convert tables (simplified)
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        # Skip markdown table separators
        if re.match(r'^\|[\s\-:|]+$', line):
            continue
        # Convert table rows
        if '|' in line and not line.startswith('| '):
            # Keep simple rows but remove extra pipes
            line = re.sub(r'\|+', '|', line)
        new_lines.append(line)
    text = '\n'.join(new_lines)

    # Convert lists (Jira uses * for bullet, # for numbered)
    text = re.sub(r'^[-*] (.+)$', r'* \1', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\. (.+)$', r'# \1', text, flags=re.MULTILINE)

    # Convert links [text](url) -> [text|url]
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'[\1|\2]', text)

    return text


def extract_archive(archive_path, extract_to):
    """Extract archive and return list of txt files found"""
    txt_files = []

    try:
        if archive_path.endswith('.zip'):
            try:
                with zipfile.ZipFile(archive_path, 'r') as z:
                    z.extractall(extract_to)
                    txt_files = [os.path.join(extract_to, n) for n in z.namelist() if n.endswith('.txt') or n.endswith('.log')]
            except zipfile.BadZipFile:
                print(f"Bad zip file: {archive_path}")
                return []

        elif archive_path.endswith('.tar') or archive_path.endswith('.tgz') or archive_path.endswith('.tar.gz'):
            try:
                with tarfile.open(archive_path, 'r:*') as t:
                    t.extractall(extract_to)
                    members = t.getmembers()
                    txt_files = [os.path.join(extract_to, m.name) for m in members if m.name.endswith('.txt') or m.name.endswith('.log')]
            except tarfile.TarError:
                print(f"Bad tar file: {archive_path}")
                return []

        elif archive_path.endswith('.gz') and not archive_path.endswith('.tar.gz'):
            # Single gz file
            import gzip
            base_name = os.path.splitext(os.path.basename(archive_path))[0]
            output_path = os.path.join(extract_to, base_name)
            with gzip.open(archive_path, 'rb') as f:
                with open(output_path, 'wb') as out:
                    out.write(f.read())
            if output_path.endswith('.txt'):
                txt_files.append(output_path)

        elif archive_path.endswith('.7z'):
            # 7z requires py7zr - skip for now if not available
            pass

        elif archive_path.endswith('.rar'):
            # rar requires unrar - skip for now if not available
            pass

    except Exception as e:
        print(f"Error extracting {archive_path}: {e}")

    return txt_files


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
