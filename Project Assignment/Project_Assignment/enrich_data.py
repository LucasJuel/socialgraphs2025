import json, requests, os, base64
from dotenv import load_dotenv

JSON_PATH = "repos_top_100_stars.json"
ENRICHED_JSON_PATH = "repos_top_100_stars_enriched.json"
BASE_URL = "https://api.github.com"

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

def enrich_data(data):
    counter = 0
    # Get readme from each repo and add to data
    for repo in data:
        full_name = repo["repository"]
        print(f"Fetching README for {full_name}...")

        data = f"/repos/{full_name}/readme"
        url = BASE_URL + data
        response = requests.get(url, headers=HEADERS[0])
        if response.status_code == 200:
            readme_data = response.json()
            repo["readme"] = base64.b64decode(readme_data.get("content", "")).decode("utf-8", errors="ignore")
        else:
            repo["readme"] = None
        counter += 1
        print(f"Processed {counter}/{len(data)} repositories.")

    return data

if __name__ == "__main__":
    #Read from JSON_PATH
    with open(JSON_PATH, "r", encoding="utf-8") as jf:
        data = json.load(jf)
    
    enrich_data(data)
    #Write back to JSON_PATH
    with open(ENRICHED_JSON_PATH, "w", encoding="utf-8") as jf:
        json.dump(data, jf, indent=4)

    