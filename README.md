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
- read gml using networkx, if a file is directed graph, convert to undirected
- write gml with computed attributes attached to nodes/edges

### Clustering Coefficents
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
- 
### Robustness

### Homophily verification

### Structural Balance

### Temporal Simulation

### Plotting modes




