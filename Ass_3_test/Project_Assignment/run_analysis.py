# Read from enriched_data.jsomn
import json
import networkx as nx
from collections import Counter

FILE_URL = 'enriched_data.json'


def load_from_json(file):
    with open(file, "r") as f:
        return json.load(f)
    


#Create networkX graph based on data
def create_network_x_graph(data):
    G = nx.Graph()
    for key in list(data.keys())[:200]:
        firstKey = key
        print(f"First key in data: {firstKey}")
        #print(data[firstKey])
        stars = data[firstKey].get("stargazers_count", None)
        forks = data[firstKey].get("forks_count", None)
        language = data[firstKey].get("language", None)
        authors = data[firstKey].get("authors", [])
        num_collab = data[firstKey].get("number_of_collaborators", 0)
        #print(f"Number of collaborators: {num_collab}, Authors: {authors}")
        G.add_node(
            firstKey,
            language=language,
            stars=stars,
            forks=forks,
            authors=list(set(authors)),
            num_collab=num_collab,
        )

        #Add edges for shared contributors
        repos = list(G.nodes())
        for i in range(len(repos)):
            for j in range(i + 1, len(repos)):
                r1 = repos[i]
                r2 = repos[j]

                a1 = set(G.nodes[r1]["authors"])
                a2 = set(G.nodes[r2]["authors"])

                common = a1.intersection(a2)
                if common:
                    G.add_edge(r1, r2, weight=len(common), shared=list(common))
        
        #print(f"Stars: {stars}, Forks: {forks}, Language: {language}")

    return G




if __name__ == "__main__":
    data = load_from_json(FILE_URL)
    G = create_network_x_graph(data)
    print(f"Graph created with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    # Example: Print node attributes for the first node
    first_node = list(G.nodes())[0]
    print(f"Attributes of the first node ({first_node}): {G.nodes[first_node]}")
    # Visualize the graph (optional) with pyvis
    from pyvis.network import Network
    net = Network(notebook=True)
    net.from_nx(G)
    net.show("repo_collab_graph.html")

    #Create communities.
    community = nx.community.louvain_communities(G, weight='weight')
    print(f"Detected {len(community)} communities.")
    sorted_communities = [community for community in community if len(community) > 1]
    for i, comm in enumerate(sorted_communities):
        langs = [G.nodes[n].get("language", "Unknown") for n in comm]
        counts = Counter(langs)
        dominant_lang, dominant_count = counts.most_common(1)[0]
        purity = dominant_count / len(comm)
        
        print(f"\nCommunity {i}:")
        print(f"  Size: {len(comm)} repos")
        print(f"  Languages: {counts}")
        print(f"  Dominant language: {dominant_lang} ({purity:.2%} purity)")
    


    
        
