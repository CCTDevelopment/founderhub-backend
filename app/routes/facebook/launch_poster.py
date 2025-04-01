import os
import json
import openai
import psycopg2
import uuid
from datetime import datetime
from facebook.poster import FacebookPoster  # Adjust this import if needed
from dotenv import load_dotenv

# Load environment variables (ideally done once in your main entry point)
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

def generate_launch_post(product_name: str, site_url: str, purpose: str) -> str:
    """
    Generates a high-converting Facebook launch post using OpenAI.
    """
    prompt = (
        f"Write a high-converting Facebook launch post for a new product called {product_name}.\n"
        f"The product helps users: {purpose}.\n"
        f"The website is {site_url}.\n"
        "The tone should be exciting, confident, and founder-to-founder. "
        "Include a clear call-to-action and 2 relevant hashtags."
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=200
    )
    return response.choices[0].message.content.strip()

def has_already_launched(product_name: str) -> bool:
    """
    Checks if a launch post for the given product has already been published.
    This function queries the 'facebook_launch_posts' table for a record with status 'posted'.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM facebook_launch_posts WHERE product_name = %s AND status = 'posted'",
                (product_name,)
            )
            count = cur.fetchone()[0]
            return count > 0
    finally:
        conn.close()

def mark_as_launched(product_name: str, site_url: str, purpose: str, message: str, post_result: dict) -> None:
    """
    Records the launch post details into the 'facebook_launch_posts' table.
    Expected columns:
      - id (UUID)
      - product_name (TEXT)
      - site_url (TEXT)
      - purpose (TEXT)
      - message (TEXT)
      - post_result (JSON)
      - status (TEXT)
      - posted_at (TIMESTAMP)
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO facebook_launch_posts (
                    id, product_name, site_url, purpose, message, post_result, status, posted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'posted', %s)
                """,
                (
                    str(uuid.uuid4()),
                    product_name,
                    site_url,
                    purpose,
                    message,
                    json.dumps(post_result),
                    datetime.utcnow()
                )
            )
        conn.commit()
    finally:
        conn.close()

def post_launch_to_facebook(product_name: str, site_url: str, purpose: str) -> dict | None:
    """
    Generates, publishes, and logs a launch post to Facebook using the provided product details.
    
    By accepting product_name, site_url, and purpose as parameters, this function lets you define the
    launch details dynamically via an API or SQL. It checks if a post has already been published and,
    if not, generates a post with OpenAI, publishes it using FacebookPoster, and logs the details in SQL.
    
    Returns the post result as a dict if successful, otherwise None.
    """
    if has_already_launched(product_name):
        print("✅ Launch post already published. Skipping.")
        return None

    print("🚀 Generating and publishing your launch post...")
    message = generate_launch_post(product_name, site_url, purpose)

    page_token = os.getenv("FB_PAGE_TOKEN")
    poster = FacebookPoster(page_token)
    post_result = poster.post(message)  # Expected to return a dict with details about the post

    if post_result:
        mark_as_launched(product_name, site_url, purpose, message, post_result)
        print("✅ Launch post published and logged.")
        return post_result
    else:
        print("❌ Failed to publish launch post.")
        return None
