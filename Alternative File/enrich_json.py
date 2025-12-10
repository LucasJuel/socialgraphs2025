# Script for enriching data in contributors.json (THREADED VERSION)

import json, os, requests, time, threading
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------
# ENV + HEADERS
# ---------------------------

load_dotenv()
TOKEN  = os.getenv("TOKENLS")
TOKEN1 = os.getenv("TOKENSS")
TOKEN2 = os.getenv("TOKENLS1")
TOKEN3 = os.getenv("TOKENSS1")

HEAD  = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN}"} if TOKEN else {})}
HEAD1 = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN1}"} if TOKEN1 else {})}
HEAD2 = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN2}"} if TOKEN2 else {})}
HEAD3 = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN3}"} if TOKEN3 else {})}

HEAD_LIST = [HEAD, HEAD1, HEAD2, HEAD3]
BASE_API  = "https://api.github.com/repos/"


# ---------------------------
# JSON UTILITIES
# ---------------------------

def load_from_json(file):
    with open(file, "r") as f:
        return json.load(f)

def write_to_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

def write_to_jsonl(file, data):
    with open(file, "a") as f:
        f.write(json.dumps(data) + "\n")

jsonl_lock = threading.Lock()


# ---------------------------
# API CALL LOGIC
# ---------------------------

def get_json(url, params=None, max_retries=10, worker_id=0, stop_event=None):
    attempt = 0
    head_idx = worker_id % len(HEAD_LIST)
    headers = HEAD_LIST[head_idx]

    while True:
        attempt += 1
        try:
            r = requests.get(url, headers=headers, params=params or {}, timeout=30)
        except:
            if attempt <= max_retries:
                time.sleep(1)
                continue
            return None

        # Rate limit
        if r.status_code == 403 and "rate limit" in r.text.lower():
            head_idx = (head_idx + 1) % len(HEAD_LIST)
            headers = HEAD_LIST[head_idx]
            time.sleep(3)
            continue

        if r.status_code != 200:
            return None

        try:
            return r.json()
        except:
            return None


# ---------------------------
# ENRICH FUNCTION
# ---------------------------

def enrich_repo(repo_fullname):
    url  = BASE_API + repo_fullname
    data = get_json(url)

    if not data:
        return {"stargazers_count": None, "forks_count": None, "language": None}

    return {
        "stargazers_count": data.get("stargazers_count"),
        "forks_count": data.get("forks_count"),
        "language": data.get("language")
    }


# ---------------------------
# THREADED WORKER
# ---------------------------

def enrich_worker(repo, repo_authors):
    """
    Returns (repo_name, enriched_data) OR None if skipped.
    """
    num_collab = len(repo_authors["authors"])

    if num_collab <= 1:
        return None  # skip

    enriched = enrich_repo(repo)
    enriched["number_of_collaborators"] = num_collab
    enriched["authors"] = repo_authors["authors"]

    return repo, enriched


# ---------------------------
# MAIN
# ---------------------------

if __name__ == "__main__":
    contributors = load_from_json("contributors.json")
    repos        = list(contributors.keys())

    enriched_repos = (
        load_from_json("enriched_data.json")
        if os.path.exists("enriched_data.json")
        else {}
    )

    print(f"Loaded {len(repos)} repos from contributors.json")
    print(f"Already enriched {len(enriched_repos)} repos")

    to_process = []
    skipped = 0

    # Determine which repos need work
    for repo in repos:
        authors = contributors[repo]["authors"]
        if len(authors) <= 1:
            skipped += 1
            print(f"[skip] {repo} has {len(authors)} collaborators")
            continue

        if repo not in enriched_repos:
            to_process.append(repo)

    print(f"\nProcessing {len(to_process)} repos with 4 threads")
    print(f"Skipped {skipped} repos\n")

    # ---------------------------
    # THREAD POOL
    # ---------------------------

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                enrich_worker,
                repo,
                contributors[repo]
            ): repo
            for repo in to_process
        }

        for future in as_completed(futures):
            result = future.result()
            if not result:
                continue

            repo, data = result
            enriched_repos[repo] = data  # store in memory

            with jsonl_lock:
                write_to_jsonl("enriched_data_incrementally.json", data)

            print(f"[OK] {repo} enriched")

    # ---------------------------
    # FINAL SAVE
    # ---------------------------

    write_to_json("enriched_data.json", enriched_repos)
    print(f"\nSaved enriched_data.json with {len(enriched_repos)} repos")