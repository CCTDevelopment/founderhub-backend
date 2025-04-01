from dotenv import load_dotenv
import os
from facebook.poster import FacebookPoster
from facebook.content_generator import generate_facebook_posts, queue_facebook_posts, get_next_queued_post

# Load env vars
load_dotenv()

FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")

def post_scheduled_content():
    # Post if there's something queued
    next_post = get_next_queued_post()
    if next_post:
        print("🗓️ Scheduled post day — posting next queued content...")
        fb_poster = FacebookPoster(FB_PAGE_TOKEN)
        fb_poster.post(next_post)
    else:
        print("📭 No queued posts available. Run the content generator.")

if __name__ == "__main__":
    post_scheduled_content()
