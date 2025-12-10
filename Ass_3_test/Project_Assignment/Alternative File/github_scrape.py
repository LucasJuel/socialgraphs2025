# gh_collab_multihop_live.py
import json
import os, time, requests, collections
import networkx as nx
import matplotlib.pyplot as plt
import csv
import threading
import pickle

TOKEN = os.getenv("TOKENLS")
HEAD = {"Accept": "application/vnd.github+json", **({"Authorization": f"token {TOKEN}"} if TOKEN else {})}



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

def get_json(url, params=None, max_retries=3):
    attempt = 0
    while True:
        attempt += 1
        try:
            r = requests.get(url, headers=HEAD, params=params or {}, timeout=30)
        except requests.RequestException as e:
            if attempt <= max_retries:
                time.sleep(min(2**attempt, 10)); continue
            print(f"[net] giving up on {url}: {e}"); return []
        # rate limit
        if r.status_code == 403 and "rate limit" in (r.text or "").lower():
            reset_ts = r.headers.get("X-RateLimit-Reset")
            wait = min(max(0, int(reset_ts or 0) - int(time.time()) + 2), 120)
            if attempt <= max_retries:
                print(f"[ratelimit] waiting {wait}s for {url}"); time.sleep(wait); continue
            print("[ratelimit] giving up"); return []
        if r.status_code != 200:
            preview = (r.text or "")[:200].replace("\n", " ")
            print(f"[error] {r.status_code} {r.reason} :: {url} :: {preview}...")
            return []
        try:
            return r.json()
        except ValueError:
            print(f"[decode] non-JSON from {url}"); return []

def get_repos(user, limit=None):
    data = get_json(f"{BASE}/users/{user}/repos",
                    {"type":"owner","sort":"updated","per_page":20})
    repos = [r for r in data if not r.get("fork")]
    return repos[:limit] if limit else repos

def get_contributors(owner, repo, limit=None):
    print(repo)
    totalData = []
    hasMore = True
    page = 1
    while hasMore:
        data = get_json(f"{BASE}/repos/{owner}/{repo}/contributors", {"per_page":100, "page": page})
        if len(data) == 100 and page < 6:
            page += 1
            totalData.extend(data)
        else:
            hasMore = False
            totalData.extend(data)
    #print([c for c in totalData if "login" not in c])
    print(totalData)
    contribs = [c["login"] for c in totalData if "login" in c]
    return contribs[:limit] if limit else contribs

import threading

def get_all_commit_authors(owner, repo, max_threads=6):
    authors_global = set()   # GitHub logins
    emails_global = set()    # (name, email) pairs

    next_page = 1            # shared page counter
    stop = False             # shared stop flag
    lock = threading.Lock()  # protects next_page, stop, and global sets

    def worker():
        nonlocal next_page, stop
        local_authors = set()
        local_emails = set()

        while True:
            # --- get a page number to work on ---
            with lock:
                if stop:
                    break
                page = next_page
                next_page += 1

            # --- fetch this page ---
            if page % 50 == 0:
                print(f"[thread] fetching page {page} for {owner}/{repo}")
            data = get_json(
                f"{BASE}/repos/{owner}/{repo}/commits",
                params={"per_page": 100, "page": page},
            )

            if not data:
                # nothing here → tell others to stop
                with lock:
                    stop = True
                break

            # --- process commits on this page ---
            for commit in data:
                # GitHub user object if available
                if commit.get("author"):
                    login = commit["author"].get("login")
                    if login:
                        local_authors.add(login)

                # raw git author identity
                c = commit.get("commit", {}).get("author", {})
                email = c.get("email")
                name = c.get("name")
                if email:
                    local_emails.add((name, email))

            # if fewer than 100 commits → last page
            if len(data) < 100:
                with lock:
                    stop = True
                break

        # --- merge local sets into global sets ---
        with lock:
            authors_global.update(local_authors)
            emails_global.update(local_emails)

    # --- create and start threads ---
    threads = []
    for _ in range(max_threads):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    # --- wait for all threads to finish ---
    for t in threads:
        t.join()

    return authors_global, emails_global

def add_repo_clique(G, contributors, repo_fullname):
    """Connect all contributors pairwise; bump weight if they met on multiple repos."""
    if not G.has_node(repo_fullname):
        G.add_node(repo_fullname, contributors=contributors)
    n = G.number_of_nodes()
    for i in range(n):
        for j in range(i+1, n):
            u, v = list(G.nodes(data=True))[i][1].get("contributors", []), list(G.nodes(data=True))[j][1].get("contributors", [])

            common = list(set(u).intersection(set(v)))
            w = len(common)
            if w == 0:
                continue
            G.add_edge(list(G.nodes(data=True))[i][0], list(G.nodes(data=True))[j][0], weight=w, users= common)

def crawl_from_repo(owner, repo_name,
                    max_depth=3,
                    max_users=500,
                    max_repos_per_user=10,
                    max_contributors_per_repo=50):
    """
    BFS starting from a specific repo.
    Depth 0 = seed repo's contributors
    Depth 1 = other repos those contributors work on
    etc.
    """
    G = nx.Graph()
    visited_users = set()
    visited_repos = set()
    processed_users = 0
    
    # Get initial contributors from seed repo
    print(f"[seed] Getting contributors from {owner}/{repo_name}")
    seed_contribs = get_contributors(owner, repo_name, limit=max_contributors_per_repo)
    
    if not seed_contribs:
        print("No contributors found for seed repo!")
        return G
    
    # Add seed repo clique
    full_name = f"{owner}/{repo_name}"
    add_repo_clique(G, seed_contribs, full_name)
    visited_repos.add(full_name)
    
    # Initialize queue with seed contributors at depth 1
    queue = collections.deque([(user, 1) for user in seed_contribs])
    
    while queue and processed_users < max_users:
        user, depth = queue.popleft()
        
        if user in visited_users:
            continue
        if depth > max_depth:
            continue
            
        visited_users.add(user)
        processed_users += 1
        print(f"[crawl] user={user} depth={depth} ({processed_users}/{max_users})")
        
        # Get this user's repos
        repos = get_repos(user, limit=max_repos_per_user)
        
        for r in repos:
            full = r["full_name"]
            if full in visited_repos:
                continue
            visited_repos.add(full)
            
            print(f"  [repo] {full}")
            contribs = get_contributors(r["owner"]["login"], r["name"], 
                                       limit=max_contributors_per_repo)
            if not contribs:
                continue
                
            add_repo_clique(G, contribs, full)
            
            # Enqueue new contributors for next depth
            if depth + 1 <= max_depth:
                for c in contribs:
                    if c not in visited_users:
                        queue.append((c, depth + 1))
    
    return G

if __name__ == "__main__":
    SEED = "memcached"          # your starting username
    SEED_REPO = ("memcached")  # owner, repo name
    MAX_DEPTH = 4               # 0 = only seed's repos, 1 = also their collaborators' repos, etc.
    MAX_USERS = 300            # cap total distinct users processed in BFS
    MAX_REPOS_PER_USER = 20     # cap repos per user
    MAX_CONTRIBS_PER_REPO = 50  # cap contributors per repo

    G = crawl_from_repo(
        SEED,
        SEED_REPO,
        max_depth=MAX_DEPTH,
        max_users=MAX_USERS,
        max_repos_per_user=MAX_REPOS_PER_USER,
        max_contributors_per_repo=MAX_CONTRIBS_PER_REPO,
    )
    print(f"[info] nodes={G.number_of_nodes()} edges={G.number_of_edges()}")



    with open("repo_collab_graph.pkl", "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    print("Saved to repo_collab_graph.pkl")

