import os
import psycopg2
from dotenv import load_dotenv

# 1. Load configuration from .env
load_dotenv()

# Get database connection info
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

# Connection string
conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"

def init_schema():
    try:
        # 2. Connect to the database
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True # Enable autocommit
        cursor = conn.cursor()
        print("? Successfully connected to the database!")

        # 3. Enable 'vector' extension (if not already enabled)
        print("?? Checking and enabling 'vector' extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        # 4. Create table (does nothing if it already exists)
        # Note: vector(1536) corresponds to OpenAI's text-embedding-3-small model.
        # If you use a different model, adjust this number (e.g., text-embedding-004 uses 768).
        print("?? Creating 'jira_issues' table...")
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS jira_issues (
            id SERIAL PRIMARY KEY,
            jira_key VARCHAR(50) UNIQUE NOT NULL,
            summary TEXT,
            description TEXT,
            resolution TEXT,
            
            -- Store raw Jira JSON response for debugging
            raw_content JSONB,
            
            -- Store structured data after ETL (including patch_link, etc.)
            metadata JSONB,
            
            -- Vector column, dimension 1536
            embedding vector(1536),
            
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)
        print("? Table 'jira_issues' created successfully (or already exists).")

        # 5. Create HNSW Index (for faster vector search)
        # This is crucial for large datasets to change search speed from O(N) to O(log N).
        print("?? Creating vector index (HNSW)...")
        create_index_sql = """
        CREATE INDEX IF NOT EXISTS jira_issues_embedding_idx 
        ON jira_issues 
        USING hnsw (embedding vector_cosine_ops);
        """
        cursor.execute(create_index_sql)
        print("? Vector index created successfully.")

        cursor.close()
        conn.close()
        print("\n?? Database Schema initialization successful!")

    except Exception as e:
        print(f"\n? Initialization failed: {e}")
        print("Please check if your Docker container is running (docker ps) and if .env settings are correct.")

if __name__ == "__main__":
    init_schema()
