import re
import os
import networkx as nx
from pathlib import Path
import json

def load_artist_list(filename='artists_clean.txt'):
    """Load the clean list of artists."""
    with open(filename, 'r', encoding='utf-8') as f:
        artists = [line.strip() for line in f if line.strip()]
    return artists

def load_wiki_pages(directory='wiki_pages'):
    """Load all downloaded wiki pages."""
    wiki_data = {}
    
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):
            filepath = os.path.join(directory, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                # We need to map filenames back to artist names
                # This is a bit tricky due to sanitization
                wiki_data[filename[:-4]] = content  # Remove .txt
    
    return wiki_data

def extract_wiki_links(text):
    """Extract all internal Wikipedia links from wikitext."""
    # Pattern to match [[Link]] or [[Link|Display Text]]
    pattern = r'\[\[([^\[\]|]+?)(?:\|[^\[\]]+)?\]\]'
    matches = re.findall(pattern, text)
    
    # Clean up the links
    links = []
    for match in matches:
        # Remove any section anchors (e.g., "Page#Section" -> "Page")
        link = match.split('#')[0].strip()
        if link:
            links.append(link)
    
    return links

def build_artist_network(artist_list, wiki_data):
    """Build a directed graph of artist connections."""
    
    # Create a set of valid artist names for faster lookup
    artist_set = set(artist_list)
    
    # Also create variations to handle naming differences
    artist_variations = {}
    for artist in artist_list:
        # Store original
        artist_variations[artist] = artist
        # Store with underscores
        artist_variations[artist.replace(' ', '_')] = artist
        # Store sanitized version
        sanitized = artist.replace('/', '_').replace('–', '-')
        artist_variations[sanitized] = artist
        artist_variations[sanitized.replace(' ', '_')] = artist
    
    # Create directed graph
    G = nx.DiGraph()
    
    # Add all artists as nodes
    for artist in artist_list:
        G.add_node(artist)
    
    # Track statistics
    links_found = {}
    
    # Process each artist's page
    for filename, content in wiki_data.items():
        # Try to map filename back to artist name
        source_artist = None
        
        # Try different variations
        if filename in artist_variations:
            source_artist = artist_variations[filename]
        elif filename.replace('_', ' ') in artist_variations:
            source_artist = artist_variations[filename.replace('_', ' ')]
        
        if not source_artist:
            print(f"Warning: Could not map {filename} to an artist")
            continue
        
        # Extract all links from this page
        all_links = extract_wiki_links(content)
        
        # Filter to only links pointing to other artists
        artist_links = []
        for link in all_links:
            # Check if this link points to another artist
            if link in artist_set:
                artist_links.append(link)
                G.add_edge(source_artist, link)
            elif link.replace('_', ' ') in artist_set:
                target = link.replace('_', ' ')
                artist_links.append(target)
                G.add_edge(source_artist, target)
        
        links_found[source_artist] = artist_links
        
        # Add word count as node attribute
        word_count = len(content.split())
        G.nodes[source_artist]['word_count'] = word_count
        
        print(f"Processed {source_artist}: {len(artist_links)} links to other artists")
    
    return G, links_found

def clean_network(G):
    """Remove isolated nodes and extract largest component."""
    
    # Remove isolated nodes (no in or out edges)
    isolated = list(nx.isolates(G))
    G.remove_nodes_from(isolated)
    print(f"Removed {len(isolated)} isolated nodes")
    
    # Extract largest weakly connected component
    components = list(nx.weakly_connected_components(G))
    largest_component = max(components, key=len)
    G_largest = G.subgraph(largest_component).copy()
    
    print(f"Largest component has {G_largest.number_of_nodes()} nodes")
    print(f"Original had {G.number_of_nodes()} nodes after removing isolates")
    
    return G_largest

def main():
    # Load artist list
    print("Loading artist list...")
    artists = load_artist_list()
    print(f"Loaded {len(artists)} artists")
    
    # Load wiki pages
    print("\nLoading wiki pages...")
    wiki_data = load_wiki_pages()
    print(f"Loaded {len(wiki_data)} wiki pages")
    
    # Build network
    print("\nBuilding network...")
    G, links = build_artist_network(artists, wiki_data)
    
    print(f"\nInitial network:")
    print(f"  Nodes: {G.number_of_nodes()}")
    print(f"  Edges: {G.number_of_edges()}")
    
    # Clean network
    print("\nCleaning network...")
    G_clean = clean_network(G)
    
    print(f"\nFinal network:")
    print(f"  Nodes: {G_clean.number_of_nodes()}")
    print(f"  Edges: {G_clean.number_of_edges()}")
    
    # Save the network
    nx.write_gexf(G_clean, 'rock_artist_network.gexf')
    print("\nNetwork saved to 'rock_artist_network.gexf'")
    
    # Also save as edge list for easier inspection
    with open('network_edges.txt', 'w', encoding='utf-8') as f:
        for source, target in G_clean.edges():
            f.write(f"{source} -> {target}\n")
    
    return G_clean

if __name__ == "__main__":
    G = main()
    
    # Print some basic statistics
    print("\n=== Network Statistics ===")
    print(f"Number of nodes: {G.number_of_nodes()}")
    print(f"Number of edges: {G.number_of_edges()}")
    print(f"Average degree: {sum(dict(G.degree()).values()) / G.number_of_nodes():.2f}")
    
    # Top 5 by out-degree (most references to others)
    out_degrees = dict(G.out_degree())
    top_out = sorted(out_degrees.items(), key=lambda x: x[1], reverse=True)[:5]
    print("\nTop 5 by out-degree (most links to others):")
    for artist, degree in top_out:
        print(f"  {artist}: {degree}")
    
    # Top 5 by in-degree (most referenced)
    in_degrees = dict(G.in_degree())
    top_in = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)[:5]
    print("\nTop 5 by in-degree (most linked to):")
    for artist, degree in top_in:
        print(f"  {artist}: {degree}")