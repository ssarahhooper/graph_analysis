
import math
import matplotlib.pyplot as plt
import argparse
import json
import networkx as nx
import queue
from typing import Dict, List, Tuple, Optional



def read_gml(file: str) -> nx.Graph:
    g = nx.read_gml(file)
    # make sure all nodes are strings
    mapping = {u: str(u) for u in g.nodes}
    g = nx.relabel_nodes(g, mapping)
    return g


# clustering
def compute_clustering_coefficients(G: nx.Graph) -> Dict:
    cc = nx.clustering(G)
    nx.set_node_attributes(G, cc, "clustering_coeff")
    return cc


def neighborhood_overlap(G: nx.Graph, u, v) -> float:
    # Jaccard-like neighborhood overlap excluding endpoints
    Nu = set(G.neighbors(u)) - {v}
    Nv = set(G.neighbors(v)) - {u}
    if len(Nu) == 0 and len(Nv) == 0:
        return 0.0
    inter = len(Nu & Nv)
    union = len(Nu | Nv)
    return inter / union if union > 0 else 0.0


def compute_neighborhood_overlap(G: nx.Graph) -> Dict[Tuple, float]:
    values = {}
    for u, v in G.edges():
        no = neighborhood_overlap(G, u, v)
        values[(u, v)] = no
        values[(v, u)] = no  # convenient for undirected
        G[u][v]["neighborhood_overlap"] = float(no)
    return values
