# Connectome data

`fly_larva_edges.csv.gz` / `fly_larva_nodes.csv.gz` — the complete synaptic
wiring diagram of the *Drosophila melanogaster* larval brain.

- 2,956 neurons, 116,922 directed synaptic connections (synapse `count` per edge,
  `etype` = axo-dendritic `ad`, axo-axonic `aa`, dendro-dendritic `dd`,
  dendro-axonic `da`).
- Node columns kept: `index`, `hemisphere`, `cell_type` (e.g. `sensory`, `KC`,
  `PN`, `DN-VNC`). Positions and annotations are dropped.

Source: M. Winding et al., "The connectome of an insect brain", *Science* 379
eadd9330 (2023), https://doi.org/10.1126/science.add9330 — redistributed via
Netzschleuder (`fly_larva`), https://networks.skewed.de/net/fly_larva.

This graph is the frozen reservoir `W`. Nothing in this repo trains it. The PRD
named a MaleCNS extract; that needs a neuPrint token, so the first `W` is the
public larval whole-brain graph. `flyhero.connectome.load_adjacency` accepts any
edge list with the same columns, so swapping graphs is a data change.
