import json
import networkx as nx
from pyvis.network import Network
import pickle


INPUT_FILE = "enriched_data.json"         # your input JSON
OUTPUT_PKL = "repo_collab_graph.pkl"     # networkx graph
OUTPUT_HTML = "repo_collab_graph.html"   # pyvis visualization


def load_data(filename):
    """Load contributors.json into a Python dict."""
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def build_graph(data):
    """
    Build graph from data formatted like:
    {
      "torvalds/linux": {
        "stargazers_count": ...,
        "forks_count": ...,
        "language": "C",
        "number_of_collaborators": 128,
        "authors": [...]
      }
    }
    """
    G = nx.Graph()

    # Add nodes
    for repo, info in data.items():
        G.add_node(
            repo,
            language=info.get("language"),
            stars=info.get("stargazers_count", 0),
            forks=info.get("forks_count", 0),
            authors=set(info.get("authors", [])),
            num_collab=info.get("number_of_collaborators", 0),
        )

    # Add edges for shared contributors
    repos = list(G.nodes())
    for i in range(len(repos)):
        for j in range(i + 1, len(repos)):
            r1 = repos[i]
            r2 = repos[j]

            a1 = G.nodes[r1]["authors"]
            a2 = G.nodes[r2]["authors"]

            common = a1.intersection(a2)
            if common:
                G.add_edge(r1, r2, weight=len(common), shared=list(common))

    return G


def visualize_graph(G, html_file):
    net = Network(
        height="900px",
        width="100%",
        directed=False,
        bgcolor="#1e1e1e",
        font_color="white",
    )

    net.barnes_hut()

    # Add nodes with tooltip info
    for node, attrs in G.nodes(data=True):
        tooltip = (
            f"{node}<br>"
            f"Language: {attrs.get('language')}<br>"
            f"Stars: {attrs.get('stars')}<br>"
            f"Forks: {attrs.get('forks')}<br>"
            f"Collaborators: {attrs.get('num_collab')}<br>"
            f"Authors: {len(attrs.get('authors', []))}"
        )

        net.add_node(
            node,
            label=node,
            title=tooltip,
            color="#76b5c5",
        )

    # Add edges
    for u, v, data in G.edges(data=True):
        weight = data.get("weight", 1)
        net.add_edge(
            u, v,
            value=weight,
            title=f"{weight} shared contributors",
            color="#ff6f91"
        )

    net.save_graph(html_file)
    print(f"[done] Saved visualization → {html_file}")


def main():
    print("[load] Loading data...")
    data = load_data(INPUT_FILE)
    print(f"[load] Loaded {len(data)} repos")

    print("[graph] Building graph...")
    G = build_graph(data)
    print(f"[graph] nodes={G.number_of_nodes()} edges={G.number_of_edges()}")

    #Degree Distribution
    degrees = [val for (node, val) in G.degree()]
    print(f"[info] Degree stats: min={min(degrees)} max={max(degrees)} avg={sum(degrees)/len(degrees):.2f}")

    with open(OUTPUT_PKL, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[save] Pickle saved → {OUTPUT_PKL}")

    print("[viz] Creating HTML visualization...")
    visualize_graph(G, OUTPUT_HTML)

    print("[done] All tasks completed!")


if __name__ == "__main__":
    main()