import pickle
import networkx as nx
from pyvis.network import Network


def visualize_top_pyvis(G, top_n=100, filename="network_top.html"):
    """Visualize only the top N most connected nodes."""
    
    # Get top N nodes by degree
    degrees = dict(G.degree())
    top_nodes = sorted(degrees, key=degrees.get, reverse=True)[:top_n]
    
    # Create subgraph
    H = G.subgraph(top_nodes).copy()
    
    print(f"Visualizing top {H.number_of_nodes()} nodes, {H.number_of_edges()} edges")
    
    # Create PyVis network
    net = Network(
        height="900px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white"
    )
    
    net.barnes_hut(
        gravity=-8000,
        central_gravity=0.5,
        spring_length=150,
        spring_strength=0.04,
        damping=0.9
    )
    
    degrees_sub = dict(H.degree())
    max_deg = max(degrees_sub.values(), 0)
    
    # Color gradient based on degree
    for node in H.nodes():
        deg = degrees_sub[node]
        ratio = deg / max_deg
        
        # Color: low degree = blue, high degree = red
        r = int(255 * ratio)
        b = int(255 * (1 - ratio))
        color = f"rgb({r}, 100, {b})"
        
        size = 15 + 50 * ratio
        
        net.add_node(
            node,
            label=node,
            size=size,
            color=color,
            title=f"{node}\nDegree: {deg}"
        )
    
    for u, v, data in H.edges(data=True):
        weight = data.get('weight', 1)
        
        # Get repos if available
        repos = data.get('repos', [])
        if isinstance(repos, set):
            repos = list(repos)
        
        # Build hover text
        hover_text = f"Weight: {weight}\n{u} ↔ {v}"
        if repos:
            hover_text += f"\n\nShared repos ({len(repos)}):\n• " + "\n• ".join(repos[:10])
            if len(repos) > 10:
                hover_text += f"\n... and {len(repos) - 10} more"
        
        net.add_edge(
            u, v,
            value=weight,                      # Edge thickness
            title=hover_text,                  # Hover text ← THIS IS THE KEY
            color="rgba(200,200,200,0.3)"
        )
    
    net.show_buttons(filter_=['physics'])
    net.save_graph(filename)
    print(f"Saved to {filename}")



if __name__ == "__main__":
    # Load the graph
    GRAPH_FILE = "repo_collab_graph_threaded.pkl"
    
    with open(GRAPH_FILE, "rb") as f:
        G = pickle.load(f)
    
    print(f"Full graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    
    # Extract largest component
    G_largest = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    #Make a subgraph exluding edges with weight less than 2
    #edges_to_remove = [(u, v) for u, v, d in G_largest.edges(data=True) if d.get('weight', 1) < 2]
    #G_largest.remove_edges_from(edges_to_remove)
    # Remove isolated nodes
    #Remove nodes where all edges have weight less than 2
    nodes_to_remove = [node for node in G_largest.nodes() if all(d.get('weight', 1) < 2 for _, _, d in G_largest.edges(node, data=True))]
    G_largest.remove_nodes_from(nodes_to_remove)



    isolated_nodes = list(nx.isolates(G_largest))
    G_largest.remove_nodes_from(isolated_nodes)

    #visualize edge weight

    
    print(f"Largest component: {G_largest.number_of_nodes()} nodes, {G_largest.number_of_edges()} edges")
    
    # =========== PYVIS VISUALIZATION ===========

    visualize_top_pyvis(G_largest, top_n=500, filename="repo_network.html")
    
    # # Create PyVis network
    # net = Network(
    #     height="900px",
    #     width="100%",
    #     bgcolor="#222222",      # Dark background
    #     font_color="white",
    #     notebook=False          # Set True if using Jupyter
    # )
    
    # # Physics settings for better layout
    # net.barnes_hut(
    #     gravity=-5000,
    #     central_gravity=0.3,
    #     spring_length=100,
    #     spring_strength=0.05,
    #     damping=0.9
    # )
    
    # # Calculate node degrees for sizing
    # degrees = dict(G_largest.degree())
    # max_degree = max(degrees.values())
    
    # # Add nodes with size based on degree
    # for node in G_largest.nodes():
    #     size = 10 + 40 * (degrees[node] / max_degree)  # Scale 10-50
    #     net.add_node(
    #         node,
    #         label=node,
    #         size=size,
    #         title=f"{node}\nConnections: {degrees[node]}"  # Hover text
    #     )
    
    # # Add edges
    # for u, v, data in G_largest.edges(data=True):
    #     weight = data.get('weight', 1)
    #     repos = data.get('repos', [])
    #     if isinstance(repos, set):
    #         repos = list(repos)
        
    #     net.add_edge(
    #         u, v,
    #         value=weight,  # Edge thickness
    #         title=f"Weight: {weight}\nRepos: {', '.join(repos[:5])}"  # Hover text
    #     )
    
    # # Enable physics controls in the UI
    # net.show_buttons(filter_=['physics'])
    

    # # Save and open
    # net.save_graph("network_interactive.html")
    # print("Saved to network_interactive.html — open in browser!")