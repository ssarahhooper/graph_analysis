# graph_analysis
CECS 427 Graph Analysis Project

## Setup

### Venv
- I used venv to run my program

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install networkx matplotlib numpy scipy imageio pillow
```
## Basic Command-line usage
```bash
python graph_analysis.py <graph_file.gml> [options]
```
## Load and Plot
```bash
python graph_analysis.py karate.gml --plot C --plot_out out_clustering.png
python graph_analysis.py karate.gml --plot N --plot_out out_overlap.png
python graph_analysis.py homophily.gml --plot P --attr_color color --plot_out out_attr.png
```

## Communities
```bash
python graph_analysis.py karate.gml --components 3 --split_output_dir splits
```

## Random edge failures and Robustness
```bash
python graph_analysis.py karate.gml --simulate_failures 10 --seed 123
python graph_analysis.py karate.gml --robustness_check 5 --robustness_runs 20
```
## Structural balance
```bash
python graph_analysis.py balanced_graph.gml   --verify_balanced_graph --sign_attr sign
python graph_analysis.py imbalanced_graph.gml --verify_balanced_graph --sign_attr sign
```
## Homophily test
```bash
python graph_analysis.py homophily.gml --verify_homophily --homophily_attr color
python graph_analysis.py karate.gml    --verify_homophily --homophily_attr club
```
## Temporal simulation
```bash
# CSV header must be: source,target,timestamp,action
python graph_analysis.py karate.gml --temporal_simulation events.csv --animate_out timeline.gif
```
## Save annotated graph
```bash
python graph_analysis.py karate.gml \
  --simulate_failures 5 \
  --components 2 --split_output_dir splits2 \
  --verify_homophily --homophily_attr club \
  --plot N --plot_out out_overlap.png \
  --output karate_annotated.gml
```
## Approach
### Graph I/O
- Read GML using NetworkX, if a file is a directed graph, convert to undirected
- write GML with computed attributes attached to nodes/edges

### Clustering Coefficients
- uses nx.clustering(G) to compute per-node clustering coefficents
- stored on nodes as clustering_coeff

### Neighborhood overlap
- How similar are the friends of u and v
- for each edge
- get N(u) set of neighbors of u and N(v) set of neighbors of v
- compute:
- inter: mutual neighbors of u and V
- union: neighbor of u or v (excluding u and v)
- overlap: 0 if union = 0, otherwise inter/union
### Community detection
- uses nx.community.girvan_newman(G) and advances until the requested number of components is reached.
- assigns each node a component ID
- can export each community subgraph to split_output_dir.

### Random edge failure
- selects k random edges and removes them from a copy of the graph
- combines connectivity, LCC average shortest path, and flow (betweenness)
- computes baseline first, then recomputes after failures on the modified copy
- computes per-node betweenness deltas and summarizes by mean
- 
### Robustness
- repeats the failure simulation 'runs' times each with k removals
- reproducible randomness by seeding a local RNG
- reports avg number of components and avg min/max component sizes across runs
- works when the graph becomes empty/single
- 
### Homophily verification
- for each node with neighbors, compute the fraction of neighbors sharing a chosen attribute
- Collect each fraction and test whether the mean differs from 0.5
- use scipy.stats.ttest_1samp if scipy is available
- falls back to normal approximation if not
- I implemented this fallback because I recently learned it in my internship and wanted to practice implementing it in my other projects
- prints mean, std, t-statistic, p-value, and short interpretation.
### Structural Balance
- assumes each edge has a sign attribute
- BFS labeling, assigning each node a label -1 or 1, along an edge with sign s, the expected label for the neighbor is label[u]*s
- Any mismatch is flagged as a violation; if no violations are found, then the graph is balanced
- accepts ints/floats and common strings so parse labeling doesn't throw errors
### Temporal Simulation
- reads a .csv with columns source, target, timestamp, action.
- sorts by timestamp; applies add/remove events to a working copy
- creates snapshots; writes an animated GIF if prompted

### Plotting modes
- `--plot C`: Nodes sized by clustering coeff; node color = degree; colorbar shows degree
- `--plot N`: Edges width by neighborhood overlap; edge color = deg(u)+deg(v); nodes colored by degree
- `--plot P`: node color by a chosen node attribute --attr_color; edge color by sign (positive vs negative)
- `--plot T`: simple snapshot placeholder (for temporal simulations) 




