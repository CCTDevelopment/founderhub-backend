import os
import json

def get_project_path(project_name):
    return f"projects/{project_name.lower().replace(' ', '_')}"

def load_assistants(folder):
    path = os.path.join(folder, "assistants.json")
    with open(path, "r") as f:
        return json.load(f)

def load_prompts(folder):
    path = os.path.join(folder, "prompts.json")
    with open(path, "r") as f:
        return json.load(f)

def get_thread_path(project_name):
    folder = get_project_path(project_name)
    return os.path.join(folder, "threads.json")

def load_threads(project_name):
    path = get_thread_path(project_name)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_threads(project_name, threads):
    path = get_thread_path(project_name)
    with open(path, "w") as f:
        json.dump(threads, f, indent=2)
