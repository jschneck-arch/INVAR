"""
skg.core.topology
=================
Graph topology, cycle basis, phase holonomy, and curvature cost.

The coupling graph G = (V, E) emerges from the CouplingField:
    V = manifestations
    E = {(i,j) : A_ij is a resolved graph edge}

Key quantities:
    β₁(A) = |E| - |V| + k         (first Betti number = independent cycles)
    Φ(c)  = Σ_{(i,j)∈c} [arg(A_ij) + (θⱼ - θᵢ)]    (phase holonomy)
    E_topo(A) = Σ_c wc · (1 - cos Φ(c))              (curvature cost)

E_topo = 0 when all cycles have consistent phase transport (no folds).
E_topo > 0 when phase transport fails around a cycle (fold detected).

β₁ > 0 means the field has topological defects — coupling cycles that
cannot be eliminated by continuous deformation. These are persistent folds.

Implementation uses a spanning-tree approach for cycle basis:
    1. Build spanning forest of G
    2. Each non-tree edge (i,j) defines one fundamental cycle
    3. β₁ = number of fundamental cycles = |E| - |V| + k
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

from .field import CouplingField, ManifestationKey

_DEFAULT_CYCLE_WEIGHT = 1.0


@dataclass
class Cycle:
    """A fundamental cycle in the coupling graph."""
    edges: List[Tuple[ManifestationKey, ManifestationKey]]  # directed edge sequence
    weight: float = _DEFAULT_CYCLE_WEIGHT

    def holonomy(
        self,
        field: CouplingField,
        theta_fn,   # callable(ManifestationKey) -> float
    ) -> float:
        """
        Φ(c) = Σ_{(i,j)∈c} [arg(A_ij) + (θⱼ - θᵢ)]

        Phase holonomy around the cycle. Zero if phase transport is consistent.
        Nonzero holonomy = coupling fold = topological defect.
        """
        phi = 0.0
        for (i, j) in self.edges:
            phi += field.phase(i, j) + (theta_fn(j) - theta_fn(i))
        return phi

    def curvature_cost(
        self,
        field: CouplingField,
        theta_fn,
    ) -> float:
        """wc · (1 - cos Φ(c)) — this cycle's contribution to E_topo."""
        phi = self.holonomy(field, theta_fn)
        return self.weight * (1.0 - math.cos(phi))


class CouplingGraph:
    """
    The coupling graph derived from CouplingField.

    Provides cycle basis, Betti number β₁, holonomy, and curvature cost.
    Reconstructed from the field on each call to build() — not cached.
    """

    def __init__(self) -> None:
        self._vertices: Set[ManifestationKey] = set()
        self._adj: Dict[ManifestationKey, List[ManifestationKey]] = defaultdict(list)
        self._cycles: List[Cycle] = []
        self._beta1: int = 0
        self._k: int = 0    # connected components

    @classmethod
    def build(cls, field: CouplingField) -> "CouplingGraph":
        """Construct the coupling graph from the current field state."""
        g = cls()
        edges: List[Tuple[ManifestationKey, ManifestationKey]] = []

        for edge in field.graph_edges():
            g._vertices.add(edge.i)
            g._vertices.add(edge.j)
            g._adj[edge.i].append(edge.j)
            g._adj[edge.j].append(edge.i)
            # Store canonical edge once
            canonical = (min(edge.i, edge.j), max(edge.i, edge.j))
            if canonical not in [(min(a, b), max(a, b)) for a, b in edges]:
                edges.append(canonical)

        g._cycles, g._beta1, g._k = g._compute_cycle_basis(edges)
        return g

    @property
    def vertices(self) -> Set[ManifestationKey]:
        return set(self._vertices)

    @property
    def beta_1(self) -> int:
        """First Betti number = number of independent cycles = |E| - |V| + k."""
        return self._beta1

    @property
    def connected_components(self) -> int:
        return self._k

    @property
    def cycles(self) -> List[Cycle]:
        return list(self._cycles)

    def neighbors(self, v: ManifestationKey) -> List[ManifestationKey]:
        return list(self._adj.get(v, []))

    # ------------------------------------------------------------------
    # Topological quantities
    # ------------------------------------------------------------------

    def topo_energy(self, field: CouplingField, theta_fn) -> float:
        """
        E_topo(A) = Σ_c wc · (1 - cos Φ(c))

        Sum over fundamental cycles. Zero when all cycles have zero holonomy
        (consistent phase transport — no folds). Positive when folds exist.
        """
        return sum(c.curvature_cost(field, theta_fn) for c in self._cycles)

    def local_topo_energy(
        self, v: ManifestationKey, field: CouplingField, theta_fn
    ) -> float:
        """E_topo(Aᵢ) — curvature contribution at vertex i (cycles passing through i)."""
        return sum(
            c.curvature_cost(field, theta_fn)
            for c in self._cycles
            if any(v in (e[0], e[1]) for e in c.edges)
        )

    def fold_cycles(self, field: CouplingField, theta_fn, threshold: float = 0.1) -> List[Cycle]:
        """Return cycles with holonomy above threshold — active folds."""
        return [
            c for c in self._cycles
            if abs(c.holonomy(field, theta_fn)) > threshold
        ]

    # ------------------------------------------------------------------
    # Cycle basis via spanning forest
    # ------------------------------------------------------------------

    def _compute_cycle_basis(
        self,
        edges: List[Tuple[ManifestationKey, ManifestationKey]],
    ) -> Tuple[List[Cycle], int, int]:
        """
        Compute fundamental cycle basis using spanning forest.

        For each edge (i,j) not in the spanning tree, there is exactly one
        fundamental cycle: the unique tree path from i to j plus the edge (i,j).

        β₁ = |E| - |V| + k  (k = connected components)
        """
        if not self._vertices:
            return [], 0, 0

        vertices = list(self._vertices)
        parent: Dict[ManifestationKey, ManifestationKey] = {}
        visited: Set[ManifestationKey] = set()
        tree_edges: Set[Tuple[ManifestationKey, ManifestationKey]] = set()
        components = 0

        def find(v):
            while parent.get(v, v) != v:
                v = parent[v]
            return v

        def union(u, v):
            ru, rv = find(u), find(v)
            if ru == rv:
                return False
            parent[rv] = ru
            return True

        for v in vertices:
            parent[v] = v

        for (u, v) in edges:
            if union(u, v):
                tree_edges.add((min(u, v), max(u, v)))

        # Count components
        roots = {find(v) for v in vertices}
        k = len(roots)
        beta1 = len(edges) - len(vertices) + k

        # Build fundamental cycles for non-tree edges
        cycles: List[Cycle] = []
        for (u, v) in edges:
            canonical = (min(u, v), max(u, v))
            if canonical in tree_edges:
                continue
            # Find tree path from u to v using BFS on tree adjacency
            path = self._tree_path(u, v, tree_edges)
            if path is not None:
                directed = [(path[k], path[k+1]) for k in range(len(path)-1)]
                directed.append((u, v))  # closing edge
                cycles.append(Cycle(edges=directed))

        return cycles, max(0, beta1), k

    def _tree_path(
        self,
        src: ManifestationKey,
        dst: ManifestationKey,
        tree_edges: Set[Tuple[ManifestationKey, ManifestationKey]],
    ) -> Optional[List[ManifestationKey]]:
        """BFS shortest path using only tree edges."""
        # Build tree adjacency
        tree_adj: Dict[ManifestationKey, List[ManifestationKey]] = defaultdict(list)
        for (u, v) in tree_edges:
            tree_adj[u].append(v)
            tree_adj[v].append(u)

        if src == dst:
            return [src]

        from collections import deque
        queue = deque([[src]])
        visited = {src}
        while queue:
            path = queue.popleft()
            node = path[-1]
            for nb in tree_adj[node]:
                if nb in visited:
                    continue
                new_path = path + [nb]
                if nb == dst:
                    return new_path
                visited.add(nb)
                queue.append(new_path)
        return None
