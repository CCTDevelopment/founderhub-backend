import os
import json
import openai
from datetime import datetime

openai.api_key = os.getenv("OPENAI_API_KEY")

QUEUE_FILE = "logs/content_queue.json"

def generate_facebook_posts(n=3):
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

    content = response.choices[0].message.content.strip().split("\n\n")
    return [post.strip() for post in content if post.strip()]

def queue_facebook_posts(posts):
    os.makedirs("logs", exist_ok=True)
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            queue = json.load(f)
    else:
        queue = []

    timestamp = datetime.utcnow().isoformat()
    for post in posts:
        queue.append({"created": timestamp, "content": post})

    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

    print(f"📦 Queued {len(posts)} post(s) for future scheduling.")

def get_next_queued_post():
    if not os.path.exists(QUEUE_FILE):
        return None

    with open(QUEUE_FILE, "r") as f:
        queue = json.load(f)

    if not queue:
        return None

    next_post = queue.pop(0)

    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

    return next_post["content"]
