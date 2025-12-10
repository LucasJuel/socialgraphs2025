# gh_collab_ultrafast.py
import json
import os
import csv
import requests
import pickle, time
import networkx as nx
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# ---------------------- CONFIG ----------------------
CSV_FILE = "top-100-starred.csv"
OUTFILE = "repo_collab_graph.pkl"
JSON_PATH = "repos_top_100_stars.json"


BASE = "https://api.github.com"

load_dotenv()

TOKENS = [
    os.getenv("TOKENLS"),
    os.getenv("TOKENSS"),
    os.getenv("TOKENLS1"),
    os.getenv("TOKENSS1"),
    #os.getenv("TOKENX1"),
    #os.getenv("TOKENX2"),
]

HEADERS = [
    {"Accept": "application/vnd.github+json",
     **({"Authorization": f"token " + t} if t else {})}
    for t in TOKENS
]

MAX_THREADS = 8   # concurrency level for crawling commits
TIMEOUT = 15
COUNTER = 0

# ---------------------- HELPERS ----------------------

def get_json(url, headers, params=None):
    time.sleep(0.1)  # to avoid hitting rate limits too fast
    global COUNTER
    COUNTER += 1
    hit_counter = 0
    current_header = headers
    rate_hit = True
    print(f"   [request #{COUNTER}]")
    while rate_hit:
        rate_hit = False
        try:
            r = requests.get(url, headers=current_header, params=params or {}, timeout=TIMEOUT)

            if r.status_code == 403 and "rate limit" in (r.text or "").lower():
                rate_hit = True
                reset_ts = r.headers.get("X-RateLimit-Reset")
                wait = max(0, int(reset_ts or 0) - int(time.time()) + 2)
                print(f"[ratelimit] wait={wait}s url={url} message={r.json().get('message')}")
                current_header = HEADERS[(COUNTER + 1) % len(HEADERS)]
                hit_counter += 1
                time.sleep(10)
                continue


            if r.status_code != 200:
                return None, r


            return r.json(), r
        except:
            return None, None


def discover_total_commit_pages(owner, repo):
    """Fetch only the first page to inspect Link headers and discover total pages."""
    headers = HEADERS[0]
    url = f"{BASE}/repos/{owner}/{repo}/commits"
    _, resp = get_json(url, headers, params={"per_page": 100, "page": 1})

    if resp is None:
        return 1

    link = resp.headers.get("Link")
    if not link:
        return 1

    # Example: <...page=492>; rel="last"
    for part in link.split(","):
        if 'rel="last"' in part:
            last_url = part.split(";")[0].strip()[1:-1]
            last_page = int(last_url.split("page=")[-1])
            return last_page

    return 1


# ---------------------- ULTRA-FAST FULL COMMIT CRAWLER ----------------------

def crawl_commit_page(owner, repo, page, token_id):
    """Fetch one commit page."""
    headers = HEADERS[token_id % len(HEADERS)]
    url = f"{BASE}/repos/{owner}/{repo}/commits"
    data, resp = get_json(url, headers, params={"per_page": 100, "page": page})

    # Blocked or no data?
    if not data or isinstance(data, dict):
        return []

    authors = []
    for commit in data:
        a = commit.get("author")
        if a and a.get("login"):
            authors.append(a["login"])

    return authors


def get_all_commits_ultra_fast(owner, repo):
    """Fetch *all* commit authors using parallel crawl."""
    print(f"[ultra-fast] discovering total commit pages for {owner}/{repo}...")

    total_pages = discover_total_commit_pages(owner, repo)
    print(f"[ultra-fast] {total_pages} pages of commits detected")

    authors = set()

    # FULL PARALLEL CRAWL
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {}
        for p in range(1, total_pages + 1):
            futures[executor.submit(crawl_commit_page, owner, repo, p, p)] = p

        for fut in as_completed(futures):
            page = futures[fut]
            try:
                page_authors = fut.result()
                authors.update(page_authors)

                if page % 100 == 0:
                    print(f"   crawled {page}/{total_pages} pages")
            except Exception as e:
                print(f"   page {page} failed → retry later")

    print(f"[ultra-fast] TOTAL authors from full commits: {len(authors)}")
    return list(authors)


# ---------------------- CONTRIBUTORS ENDPOINT ----------------------

def get_contributors_endpoint(owner, repo):
    """Try fast /contributors first."""
    contributors = []
    page = 1
    token = 0

    while True:
        headers = HEADERS[token % len(HEADERS)]
        token += 1

        url = f"{BASE}/repos/{owner}/{repo}/contributors"
        data, _ = get_json(url, headers, params={"per_page": 100, "page": page})

        if not data:
            break

        if isinstance(data, dict) and "message" in data:
            return []

        contributors += [c["login"] for c in data if "login" in c]

        if len(data) < 100:
            break

        page += 1

    return list(set(contributors))


# ---------------------- COMBINED CONTRIBUTOR FETCHER ----------------------

def get_contributors(repo_full):
    owner, repo = repo_full.split("/", 1)

    # Try fast method first
    contribs = get_contributors_endpoint(owner, repo)
    if contribs:
        print(f"[contributors] using endpoint contributors: {len(contribs)} users")
        return contribs

    # Fallback → ultra-fast full commit crawl
    print(f"[contributors] falling back to full commit crawl...")
    return get_all_commits_ultra_fast(owner, repo)


# ---------------------- CSV ----------------------

def load_repos_from_csv(path):
    repos = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repos.append({
                "repo_full": row["username"] + "/" + row["repo_name"],
                "source": row["item"],
                "stars": int(row["stars"]),
                "forks": int(row["forks"]),
                "language": row["language"],
            })
    return repos


# ---------------------- BUILD GRAPH ----------------------

def build_repo_graph(repos):
    G = nx.Graph()
    print(f"[info] loading contributors for {len(repos)} repos")

    #Load existing repos from JSON to avoid re-fetching
    if os.path.exists(JSON_PATH):
        print(f"[info] loading existing repo data from {JSON_PATH}...")
        with open(JSON_PATH, "r", encoding="utf-8") as jf:
            existing_repos = json.load(jf)     
            #print(existing_repos[:3])   
            existing_repos = {record["repository"]: record for record in existing_repos}



        for repo in repos:
           
            full = repo["repo_full"]
            language = repo["language"]

            if not language:
                print(f"[skip] no language for {full}, skipping...")
                continue

            print(f"\n[repo] fetching contributors for {full}")
            if repo["repo_full"] in existing_repos:
                print(f"[skip] already have data for {repo['repo_full']}, skipping...")
                contribs = existing_repos[repo["repo_full"]]["contributors"]
            else: 
                contribs = get_contributors(full)

            repo_data = {}
            for node, attrs in G.nodes(data=True):
                serializable = {k: (list(v) if isinstance(v, set) else v) for k, v in attrs.items()}
                serializable["neighbors"] = list(G[node].keys())
                repo_data[node] = serializable

            record = {
                "repository": full,
                "stars": repo["stars"],
                "forks": repo["forks"],
                "language": language,
                "contributors": contribs,
                "number_of_collaborators": len(contribs),
            }

            print(f"[append] Added {full}")


            G.add_node(
                full,
                contributors=contribs,
                stars=repo["stars"],
                forks=repo["forks"],
                language=repo["language"],
                number_of_collaborators=len(contribs)
            )

    print("\n[info] building edges...")
    nodes = list(G.nodes())

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            r1, r2 = nodes[i], nodes[j]
            c1 = set(G.nodes[r1]["contributors"])
            c2 = set(G.nodes[r2]["contributors"])
            common = c1.intersection(c2)

            if common:
                G.add_edge(r1, r2, weight=len(common), shared=list(common))

    return G


# ---------------------- MAIN ----------------------

if __name__ == "__main__":
    print("HEADERS:", HEADERS)
    repos = load_repos_from_csv(CSV_FILE)
    print(f"[csv] Loaded {len(repos)} repositories")

    G = build_repo_graph(repos)

    print(f"\n[info] final graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    with open(OUTFILE, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"[saved] {OUTFILE}")
