from dotenv import load_dotenv
import os
from facebook.content_generator import generate_facebook_posts, queue_facebook_posts

# Load env
load_dotenv()

if __name__ == "__main__":
    posts = generate_facebook_posts(n=5)
    queue_facebook_posts(posts)
