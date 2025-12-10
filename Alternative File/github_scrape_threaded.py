# gh_collab_multihop_live.py
import json
import os, time, requests, collections
import networkx as nx
import csv
import threading
import pickle
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal, os, sys


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

HEAD_LIST = [HEAD, HEAD1, HEAD2, HEAD3]
RATELIMIT_COUNTER = 0


# ---------------------- CSV PARSER ----------------------

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


# ---------------------- SAVE CONTRIBUTORS WITH DEPTH ----------------------

save_lock = threading.Lock()

def save_repo_contribs(owner, repo, authors, depth, filename="contributors.json"):
    entry = {
        f"{owner}/{repo}": {
            "authors": list(authors),
            "depth": depth
        }
    }

    with save_lock:
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        else:
            data = {}

        data.update(entry)

        tmpfile = filename + ".tmp"
        with open(tmpfile, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmpfile, filename)

        print(f"[save][repo {owner}/{repo}] stored {len(authors)} authors depth={depth}")


# ---------------------- GET JSON ----------------------

def get_json(url, params=None, max_retries=20, worker_id=0, stop_event=None):
    attempt = 0
    HEADINT = HEAD_LIST[worker_id % len(HEAD_LIST)]
    while True:
        attempt += 1
        try:
            r = requests.get(url, headers=HEADINT, params=params or {}, timeout=30)
        except requests.RequestException as e:
            print(f"[net][worker {worker_id}] FAIL {url} attempt={attempt} → {e}")
            if attempt <= max_retries:
                time.sleep(min(2**attempt, 10))
            return None

        remaining = r.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            print(f"[rate][worker {worker_id}] {url} remaining={remaining}")

        if r.status_code == 403 and "rate limit" in (r.text or "").lower():
            reset_ts = r.headers.get("X-RateLimit-Reset")
            wait = max(0, int(reset_ts or 0) - int(time.time()) + 2)
            HEADINT = HEAD_LIST[(worker_id + 1) % len(HEAD_LIST)]
            if attempt <= max_retries:
                if stop_event is None:
                    print(f"[ratelimit][worker {worker_id}] wait={wait}s attempt={attempt} url={url}")
                    time.sleep(5)
                else:
                    if stop_event.wait(5):
                        return None
                continue
            return None

        if r.status_code != 200:
            return None

        try:
            return r.json()
        except ValueError:
            return None


# ---------------------- REPOS FOR USER ----------------------

def get_repos(user, limit=None):
    data = get_json(
        f"{BASE}/users/{user}/repos",
        {"type": "owner", "sort": "updated", "per_page": 50}
    )
    repos = [r for r in data if not r.get("fork")]
    return repos[:limit] if limit else repos


# ---------------------- COLLECT AUTHORS FROM COMMITS ----------------------

def get_all_commit_authors(owner, repo, max_threads=1):
    authors_global = set()
    emails_global = set()
    next_page = 1
    stop_event = threading.Event()
    lock = threading.Lock()

    def worker(worker_id):
        nonlocal next_page
        local_auth = set()
        local_emails = set()

        while not stop_event.is_set():
            with lock:
                if stop_event.is_set():
                    break
                page = next_page
                next_page += 1

            data = get_json(
                f"{BASE}/repos/{owner}/{repo}/commits",
                params={"per_page": 100, "page": page},
                worker_id=worker_id,
                stop_event=stop_event
            )

            if not data:
                stop_event.set()
                break

            for commit in data:
                if commit.get("author"):
                    login = commit["author"].get("login")
                    if login:
                        local_auth.add(login)

                c = commit.get("commit", {}).get("author", {})
                email = c.get("email")
                if email:
                    local_emails.add((c.get("name"), email))

            with lock:
                authors_global.update(local_auth)
                emails_global.update(local_emails)
                local_auth.clear()
                local_emails.clear()

                if len(authors_global) >= 100:
                    stop_event.set()

            if len(data) < 100:
                stop_event.set()
                break

    threads = []
    for wid in range(max_threads):
        t = threading.Thread(target=worker, args=[wid], daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # commits fallback depth = 0
    save_repo_contribs(owner, repo, authors_global, depth=0)

    return authors_global, emails_global


# ---------------------- CONTRIBUTORS WITH FALLBACK ----------------------

def get_contributors_with_fallback(owner, repo, limit=None, max_threads=6):
    full_name = f"{owner}/{repo}"
    if full_name in EXISTING_REPOS:
        return EXISTING_REPOS[full_name]["authors"]

    totalData = []
    page = 1
    hasMore = True

    while hasMore:
        data = get_json(
            f"{BASE}/repos/{owner}/{repo}/contributors",
            {"per_page": 100, "page": page},
            worker_id=1
        )

        if not data:
            break

        if isinstance(data, dict) and "message" in data:
            authors, _ = get_all_commit_authors(owner, repo, max_threads=2)
            return list(authors)

        totalData.extend(data)

        if len(data) == 100 and page < 6:
            page += 1
        else:
            hasMore = False

    if not totalData:
        authors, _ = get_all_commit_authors(owner, repo, max_threads=2)
        return list(authors)

    contribs = [c["login"] for c in totalData if "login" in c]
    return contribs[:limit] if limit else contribs


# ---------------------- ADD REPO TO GRAPH ----------------------

def add_repo_clique(G, contributors, repo_fullname, depth, lock):
    with lock:
        if not G.has_node(repo_fullname):
            G.add_node(repo_fullname, contributors=contributors, depth=depth)

        for other_node, other_data in list(G.nodes(data=True)):
            if other_node == repo_fullname:
                continue

            other_contribs = other_data.get("contributors", [])
            common = list(set(contributors).intersection(other_contribs))
            if len(common) > 0:
                if G.has_edge(repo_fullname, other_node):
                    G[repo_fullname][other_node]['weight'] += len(common)
                else:
                    G.add_edge(repo_fullname, other_node, weight=len(common), users=common)


# ---------------------- PROCESS REPOS FOR USER ----------------------

def process_single_repo(owner, name, full_name, max_contributors):
    if full_name in EXISTING_REPOS:
        return full_name, EXISTING_REPOS[full_name]["authors"]

    contribs = get_contributors_with_fallback(owner, name, limit=max_contributors)
    return full_name, contribs


def process_user_parallel_repos(user, depth, max_repos_per_user, max_contributors_per_repo, repo_threads=4):
    repos = get_repos(user, limit=max_repos_per_user)
    if not repos:
        return user, []

    results = []

    with ThreadPoolExecutor(max_workers=repo_threads) as executor:
        futures = {
            executor.submit(
                process_single_repo,
                r["owner"]["login"], r["name"], r["full_name"], max_contributors_per_repo
            ): r["full_name"] for r in repos
        }

        for fut in as_completed(futures):
            try:
                full_name, contribs = fut.result()
                if contribs:
                    results.append({
                        "repo_full_name": full_name,
                        "contributors": contribs,
                        "depth": depth
                    })
            except:
                pass

    return user, results


# ---------------------- BFS CRAWLER ----------------------

def crawl_from_repo_fast(owner, repo_name,
                          max_depth=3,
                          max_users=500,
                          max_repos_per_user=10,
                          max_contributors_per_repo=50,
                          user_threads=6,
                          repo_threads=4):

    G = nx.Graph()
    graph_lock = threading.Lock()

    visited_users = set()
    visited_repos = set()
    visited_lock = threading.Lock()

    processed_users = 0
    processed_lock = threading.Lock()

    seed_contribs = get_contributors_with_fallback(owner, repo_name, limit=max_contributors_per_repo)
    full_name = f"{owner}/{repo_name}"

    add_repo_clique(G, seed_contribs, full_name, depth=0, lock=graph_lock)
    save_repo_contribs(owner, repo_name, seed_contribs, depth=0)
    visited_repos.add(full_name)

    queue = collections.deque([(user, 1) for user in seed_contribs])

    while queue:
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

                visited_users.add(user)
                batch.append((user, depth))

        if not batch:
            break

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

            for fut in as_completed(futures):
                user, depth = futures[fut]

                try:
                    _, results = fut.result()
                    for result in results:
                        repo_full = result["repo_full_name"]
                        contribs = result["contributors"]

                        with visited_lock:
                            if repo_full in visited_repos:
                                continue
                            visited_repos.add(repo_full)

                        add_repo_clique(G, contribs, repo_full, depth=depth, lock=graph_lock)

                        owner2, repo2 = repo_full.split("/", 1)
                        save_repo_contribs(owner2, repo2, contribs, depth)

                        if depth + 1 <= max_depth:
                            for c in contribs:
                                if c not in visited_users:
                                    queue.append((c, depth + 1))

                except:
                    pass

    return G


# ---------------------- LOAD CACHE ----------------------

def load_existing_contribs(filename="contributors.json"):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


# ---------------------- MAIN ----------------------

if __name__ == "__main__":
    SEED = "torvalds"
    SEED_REPO = "linux"
    MAX_DEPTH = 3
    MAX_USERS = 200000
    MAX_REPOS_PER_USER = 20
    MAX_CONTRIBS_PER_REPO = 30

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    EXISTING_REPOS = load_existing_contribs()
    print(f"[cache] loaded {len(EXISTING_REPOS)} repos from contributors.json")

    G = crawl_from_repo_fast(
        SEED, SEED_REPO,
        max_depth=MAX_DEPTH,
        max_users=MAX_USERS,
        max_repos_per_user=MAX_REPOS_PER_USER,
        max_contributors_per_repo=MAX_CONTRIBS_PER_REPO,
        user_threads=6,
        repo_threads=4
    )

    print(f"[info] final graph nodes={G.number_of_nodes()} edges={G.number_of_edges()}")

    with open("repo_collab_graph_threaded.pkl", "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("[saved] repo_collab_graph_threaded.pkl")