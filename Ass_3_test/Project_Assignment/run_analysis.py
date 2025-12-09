# Read from enriched_data.jsomn
import json
import networkx as nx
from collections import Counter
import igraph as ig
import pickle, os
import matplotlib.pyplot as plt

FILE_URL = 'enriched_data.json'


def load_from_json(file):
    with open(file, "r") as f:
        return json.load(f)
    


#Create networkX graph based on data
def create_network_x_graph(data):
    G = nx.Graph()
    for key in list(data.keys()):
        firstKey = key
        #print(f"First key in data: {firstKey}")
        #print(data[firstKey])
        stars = data[firstKey].get("stargazers_count", None)
        forks = data[firstKey].get("forks_count", None)
        language = data[firstKey].get("language", None)
        if language is None:
            continue
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
    currentProgess = 0
    for i in range(len(repos)):
        for j in range(i + 1, len(repos)):
            currentProgess += 1
            if currentProgess % 100000 == 0:
                print(f"Processed {currentProgess} repo pairs... out of {len(repos)*(len(repos)-1)//2}")
            r1 = repos[i]
            r2 = repos[j]

            a1 = set(G.nodes[r1]["authors"])
            a2 = set(G.nodes[r2]["authors"])

            common = a1.intersection(a2)
            if common:
                G.add_edge(r1, r2, weight=len(common), shared=list(common))
        
        #print(f"Stars: {stars}, Forks: {forks}, Language: {language}")

    return G


GRAPH_FILE = "collab_graph.pkl"

def load_or_create_graph(data):
    # 1. If file exists → load it
    if os.path.exists(GRAPH_FILE):
        print("Loading existing graph from collab_graph.pkl...")
        with open(GRAPH_FILE, "rb") as f:
            G = pickle.load(f)
        print(f"Loaded graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
        return G
    
    # 2. Else → create graph and save
    print("Graph file not found — creating graph...")
    G = create_network_x_graph(data)

    print("Saving graph to collab_graph.pkl...")
    with open(GRAPH_FILE, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("Graph saved.")
    return G




if __name__ == "__main__":
    data = load_from_json(FILE_URL)
    G = load_or_create_graph(data)
    print(f"Graph created with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    # Visualize the graph (optional) with pyvis
    #from pyvis.network import Network
    #net = Network(notebook=True)
    #net.from_nx(G)
    #net.show("repo_collab_graph.html")

    #Create communities.
    community = nx.community.louvain_communities(G, weight='weight')
    #g = ig.Graph.TupleList(G.edges(data=True), directed=False, weights=True)
    #print(f"Converted to igraph with {g.vcount()} vertices and {g.ecount()} edges.")
    #community = g.community_multilevel(weights=g.es['weight'])
    print(f"Detected {len(community)} communities.")
    sorted_communities = [community for community in community if len(community) > 1]
    community_objects = sorted(sorted_communities, key=len, reverse=True)
    for i, comm in enumerate(sorted_communities):
        # Find dominant language and purity
        langs = [G.nodes[n].get("language", "Unknown") for n in comm]
        counts = Counter(langs)
        dominant_lang, dominant_count = counts.most_common(1)[0]
        purity = dominant_count / len(comm)
        
        # print(f"\nCommunity {i}:")
        # print(f"  Size: {len(comm)} repos")
        # print(f"  Languages: {counts}")
        # print(f"  Dominant language: {dominant_lang} ({purity:.2%} purity)")

        community_object = {
            "size": len(comm),
            "languages": counts,
            "dominant_language": dominant_lang,
            "purity": purity,
            #"repos": list(comm),
        }

        community_objects[i] = community_object

    sorted_communities = sorted(community_objects, key=lambda x: x.get("size", None), reverse=True)
    print(sorted_communities[:5])  # Print top 5 communities
    #Find average degree based on language
    language_degrees = {}
    for node, attrs in G.nodes(data=True):
        lang = attrs.get("language", "Unknown")
        degree = G.degree(node)
        if lang not in language_degrees:
            language_degrees[lang] = []
        language_degrees[lang].append(degree)

    print("\nAverage degree by programming language:")
    for lang, degrees in language_degrees.items():
        avg_degree = sum(degrees) / len(degrees)
        print(f"  {lang}: {avg_degree:.2f}")

    #Top languages based on number of repos
    lang_counter = Counter()
    for node, attrs in G.nodes(data=True):
        lang = attrs.get("language", "Unknown")
        lang_counter[lang] += 1

    #Bar chart showing language popularity
    plt.figure(figsize=(10, 6))
    langs, counts = zip(*lang_counter.most_common(10))
    plt.bar(langs, counts, color='skyblue')
    plt.xlabel('Programming Language')
    plt.ylabel('Number of Repositories')
    plt.title('Top 10 Programming Languages by Number of Repositories')
    plt.xticks(rotation=45)
    
    print("\nTop programming languages by number of repositories:")
    for lang, count in lang_counter.most_common(10):
        print(f"  {lang}: {count} repositories")
# Repos med samme sprog, deler contributors (modularity)

    
        
