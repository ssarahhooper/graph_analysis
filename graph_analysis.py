
import math
import matplotlib.pyplot as plt
import argparse
import json
import networkx as nx
import queue




def read_gml(file: str) -> nx.Graph:
    g = nx.read_gml(file)
    # make sure all nodes are strings
    mapping = {u: str(u) for u in g.nodes}
    g = nx.relabel_nodes(g, mapping)
    return g