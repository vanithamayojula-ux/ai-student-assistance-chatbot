---
title: Design and Analysis of Algorithms Syllabus (AICTE Model Curriculum, B.Tech CSE)
category: syllabus
doc_id: AICTE-DAA
origin: official
source: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf
---
# Design and Analysis of Algorithms Syllabus (AICTE Model Curriculum, B.Tech CSE)

This is the Design and Analysis of Algorithms (DAA) syllabus from the AICTE Model Curriculum for the UG degree in Computer Science and Engineering (revised 2022), published by AICTE, the All India Council for Technical Education. It is a model syllabus that universities adapt. It is not LPU's own syllabus: LPU does not publish its course syllabi on its public website, so LPU's code, credits and units may differ. In LPU's published sample B.Tech CSE curriculum, Design and Analysis of Algorithms is a Year 3, Autumn term course.

## Topics at a glance

**Q:** What topics are covered in the Design and Analysis of Algorithms syllabus?
**A:** The AICTE Design and Analysis of Algorithms syllabus covers six modules: applications of graph search (BFS and DFS), greedy algorithms, divide and conquer, dynamic programming and shortest paths, network flows, and intractability (P, NP and NP-completeness).

## Course details

| Item | Value |
|---|---|
| AICTE course code | PCC CS-404 |
| Course title | Design and Analysis of Algorithms |
| Credits | 5 (3 lecture, 0 tutorial, 4 practical hours: 3L:0T:4P) |

## Module 1: Applications of graph search (about 1.5 weeks)

- Review of breadth-first search (BFS) and depth-first search (DFS).
- Checking whether an undirected graph is 2-edge connected.
- Checking whether a directed graph is strongly connected.

## Module 2: Greedy algorithms (2 weeks)

- The greedy paradigm.
- Examples: activity selection, deadline scheduling, fractional knapsack, Kruskal's algorithm for minimum spanning trees, and Huffman coding.

## Module 3: Divide and conquer (2 weeks)

- Why the paradigm is useful, shown through integer multiplication.
- Writing and solving recurrence relations.
- Geometry examples: domination number of a set of points, finding maximal points, and the closest pair of points.
- A linear-time algorithm for finding the median.
- Randomized divide and conquer: randomized quicksort and selection.

## Module 4: Dynamic programming and shortest paths (2.5 weeks)

- Computing Fibonacci numbers and why plain divide and conquer is a bad idea for it; storing results in tables.
- Subproblems and optimal substructure.
- Examples: subset sum, integer knapsack, longest increasing subsequence, longest common subsequence, and matrix chain multiplication.
- Shortest paths: Dijkstra's algorithm for single-source shortest paths, Bellman-Ford for negative edge weights, and Floyd-Warshall for all-pairs shortest paths.

## Module 5: Network flows (2 weeks)

- The maximum s-t flow problem in capacitated networks and the Ford-Fulkerson algorithm.
- Residual capacities and residual graphs, and how they correct earlier greedy choices.
- The max-flow min-cut theorem and integrality of maximum flow for integer capacities.
- Applications: maximum bipartite matching and maximum disjoint paths.

## Module 6: Intractability (2 weeks)

- Models of computation: Turing machines and the RAM model, with a brief look at the PRAM model and memory hierarchy.
- Polynomial-time computation and polynomial-time reductions; yes and no instances of decision problems; decision vs optimization.
- NP as the class of problems whose yes-certificates can be checked efficiently.
- NP-hardness and the Cook-Levin theorem (statement only); NP-completeness and examples of reductions.

## Advanced modules (desirable)

- Polynomial multiplication using the FFT and DFT.
- Beyond NP-completeness: approximation algorithms (bin packing, vertex cover), exponential algorithms such as TSP in 2^n time, and popular heuristics for satisfiability.

## Textbooks and references

Textbooks: Algorithm Design (Kleinberg and Tardos); Algorithms (Dasgupta, Papadimitriou and Vazirani); Design and Analysis of Algorithms (Gajendra Sharma, 4th edition, Khanna).

References: Introduction to Algorithms (Cormen, Leiserson, Rivest and Stein, 4th edition); Algorithm Design: Foundations, Analysis, and Internet Examples (Goodrich and Tamassia, 2nd edition).

## Source

AICTE Model Curriculum for UG Degree Course in Computer Science and Engineering, printed pages 103 to 106: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf. Retrieved 24 November 2026.
