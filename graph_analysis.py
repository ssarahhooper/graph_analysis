#!/usr/bin/env python3


import argparse
import csv
import itertools
import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

# allow program to degrade gracefully if dependencies are not installed
try:
    from scipy import stats as scipy_stats # type: ignore
except Exception: # pragma: no cover
    scipy_stats = None


try:
    import imageio.v2 as imageio # type: ignore
except Exception: # pragma: no cover
    imageio = None


# read gml file, with error handling
def read_graph(path: str) -> nx.Graph:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Graph file not found: {path}")
    try:
        G = nx.read_gml(path)
    except Exception as e:
        raise ValueError(f"Failed to read GML ({path}): {e}")
    if len(G) == 0:
       print("[warn] Loaded an empty graph.")
    # Ensure undirected by default
    if isinstance(G, nx.DiGraph):
        G = G.to_undirected()
    return G


# output graph
def write_graph(G: nx.Graph, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    nx.write_gml(G, out_path)
    print(f"[ok] Wrote graph with {G.number_of_nodes()} nodes / {G.number_of_edges()} edges -> {out_path}")


# clustering
def compute_clustering_coefficients(G: nx.Graph) -> Dict:
    cc = nx.clustering(G)
    nx.set_node_attributes(G, cc, "clustering_coeff")
    return cc


def neighborhood_overlap(G: nx.Graph) -> Dict[Tuple, float]:
    overlap = {}
    for u, v in G.edges():
        Nu = set(G.neighbors(u))
        Nv = set(G.neighbors(v))
        inter = Nu & Nv
        union = (Nu | Nv) - {u, v}
        val = 0.0 if not union else len(inter) / len(union)
        overlap[(u, v)] = val
        overlap[(v, u)] = val  # store symmetrically for convenience
    nx.set_edge_attributes(G, {k: float(v) for k, v in overlap.items()}, "neighborhood_overlap")
    return overlap


def compute_neighborhood_overlap(G: nx.Graph) -> Dict[Tuple, float]:
    return neighborhood_overlap(G)


def girvan_newman_n_components(G: nx.Graph, n: int) -> List[set]:
    # empty graph
    if G.number_of_edges() == 0 or G.number_of_nodes() == 0:
        return [set(G.nodes())]
    # initalize generator
    gen = nx.community.girvan_newman(G)
    # loop n-1 times,, splits graph into one more component, comp holds last partition produced
    comp = None
    try:
        for _ in range(n - 1):
            comp = next(gen)
    except StopIteration:
        pass
    # generator ran out early
    if comp is None:
        # n == 1 or generator empty
        partition = [set(G.nodes())]
    else:
        # build list of sets, one per community
        partition = [set(c) for c in comp]
    # tag nodes with component id
    comp_id = {}
    for i, nodes in enumerate(partition):
        for u in nodes:
            comp_id[u] = i
    nx.set_node_attributes(G, comp_id, name="component")
    return partition


def simulate_edge_failures(G: nx.Graph, k: int, seed: Optional[int] = None) -> Tuple[nx.Graph, List[Tuple]]:
    # no edges, nothing to remove
    if k <= 0 or G.number_of_edges() == 0:
        return G.copy(), []
    # random number generator
    rng = random.Random(seed)
    # all current edges in graph
    edges = list(G.edges())
    # prevents removing more edges than actually exist
    k = min(k, len(edges))
    # selects k edges at random to fail
    removed = rng.sample(edges, k)
    # remove edges from copy and return new graph and removed edges
    G2 = G.copy()
    G2.remove_edges_from(removed)
    return G2, removed


def avg_shortest_path_length_lcc(G: nx.Graph) -> float:
    # value undefined
    if G.number_of_nodes() == 0:
        return float("nan")
    # graph fully connected
    if nx.is_connected(G):
        return nx.average_shortest_path_length(G)
    # Compute on largest connected component
    components = sorted((set(c) for c in nx.connected_components(G)), key=len, reverse=True)
    # if somehow no connected componets
    if not components:
        return float("inf")
    # exctract LCC subgraph
    H = G.subgraph(components[0]).copy()
    if H.number_of_nodes() <= 1:
        return 0.0
    return nx.average_shortest_path_length(H)


def analyze_failure_impact(G: nx.Graph, k: int, seed: Optional[int] = None) -> Dict:
    # baseline average shortest path
    base_asp = avg_shortest_path_length_lcc(G)
    # node betweenness centrality before failures
    base_betw = nx.betweenness_centrality(G)
    # connected components before failures.
    base_components = nx.number_connected_components(G)

    G2, removed = simulate_edge_failures(G, k, seed)

    # recompute after failures
    asp2 = avg_shortest_path_length_lcc(G2)
    betw2 = nx.betweenness_centrality(G2)
    comps2 = nx.number_connected_components(G2)

    # per-node betweenness change and average
    all_nodes = set(G.nodes()) | set(G2.nodes())
    delta_betw = {u: betw2.get(u, 0.0) - base_betw.get(u, 0.0) for u in all_nodes}
    avg_delta_betw = statistics.fmean(delta_betw.values()) if delta_betw else 0.0

    return {
        "removed_edges": removed,
        "avg_shortest_path_before": base_asp,
        "avg_shortest_path_after": asp2,
        "delta_avg_shortest_path": (asp2 - base_asp) if (not math.isnan(base_asp) and not math.isnan(asp2)) else float("nan"),
        "num_components_before": base_components,
        "num_components_after": comps2,
        "avg_delta_betweenness": avg_delta_betw,
        "graph_after": G2,
    }


def robustness_check(G: nx.Graph, k: int, runs: int = 50, base_partition: Optional[List[set]] = None, seed: Optional[int] = None) -> Dict:
    rng = random.Random(seed)
    num_components = []
    max_sizes = []
    min_sizes = []
    cluster_persistence = []

    # if inital community parition, builds a dict mapping each node to original com id.
    base_labels = None
    if base_partition is not None:
        base_labels = {}
        for i, part in enumerate(base_partition):
            for u in part:
                base_labels[u] = i

    # repeat 'runs' times, each with new copy of g and k random edges removed
    for r in range(runs):
        G2, _ = simulate_edge_failures(G, k, seed=rng.randint(0, 1_000_000))
        # compute connected components after failures
        comps = [set(c) for c in nx.connected_components(G2)]
        sizes = [len(c) for c in comps] or [0]
        num_components.append(len(comps))
        max_sizes.append(max(sizes))
        min_sizes.append(min(sizes))

        if base_labels is not None:
            # Measure fraction of nodes that remain with majority of their original cluster mates
            pers_scores = []
            for c in comps:
                labels = [base_labels.get(u, -1) for u in c]
                if not labels:
                    continue
                maj = max(set(labels), key=labels.count)
                pers_scores.append(labels.count(maj) / len(labels))
            cluster_persistence.append(statistics.fmean(pers_scores) if pers_scores else 0.0)

    report = {
        "runs": runs,
        "k_removed": k,
        "avg_num_components": statistics.fmean(num_components) if num_components else 0,
        "max_component_size_avg": statistics.fmean(max_sizes) if max_sizes else 0,
        "min_component_size_avg": statistics.fmean(min_sizes) if min_sizes else 0,
    }
    if cluster_persistence:
        report["avg_cluster_persistence"] = statistics.fmean(cluster_persistence)
    return report


def verify_homophily_ttest(G: nx.Graph, attr: str = "color") -> Dict:
    fracs = []
    for u in G.nodes():
        nbrs = list(G.neighbors(u))
        if not nbrs:  # skip
            continue
        au = G.nodes[u].get(attr, None) # u's attribute value
        same = sum(1 for v in nbrs if G.nodes[v].get(attr, None) == au)
        fracs.append(same / len(nbrs))  # fract in [0,1]
    # if every node was isolated
    if not fracs:
        return {"error": "No nodes with neighbors to test."}

    mean_frac = float(np.mean(fracs))
    std_frac = float(np.std(fracs, ddof=1)) if len(fracs) > 1 else 0.0

    # Welch t-test vs 0.5 (null: mean == 0.5) homophily if > 0
    # Implement manually if scipy is not installed
    n = len(fracs)
    if scipy_stats is not None and n >= 2:
        t_stat, p_val = scipy_stats.ttest_1samp(fracs, popmean=0.5)
    else:
        if n <= 1:
            t_stat, p_val = float("nan"), float("nan")
        else:
            se = std_frac / math.sqrt(n)
            t_stat = (mean_frac - 0.5) / se if se > 0 else float("inf")
            # aproximate p via normal
            p_val = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))

    return {
        "attr": attr,
        "n_tested": n,
        "mean_same_attr_neighbor_frac": mean_frac,
        "std_same_attr_neighbor_frac": std_frac,
        "t_statistic": float(t_stat),
        "p_value": float(p_val),
        "interpretation": (
            "Evidence of homophily (mean>0.5)" if mean_frac > 0.5 and (p_val < 0.05) else
            ("Evidence of heterophily (mean<0.5)" if mean_frac < 0.5 and (p_val < 0.05) else
             "No strong evidence against 0.5 null")
        )
    }


# -----------------------------
# Structural balance
# -----------------------------

def verify_structural_balance(G: nx.Graph, sign_attr: str = "sign") -> Dict:
    # parse into 1 or -1
    def parse_sign(val) -> int:
        if isinstance(val, (int, float)):
            return 1 if val >= 0 else -1
        if isinstance(val, str):
            val = val.strip().lower()
            if val in {"+", "pos", "positive", "+1", "1"}:
                return 1
            if val in {"-", "neg", "negative", "-1"}:
                return -1
        return 1  # default if missing, treat as positive

    label: Dict = {}
    # contradict balance condition
    violations: List[Tuple] = []

    # BFS over each component
    for start in G.nodes():
        if start in label:
            continue
        label[start] = 1
        q = deque([start])
        while q:
            u = q.popleft()
            # for each unlabled node, for an edge with sign s,
            for v in G.neighbors(u):
                s = parse_sign(G.edges[u, v].get(sign_attr, 1))
                expected = label[u] * s
                # if v is unlabled assign expected and continue
                if v not in label:
                    label[v] = expected
                    q.append(v)
                # if v is already labeled and dosn't match expected, record violation
                else:
                    if label[v] != expected:
                        violations.append((u, v, s))
    return {
        "balanced": len(violations) == 0,
        "violations": violations,
        "labels": label,
    }


# -----------------------------
# Plotting
# -----------------------------

def plot_graph(G: nx.Graph, mode: str, out_path: Optional[str] = None, attr_color: str = "color") -> None:
    # compute node positions
    pos = nx.spring_layout(G, seed=42)
    plt.figure(figsize=(9, 7))

    # mode c = clustering coefficent
    if mode.upper() == "C":
        # Node size = clustering, color = degree adds colorbar for node degree
        cc = nx.get_node_attributes(G, "clustering") or compute_clustering_coefficients(G)
        sizes = [300 + 1200 * cc.get(u, 0.0) for u in G.nodes()]
        degrees = dict(G.degree())
        colors = [degrees.get(u, 0) for u in G.nodes()]
        nx.draw_networkx_nodes(G, pos, node_size=sizes, node_color=colors)
        nx.draw_networkx_edges(G, pos, alpha=0.35)
        nx.draw_networkx_labels(G, pos, font_size=8)
        plt.title("Clustering coefficient (size) & Degree (color)")
        cbar = plt.colorbar(plt.cm.ScalarMappable(), ax=plt.gca())
        cbar.set_label("Degree")

    # mode n = neighborhood overlap
    elif mode.upper() == "N":
        # edge thickness = neighborhood overlap, edge color = sum of endpoint degrees
        no = nx.get_edge_attributes(G, "neighborhood_overlap") or neighborhood_overlap(G)
        deg = dict(G.degree())
        widths = [1 + 6 * no.get((u, v), no.get((v, u), 0.0)) for u, v in G.edges()]
        ecolors = [deg[u] + deg[v] for u, v in G.edges()]
        nx.draw_networkx_nodes(G, pos, node_size=300, node_color=list(deg.values()))
        nx.draw_networkx_edges(G, pos, width=widths, edge_color=ecolors)
        nx.draw_networkx_labels(G, pos, font_size=8)
        plt.title("Neighborhood overlap (edge width) & Degree sum (edge color)")
        cbar = plt.colorbar(plt.cm.ScalarMappable(), ax=plt.gca())
        cbar.set_label("deg(u)+deg(v)")

    # mode p - attribute plot
    elif mode.upper() == "P":
        # Plot provided attributes: node color by attr_color, edge color by sign
        node_colors = []
        attrs = nx.get_node_attributes(G, attr_color)
        # Map category to int
        mapping = {}
        next_id = 0
        for u in G.nodes():
            val = attrs.get(u, None)
            if val not in mapping:
                mapping[val] = next_id
                next_id += 1
            node_colors.append(mapping[val])
        edge_colors = []
        for u, v in G.edges():
            s = G.edges[u, v].get("sign", 1)
            if isinstance(s, str):
                s = 1 if s.strip().startswith("+") else -1
            edge_colors.append(1 if s >= 0 else 0)
        nx.draw_networkx_nodes(G, pos, node_size=350, node_color=node_colors)
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, alpha=0.7)
        nx.draw_networkx_labels(G, pos, font_size=8)
        plt.title(f"Attributes: node color by '{attr_color}', edge color by sign")
        cbar = plt.colorbar(plt.cm.ScalarMappable(), ax=plt.gca())
        cbar.set_label(attr_color)

    elif mode.upper() == "T":
        # Placeholder note for temporal mode
        nx.draw(G, pos, with_labels=True, node_size=350)
        plt.title("Temporal simulation snapshot (use --temporal_simulation)")

    else:
        raise ValueError("Unknown plot mode. Use C, N, P, or T.")

    # save or show
    plt.tight_layout()
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        plt.savefig(out_path, dpi=140, bbox_inches="tight")
        print(f"[ok] Saved plot -> {out_path}")
    else:
        plt.show()
    plt.close()


# -----------------------------
# Temporal simulation
# -----------------------------

def run_temporal_simulation(G: nx.Graph, csv_path: str, animate_out: Optional[str] = None, layout_seed: int = 42) -> Dict:
    # validate input and read events
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Temporal CSV not found: {csv_path}")

    events = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = row.get("source")
            dst = row.get("target")
            ts = row.get("timestamp")
            act = row.get("action", "add").lower()
            if not src or not dst or not ts:
                continue
            events.append((ts, src, dst, act))
    events.sort(key=lambda x: x[0])

    frames = []
    # fix node positions
    pos = nx.spring_layout(G, seed=layout_seed)

    # Apply events in order and take snapshots per timestamp
    current_ts = None
    snapshots = []
    G_work = G.copy()

    # render each snapshot
    for ts, u, v, act in events:
        if current_ts is None:
            current_ts = ts
        if ts != current_ts:
            snapshots.append((current_ts, G_work.copy()))
            current_ts = ts
        if act.startswith("add"):
            G_work.add_edge(u, v)
        elif act.startswith("rem") or act.startswith("del"):
            if G_work.has_edge(u, v):
                G_work.remove_edge(u, v)
        else:
            print(f"[warn] Unknown action '{act}' for ({u},{v})@{ts}")
    snapshots.append((current_ts if current_ts else "t0", G_work.copy()))

    # Produce frames
    for ts, Gi in snapshots:
        plt.figure(figsize=(8, 6))
        deg = dict(Gi.degree())
        node_sizes = [300 + 30 * deg.get(u, 0) for u in Gi.nodes()]
        nx.draw(Gi, pos, with_labels=True, node_size=node_sizes)
        plt.title(f"Time {ts}: |V|={Gi.number_of_nodes()}, |E|={Gi.number_of_edges()}")
        plt.tight_layout()
        if animate_out and imageio is not None:
            # Render to image buffer
            import io
            from PIL import Image
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
            buf.seek(0)
            frames.append(imageio.imread(buf))
            buf.close()
        plt.close()

    # gif
    if animate_out and imageio is not None:
        imageio.mimsave(animate_out, frames, duration=0.9)
        print(f"[ok] Saved animation -> {animate_out}")

    return {"snapshots": len(snapshots)}


# -----------------------------
# Export components
# -----------------------------

def export_components(G: nx.Graph, partition: List[set], out_dir: str, base_name: str = "component") -> None:
    os.makedirs(out_dir, exist_ok=True)
    for i, nodes in enumerate(partition):
        H = G.subgraph(nodes).copy()
        out_path = os.path.join(out_dir, f"{base_name}_{i}.gml")
        nx.write_gml(H, out_path)
    print(f"[ok] Exported {len(partition)} components -> {out_dir}")


# -----------------------------
# CLI
# -----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyze and visualize GML graphs with community and robustness tooling.")
    p.add_argument("graph_file", help="Input .gml graph")

    # Community options
    p.add_argument("--components", type=int, default=0, help="Partition graph into N components via Girvan–Newman")
    p.add_argument("--split_output_dir", type=str, default=None, help="If set, export each component to this directory")

    # Robustness & failures
    p.add_argument("--simulate_failures", type=int, default=0, metavar="K", help="Remove K random edges and report impact")
    p.add_argument("--robustness_check", type=int, default=0, metavar="K", help="Run multiple simulations removing K edges")
    p.add_argument("--robustness_runs", type=int, default=50, help="Number of runs for robustness_check")

    # Plotting
    p.add_argument("--plot", type=str, choices=["C", "N", "P", "T"], default=None, help="Plot mode: C,N,P or T")
    p.add_argument("--plot_out", type=str, default=None, help="Path to save plot image (png)")
    p.add_argument("--attr_color", type=str, default="color", help="Node attribute name for color in P mode")

    # Verifications
    p.add_argument("--verify_homophily", action="store_true")
    p.add_argument("--homophily_attr", type=str, default="color")
    p.add_argument("--verify_balanced_graph", action="store_true")
    p.add_argument("--sign_attr", type=str, default="sign")

    # Temporal
    p.add_argument("--temporal_simulation", type=str, default=None, help="CSV file with source,target,timestamp,action")
    p.add_argument("--animate_out", type=str, default=None, help="Output GIF for temporal simulation")

    # Output
    p.add_argument("--output", type=str, default=None, help="Save final graph (with annotations) to .gml")

    # Misc
    p.add_argument("--seed", type=int, default=42, help="Random seed")

    return p


# main
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    random.seed(args.seed)
    np.random.seed(args.seed)

    # Load
    G = read_graph(args.graph_file)

    # Compute metrics
    cc = compute_clustering_coefficients(G)
    no = neighborhood_overlap(G)

    # failures
    failure_report = None
    if args.simulate_failures > 0:
        failure_report = analyze_failure_impact(G, args.simulate_failures, seed=args.seed)
        print("\n[simulate_failures]")
        for k, v in failure_report.items():
            if k == "graph_after":
                continue
            print(f"  {k}: {v}")
        # Replace G with post-failure graph
        G = failure_report["graph_after"]

    # community partitioning
    partition = None
    if args.components and args.components > 0:
        # if user requested GN with robustness pre-check via same flag,  interpret as before partitioning
        if args.robustness_check > 0 and args.simulate_failures == 0:
            # single pre-partition removal to test sensitivity
            Gtmp, removed = simulate_edge_failures(G, args.robustness_check, seed=args.seed)
            print(f"[robustness pre-check] Temporarily removed {len(removed)} edges before GN partitioning (non-destructive)")
            partition = girvan_newman_n_components(Gtmp, args.components)
        else:
            partition = girvan_newman_n_components(G, args.components)
        print(f"[ok] Computed Girvan–Newman partition into {len(partition)} components.")
        if args.split_output_dir:
            export_components(G, partition, args.split_output_dir)

    # robustness
    if args.robustness_check > 0:
        base_partition = partition if partition is not None else None
        report = robustness_check(G, args.robustness_check, runs=args.robustness_runs, base_partition=base_partition, seed=args.seed)
        print("\n[robustness_check]")
        for k, v in report.items():
            print(f"  {k}: {v}")

    # verifications
    if args.verify_homophily:
        homo = verify_homophily_ttest(G, attr=args.homophily_attr)
        print("\n[verify_homophily]")
        for k, v in homo.items():
            print(f"  {k}: {v}")

    if args.verify_balanced_graph:
        bal = verify_structural_balance(G, sign_attr=args.sign_attr)
        print("\n[verify_balanced_graph]")
        print(f"  balanced: {bal['balanced']}")
        if not bal["balanced"]:
            print(f"  violations (first 10): {bal['violations'][:10]}")

    # plot
    if args.plot:
        try:
            plot_graph(G, args.plot, out_path=args.plot_out, attr_color=args.attr_color)
        except Exception as e:
            print(f"[warn] Plotting failed: {e}")

    # temporal simulation
    if args.temporal_simulation:
        try:
            run_temporal_simulation(G, args.temporal_simulation, animate_out=args.animate_out)
        except Exception as e:
            print(f"[warn] Temporal simulation failed: {e}")

    # output
    if args.output:
        write_graph(G, args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
