# gh_collab_multihop_live.py
import json
import os, time, requests, collections
import networkx as nx
import csv
import threading
import pickle
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://api.github.com"
load_dotenv()
TOKEN = os.getenv("TOKENLS")
TOKEN1 = os.getenv("TOKENSS")
TOKEN2 = os.getenv("TOKENLS1")
TOKEN3 = os.getenv("TOKENSS1")

HEAD = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN}"} if TOKEN else {})}
HEAD1 = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN1}"} if TOKEN1 else {})}
HEAD2 = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN2}"} if TOKEN2 else {})}
HEAD3 = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN3}"} if TOKEN3 else {})}
def parse_csv(file):
    data = []
    with open(file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[1] == 'C' and (row[5] not in ['', 'Markdown']):
                data.append({
                    'repo': row[2],
                    'description': row[10],
                    'language': row[5],
                    'stars': int(row[3]),
                    'forks': int(row[4]),
                    'url': row[6],
                    'username': row[7],
                    'issues': int(row[8]),
                    'last_commit': row[9],
                })
    return data


def get_json(url, params=None, max_retries=20):
    attempt = 0
    HEADINT = HEAD
    while True:
        
        attempt += 1
        try:
            if attempt % 4 == 1:
                HEADINT = HEAD1
                #print(f"[token switch] switching token for {url}")
            elif attempt % 4 == 2:
                HEADINT = HEAD2
                #print(f"[token switch] switching token1 for {url}")
            elif attempt % 4 == 3:
                HEADINT = HEAD3
                #print(f"[token switch] switching token2 for {url}")
            else:
                HEADINT = HEAD
                #print(f"[token switch] switching token3 for {url}")
            r = requests.get(url, headers=HEADINT, params=params or {}, timeout=30)
            #print(f"[request] {r.status_code} for token attempt {attempt} on {url} ")
        except requests.RequestException as e:
            if attempt <= max_retries:
                time.sleep(min(2**attempt, 10))
                continue
            print(f"[net] giving up on {url}: {e}")
            return []
        # rate limit
        if r.status_code == 403 and "rate limit" in (r.text or "").lower():
            reset_ts = r.headers.get("X-RateLimit-Reset")
            wait = min(max(0, int(reset_ts or 0) - int(time.time()) + 2), 20)
            if attempt <= max_retries:
                print(f"[ratelimit] waiting {wait}s for {url} on attempt {attempt}")
                time.sleep(wait)
                continue
            print("[ratelimit] giving up")
            return []
        if r.status_code != 200:
            preview = (r.text or "")[:200].replace("\n", " ")
            print(f"[error] {r.status_code} {r.reason} :: {url} :: {preview}...")
            return []
        try:
            return r.json()
        except ValueError:
            print(f"[decode] non-JSON from {url}")
            return []


def get_repos(user, limit=None):
    data = get_json(f"{BASE}/users/{user}/repos",
                    {"type": "owner", "sort": "updated", "per_page": 50})
    repos = [r for r in data if not r.get("fork")]
    return repos[:limit] if limit else repos


# Add get_all_commit_authors back (it was in your original script)
def get_all_commit_authors(owner, repo, max_threads=6):
    authors_global = set()
    emails_global = set()
    next_page = 1
    stop = False
    lock = threading.Lock()

    def worker():
        nonlocal next_page, stop
        local_authors = set()
        local_emails = set()

        while True:
            with lock:
                if stop:
                    break
                page = next_page
                next_page += 1

            if page % 50 == 0:
                print(f"[commits] fetching page {page} for {owner}/{repo}")
            
            data = get_json(
                f"{BASE}/repos/{owner}/{repo}/commits",
                params={"per_page": 100, "page": page},
            )

            if not data:
                with lock:
                    stop = True
                break

            for commit in data:
                if commit.get("author"):
                    login = commit["author"].get("login")
                    if login:
                        local_authors.add(login)

                c = commit.get("commit", {}).get("author", {})
                email = c.get("email")
                name = c.get("name")
                if email:
                    local_emails.add((name, email))

            if len(data) < 100:
                with lock:
                    stop = True
                break

            if len(local_authors) == 100:
                with lock:
                    stop = True
                break

        with lock:
            authors_global.update(local_authors)
            emails_global.update(local_emails)

    threads = []
    for _ in range(max_threads):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return authors_global, emails_global



def get_contributors_with_fallback(owner, repo, limit=None, max_threads=6):
    """
    Try /contributors endpoint first, fall back to commits API for large repos.
    """
    # Try the fast endpoint first
    totalData = []
    hasMore = True
    page = 1
    
    while hasMore:
        data = get_json(f"{BASE}/repos/{owner}/{repo}/contributors", 
                       {"per_page": 100, "page": page})
        
        # Check if repo is too large (403 error returns empty or error)
        if not data:
            break
        if isinstance(data, dict) and "message" in data:
            # API returned an error message - repo too large
            print(f"[fallback] {owner}/{repo} too large, using commits API...")
            authors, _ = get_all_commit_authors(owner, repo, max_threads=max_threads)
            contribs = list(authors)
            return contribs[:limit] if limit else contribs
        
        if len(data) == 100 and page < 6:
            page += 1
            totalData.extend(data)
        else:
            hasMore = False
            totalData.extend(data)
    
    # If we got no data at all, try commits API
    if not totalData:
        print(f"[fallback] No contributors from API, trying commits for {owner}/{repo}...")
        authors, _ = get_all_commit_authors(owner, repo, max_threads=max_threads)
        contribs = list(authors)
        return contribs[:limit] if limit else contribs
    
    contribs = [c["login"] for c in totalData if "login" in c]
    return contribs[:limit] if limit else contribs


def add_repo_clique(G, contributors, repo_fullname, lock):
    """Thread-safe: Connect all contributors pairwise."""
    with lock:
        if not G.has_node(repo_fullname):
            G.add_node(repo_fullname, contributors=contributors)
        
        # Compare with all existing nodes
        for other_node, other_data in list(G.nodes(data=True)):
            if other_node == repo_fullname:
                continue
            other_contribs = other_data.get("contributors", [])
            common = list(set(contributors).intersection(set(other_contribs)))
            w = len(common)
            if w > 0:
                if G.has_edge(repo_fullname, other_node):
                    G[repo_fullname][other_node]['weight'] += w
                else:
                    G.add_edge(repo_fullname, other_node, weight=w, users=common)


def process_user(user, depth, max_repos_per_user, max_contributors_per_repo):
    """Process a single user - fetch their repos and contributors."""
    results = []
    repos = get_repos(user, limit=max_repos_per_user)
    
    for r in repos:
        full = r["full_name"]
        owner = r["owner"]["login"]
        name = r["name"]
        contribs = get_contributors_with_fallback(owner, name, limit=max_contributors_per_repo)
        
        if contribs:
            results.append({
                'repo_full_name': full,
                'contributors': contribs,
                'depth': depth
            })
    
    return user, results


def crawl_from_repo_threaded(owner, repo_name,
                              max_depth=3,
                              max_users=500,
                              max_repos_per_user=10,
                              max_contributors_per_repo=50,
                              max_threads=8):
    """
    Multithreaded BFS starting from a specific repo.
    """
    G = nx.Graph()
    graph_lock = threading.Lock()
    
    visited_users = set()
    visited_repos = set()
    visited_lock = threading.Lock()
    
    processed_users = 0
    processed_lock = threading.Lock()
    
    # Get initial contributors from seed repo
    print(f"[seed] Getting contributors from {owner}/{repo_name}")
    seed_contribs = get_contributors_with_fallback(owner, repo_name, limit=max_contributors_per_repo)
    
    if not seed_contribs:
        print("No contributors found for seed repo!")
        return G
    
    # Add seed repo
    full_name = f"{owner}/{repo_name}"
    add_repo_clique(G, seed_contribs, full_name, graph_lock)
    visited_repos.add(full_name)
    
    # Initialize queue with seed contributors at depth 1
    queue = collections.deque([(user, 1) for user in seed_contribs])
    
    while queue:
        # Collect a batch of users to process in parallel
        batch = []
        with visited_lock:
            while queue and len(batch) < max_threads:
                user, depth = queue.popleft()
                
                if user in visited_users:
                    continue
                if depth > max_depth:
                    continue
                
                with processed_lock:
                    if processed_users >= max_users:
                        break
                    processed_users += 1
                    current_count = processed_users
                
                visited_users.add(user)
                batch.append((user, depth))
                print(f"[queue] Added {user} (depth={depth}) to batch ({current_count}/{max_users})")
        
        if not batch:
            break
        
        # Process batch in parallel
        print(f"\n[batch] Processing {len(batch)} users in parallel...")
        
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = {
                executor.submit(
                    process_user, 
                    user, 
                    depth, 
                    max_repos_per_user, 
                    max_contributors_per_repo
                ): (user, depth) 
                for user, depth in batch
            }
            
            for future in as_completed(futures):
                user, depth = futures[future]
                try:
                    _, results = future.result()
                    
                    for result in results:
                        repo_full = result['repo_full_name']
                        contribs = result['contributors']
                        
                        with visited_lock:
                            if repo_full in visited_repos:
                                continue
                            visited_repos.add(repo_full)
                        
                        print(f"  [repo] {repo_full} ({len(contribs)} contributors)")
                        add_repo_clique(G, contribs, repo_full, graph_lock)
                        
                        # Enqueue new contributors for next depth
                        if depth + 1 <= max_depth:
                            with visited_lock:
                                for c in contribs:
                                    if c not in visited_users:
                                        queue.append((c, depth + 1))
                    
                    print(f"[done] Processed user {user}")
                    
                except Exception as e:
                    print(f"[error] Failed to process {user}: {e}")
        
        with processed_lock:
            if processed_users >= max_users:
                print(f"\n[limit] Reached max_users limit ({max_users})")
                break
    
    return G


# ============ EVEN FASTER: Parallel repo processing within each user ============

def process_single_repo(owner, name, full_name, max_contributors):
    """Process a single repo - get its contributors."""
    contribs = get_contributors_with_fallback(owner, name, limit=max_contributors)
    return full_name, contribs


def process_user_parallel_repos(user, depth, max_repos_per_user, max_contributors_per_repo, repo_threads=4):
    """Process a user with parallel repo fetching."""
    repos = get_repos(user, limit=max_repos_per_user)
    results = []
    
    if not repos:
        return user, results
    
    # Fetch contributors for all repos in parallel
    with ThreadPoolExecutor(max_workers=repo_threads) as executor:
        futures = {
            executor.submit(
                process_single_repo,
                r["owner"]["login"],
                r["name"],
                r["full_name"],
                max_contributors_per_repo
            ): r["full_name"]
            for r in repos
        }
        
        for future in as_completed(futures):
            try:
                full_name, contribs = future.result()
                if contribs:
                    results.append({
                        'repo_full_name': full_name,
                        'contributors': contribs,
                        'depth': depth
                    })
            except Exception as e:
                print(f"[error] Repo fetch failed: {e}")
    
    return user, results


def crawl_from_repo_fast(owner, repo_name,
                          max_depth=3,
                          max_users=500,
                          max_repos_per_user=10,
                          max_contributors_per_repo=50,
                          user_threads=6,
                          repo_threads=4):
    """
    Fast multithreaded BFS with parallel user AND repo processing.
    """
    G = nx.Graph()
    graph_lock = threading.Lock()
    
    visited_users = set()
    visited_repos = set()
    visited_lock = threading.Lock()
    
    processed_users = 0
    processed_lock = threading.Lock()
    
    # Get initial contributors from seed repo
    print(f"[seed] Getting contributors from {owner}/{repo_name}")
    seed_contribs = get_contributors_with_fallback(owner, repo_name, limit=max_contributors_per_repo)
    
    if not seed_contribs:
        print("No contributors found for seed repo!")
        return G
    
    # Add seed repo
    full_name = f"{owner}/{repo_name}"
    add_repo_clique(G, seed_contribs, full_name, graph_lock)
    visited_repos.add(full_name)
    
    # Initialize queue
    queue = collections.deque([(user, 1) for user in seed_contribs])
    
    while queue:
        # Collect batch
        batch = []
        with visited_lock:
            while queue and len(batch) < user_threads:
                user, depth = queue.popleft()
                
                if user in visited_users or depth > max_depth:
                    continue
                
                with processed_lock:
                    if processed_users >= max_users:
                        break
                    processed_users += 1
                    current_count = processed_users
                
                visited_users.add(user)
                batch.append((user, depth))
                print(f"[queue] {user} (depth={depth}) [{current_count}/{max_users}]")
        
        if not batch:
            break
        
        # Process batch with nested parallelism
        print(f"\n[batch] Processing {len(batch)} users...")
        
        with ThreadPoolExecutor(max_workers=user_threads) as executor:
            futures = {
                executor.submit(
                    process_user_parallel_repos,
                    user, depth,
                    max_repos_per_user,
                    max_contributors_per_repo,
                    repo_threads
                ): (user, depth)
                for user, depth in batch
            }
            
            for future in as_completed(futures):
                user, depth = futures[future]
                try:
                    _, results = future.result()
                    
                    for result in results:
                        repo_full = result['repo_full_name']
                        contribs = result['contributors']
                        
                        with visited_lock:
                            if repo_full in visited_repos:
                                continue
                            visited_repos.add(repo_full)
                        
                        print(f"  [repo] {repo_full} ({len(contribs)} contribs)")
                        add_repo_clique(G, contribs, repo_full, graph_lock)
                        
                        if depth + 1 <= max_depth:
                            with visited_lock:
                                for c in contribs:
                                    if c not in visited_users:
                                        queue.append((c, depth + 1))
                    
                except Exception as e:
                    print(f"[error] {user}: {e}")
        
        with processed_lock:
            if processed_users >= max_users:
                break
    
    return G


if __name__ == "__main__":
    SEED = "torvalds"
    SEED_REPO = "linux"
    MAX_DEPTH = 3
    MAX_USERS = 200000
    MAX_REPOS_PER_USER = 20
    MAX_CONTRIBS_PER_REPO = 30
    
    # Choose one:
    
    # Option 1: Basic threading (users in parallel)
    # G = crawl_from_repo_threaded(
    #     SEED, SEED_REPO,
    #     max_depth=MAX_DEPTH,
    #     max_users=MAX_USERS,
    #     max_repos_per_user=MAX_REPOS_PER_USER,
    #     max_contributors_per_repo=MAX_CONTRIBS_PER_REPO,
    #     max_threads=8
    # )
    
    # Option 2: Fast threading (users AND repos in parallel)
    G = crawl_from_repo_fast(
        SEED, SEED_REPO,
        max_depth=MAX_DEPTH,
        max_users=MAX_USERS,
        max_repos_per_user=MAX_REPOS_PER_USER,
        max_contributors_per_repo=MAX_CONTRIBS_PER_REPO,
        user_threads=6,   # Parallel users
        repo_threads=4    # Parallel repos per user
    )
    
    print(f"\n[info] nodes={G.number_of_nodes()} edges={G.number_of_edges()}")
    
    with open("repo_collab_graph_threaded.pkl", "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    print("Saved to repo_collab_graph_threaded.pkl")