import os
import json
import requests
import psycopg2
from psycopg2.extras import Json
from pgvector.psycopg2 import register_vector
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
# Database
DB_DSN = f"dbname={os.getenv('DB_NAME')} user={os.getenv('DB_USER')} password={os.getenv('DB_PASSWORD')} host={os.getenv('DB_HOST')} port={os.getenv('DB_PORT')}"

# Jira
JIRA_BASE_URL = os.getenv("JIRA_DOMAIN")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN") # Use the PAT from .env
JIRA_JQL = os.getenv("JIRA_JQL")

# OpenAI
OPENAI_CLIENT = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# F-004: AI ETL Prompt Template
ETL_PROMPT_TEMPLATE = """
# Role
You are a Data Extraction Specialist for a Bug Tracking System.
# Task
Your task is to process a raw Jira ticket thread and extract only the technically relevant information for indexing.
# Input Text (Raw Jira Data)
<raw_data>
{raw_data}
</raw_data>
# Instructions
1. Summarize the Problem: Extract core technical symptom.
2. Extract the Resolution: Identify HOW the issue was fixed.
3. Keywords: List technical keywords.
# Output Format (JSON)
{{
  "summary_enhanced": "String",
  "symptom_description": "String",
  "resolution_logic": "String",
  "has_patch": boolean,
  "patch_link": "String or null"
}}
"""

def get_db_connection():
    """Establish database connection and register vector extension."""
    conn = psycopg2.connect(DB_DSN)
    register_vector(conn)
    return conn

def fetch_jira_issues(jql, start_at=0, max_results=50):
    """
    Fetch data from Jira Data Center using Bearer Token (PAT).
    Using API v2 which is standard for Data Center / Server versions.
    """
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    
    # Header-based authentication for Personal Access Tokens
    headers = {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    query = {
        'jql': jql,
        'startAt': start_at,
        'maxResults': max_results,
        'fields': ['key', 'summary', 'description', 'comment', 'resolution', 'labels', 'components']
    }
    
    print(f"Fetching Jira issues starting at {start_at}...")
    
    try:
        response = requests.get(url, headers=headers, params=query, timeout=30)
        
        if response.status_code != 200:
            print(f"Error fetching Jira (Status: {response.status_code})")
            print("Response:", response.text[:200]) # Print first 200 chars for debugging
            return []
            
        return response.json().get('issues', [])
        
    except Exception as e:
        print(f"Connection Error: {e}")
        return []

def ai_process_issue(issue_data):
    """
    F-004: Clean and structure data using AI (GPT-3.5-Turbo).
    Extracts summary, symptoms, resolution, and patch info.
    """
    # Extract comments safely
    comments_list = []
    if 'comment' in issue_data['fields'] and issue_data['fields']['comment']:
        comments_list = [c.get('body', '') for c in issue_data['fields']['comment'].get('comments', [])]

    # Simplify input to save Tokens (only keep Summary, Description, Comments)
    raw_text = json.dumps({
        "summary": issue_data['fields'].get('summary', ''),
        "description": issue_data['fields'].get('description', ''),
        "comments": comments_list
    }, ensure_ascii=False)

    try:
        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a JSON generator."},
                {"role": "user", "content": ETL_PROMPT_TEMPLATE.format(raw_data=raw_text[:12000])} # Limit length
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI ETL Failed for {issue_data['key']}: {e}")
        # Fallback: Return basic data if AI fails
        return {
            "summary_enhanced": issue_data['fields'].get('summary', ''),
            "symptom_description": "AI Processing Failed or content too long.",
            "resolution_logic": "Unknown",
            "has_patch": False,
            "patch_link": None
        }

def generate_embedding(text):
    """Generate embedding using OpenAI text-embedding-3-small."""
    # Remove newlines to improve embedding quality
    text = text.replace("\n", " ")
    if not text.strip():
        return [0.0] * 1536 # Return zero vector if empty
        
    try:
        response = OPENAI_CLIENT.embeddings.create(input=[text], model="text-embedding-3-small")
        return response.data[0].embedding
    except Exception as e:
        print(f"Embedding Error: {e}")
        return [0.0] * 1536

def main():
    # 1. Connect to DB
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"Fatal: Cannot connect to database. {e}")
        return

    jql = JIRA_JQL
    if not jql:
        print("Error: JIRA_JQL not found in .env")
        return

    start_at = 0
    batch_size = 10 # Process 10 items per batch
    
    print(f"Starting ETL Process for JQL: {jql}")
    
    while True:
        # 2. Fetch Issues
        issues = fetch_jira_issues(jql, start_at, batch_size)
        
        if not issues:
            print("No more issues found or error occurred. Exiting loop.")
            break
            
        for issue in issues:
            key = issue['key']
            
            # 3. Check duplicate (Simple incremental update)
            cursor.execute("SELECT id FROM jira_issues WHERE jira_key = %s", (key,))
            if cursor.fetchone():
                print(f"Skipping {key} (Already exists)")
                continue

            print(f"Processing {key}...")

            # 4. AI ETL Processing (Transform)
            clean_data = ai_process_issue(issue)
            
            # 5. Prepare text for embedding (Summary + Symptom + Resolution)
            text_to_embed = f"Issue: {clean_data.get('summary_enhanced')}. Symptom: {clean_data.get('symptom_description')}. Fix: {clean_data.get('resolution_logic')}"
            
            # 6. Generate vector
            vector = generate_embedding(text_to_embed)
            
            # 7. Load into database
            try:
                cursor.execute("""
                    INSERT INTO jira_issues 
                    (jira_key, summary, description, resolution, raw_content, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    key,
                    clean_data.get('summary_enhanced'),
                    clean_data.get('symptom_description'),
                    clean_data.get('resolution_logic'),
                    Json(issue),        # Store raw data
                    Json(clean_data),   # Store structured data
                    vector
                ))
                conn.commit()
                print(f"Successfully indexed {key}")
            except Exception as e:
                conn.rollback()
                print(f"DB Error inserting {key}: {e}")

        # Move to next page
        start_at += batch_size
        
    print("ETL Process Completed.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
