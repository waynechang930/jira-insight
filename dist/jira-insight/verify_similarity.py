import os
import requests
import psycopg2
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
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# OpenAI
OPENAI_CLIENT = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_jira_content(issue_key):
    """Fetch specific issue content to use as the 'Query'."""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}"
    headers = {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    print(f"?? Fetching content for Issue: {issue_key}...")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            fields = data.get('fields', {})
            summary = fields.get('summary', '')
            description = fields.get('description', '') or ''
            
            print(f"? Target Issue Found: {summary}")
            # Combine Summary and Description for the search query
            return f"Issue: {summary}. Description: {description[:1000]}"
        else:
            print(f"? Failed to fetch Jira issue. Status: {response.status_code}")
            return None
    except Exception as e:
        print(f"? Connection Error: {e}")
        return None

def generate_embedding(text):
    """Generate embedding vector."""
    text = text.replace("\n", " ")
    return OPENAI_CLIENT.embeddings.create(input=[text], model="text-embedding-3-small").data[0].embedding

def search_similar_issues(query_vector, exclude_key, top_k=5):
    """
    Search the vector database for similar issues, 
    EXCLUDING the issue itself.
    """
    conn = psycopg2.connect(DB_DSN)
    register_vector(conn)
    cursor = conn.cursor()
    
    print(f"\n?? Searching Database for top {top_k} similar cases (Excluding {exclude_key})...")
    
    # SQL Query:
    # 1. Calculate Similarity (1 - distance)
    # 2. WHERE clause filters out the target key itself
    sql = """
    SELECT jira_key, summary, 1 - (embedding <=> %s::vector) as similarity
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

def main():
    # ?? The Verification Target (Query Issue)
    TARGET_ISSUE = "R5KTC2841A-475"
    
    # 1. Get the text from Jira (Simulating a new user report)
    query_text = get_jira_content(TARGET_ISSUE)
    
    if not query_text:
        print("Cannot proceed without query text.")
        return

    # 2. Convert to Vector
    print("?? Generating embedding for query...")
    query_vector = generate_embedding(query_text)
    
    # 3. Search (Passing TARGET_ISSUE to be excluded)
    results = search_similar_issues(query_vector, exclude_key=TARGET_ISSUE)
    
    # 4. Display Results
    print("\n" + "="*80)
    print(f"?? SIMILARITY ANALYSIS REPORT FOR: {TARGET_ISSUE}")
    print("="*80)
    
    if not results:
        print("No similar matches found. The database might be empty or too small.")
    
    for rank, (key, summary, score) in enumerate(results, 1):
        score_percent = score * 100
        
        # Color coding for terminal (Optional visual aid)
        # High similarity > 85%, Medium > 75%
        prefix = "??" if score > 0.85 else "  "
        
        print(f"{prefix} Rank #{rank} | Key: {key} | Similarity: {score_percent:.2f}%")
        print(f"   Summary: {summary}")
        print("-" * 80)

if __name__ == "__main__":
    main()
