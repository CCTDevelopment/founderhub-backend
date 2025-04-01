import os
import json
import openai
import psycopg2
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables (ideally once in your main entry point)
load_dotenv()

# Set OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_db_connection():
    """
    Establishes and returns a connection to the Postgres database.
    """
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def generate_facebook_posts(n: int = 3) -> list[str]:
    """
    Generates 'n' Facebook post ideas using the OpenAI API.
    Returns a list of post content strings.
    """
    prompt = (
        f"You're the AI CMO for a startup called FounderHub.ai.\n"
        f"Generate {n} engaging, founder-focused Facebook post ideas to promote the product, build trust, and drive traffic. "
        f"Include tips, inspiration, and subtle CTAs. Make each one sound authentic, not too salesy. Use emojis and 2 hashtags max per post."
    )

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=800
    )

    # Split by double newlines to separate posts; adjust as needed.
    content = response.choices[0].message.content.strip().split("\n\n")
    return [post.strip() for post in content if post.strip()]

def queue_facebook_posts(posts: list[str]) -> None:
    """
    Queues the provided Facebook posts by inserting them into the SQL table 'content_queue'.
    Each post is tagged with a unique UUID and the current UTC timestamp.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for post in posts:
                cur.execute(
                    """
                    INSERT INTO content_queue (id, created_at, content)
                    VALUES (%s, %s, %s)
                    """,
                    (str(uuid.uuid4()), datetime.utcnow(), post)
                )
        conn.commit()
        print(f"📦 Queued {len(posts)} post(s) for future scheduling.")
    finally:
        conn.close()

def get_next_queued_post() -> str | None:
    """
    Retrieves and removes the earliest queued post from the SQL table 'content_queue'.
    Returns the content of the post, or None if the queue is empty.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content FROM content_queue
                ORDER BY created_at ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return None
            post_id, content = row
            cur.execute("DELETE FROM content_queue WHERE id = %s", (post_id,))
            conn.commit()
            return content
    finally:
        conn.close()
