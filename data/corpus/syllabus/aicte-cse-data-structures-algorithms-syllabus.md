---
title: Data Structures and Algorithms Syllabus (AICTE Model Curriculum, B.Tech CSE)
category: syllabus
doc_id: AICTE-DSA
origin: official
source: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf
---
# Data Structures and Algorithms Syllabus (AICTE Model Curriculum, B.Tech CSE)

This is the Data Structures and Algorithms syllabus from the AICTE Model Curriculum for the UG degree in Computer Science and Engineering (revised 2022), published by AICTE, the All India Council for Technical Education. It is a model syllabus that universities adapt. It is not LPU's own syllabus: LPU does not publish its course syllabi on its public website, so LPU's course code, credits and units may differ. In LPU's published sample B.Tech CSE curriculum, Data Structures and Algorithms is a Year 2, Autumn term course.

## Topics at a glance

**Q:** What topics are covered in the Data Structures and Algorithms syllabus?
**A:** The AICTE Data Structures and Algorithms syllabus covers seven essential modules: introduction and asymptotic complexity, abstract data types (arrays, linked lists, stacks, queues, dictionaries and binary trees), priority queues and heaps, binary search trees, AVL trees and 2-4 trees, hash tables and tries, sorting and selection (merge sort, quicksort), and graph representations and traversals (BFS and DFS).

## Course details

| Item | Value |
|---|---|
| AICTE course code | PCC CS-301 |
| Course title | Data Structure and Algorithms |
| Credits | 5 (3 lecture, 0 tutorial, 4 practical hours: 3L:0T:4P) |
| AICTE semester | Semester III |

## Module 1: Introduction and basic terminology (1 week)

- Notion of data structures and algorithms, and the interplay between them.
- Growth of functions ($\log n$, $n$, $2^n$) and applications such as recursive and iterative binary search.
- Worst-case and average-case time and space complexity and their relative merits.
- Asymptotic notation: $O(\cdot)$ and $\Omega(\cdot)$.

## Module 2: Abstract data types, lists, stacks, queues and binary trees (2.5 weeks)

- Abstract data types (ADTs): arrays and linked list ADTs; specification vs implementation.
- Stacks and queues: ADTs and implementations using fixed-size arrays, circular arrays and linked lists; stack applications such as postfix notation and matching parentheses.
- Doubly linked lists: ADT and implementation.
- Dictionary ADT: implementation using arrays, linked lists and binary search.
- Tree ADT and basic traversal algorithms: pre-order, post-order and in-order traversals for binary trees.

## Module 3: Priority queues and heaps (1 week)

- Priority Queue ADT (`FindMin`, `Insert`, `DeleteMin`) and definition of heaps.
- Implementation of priority queues using heaps, array-based heap representation and running time analysis.
- Heap-sort, and why array implementation is more efficient than balanced binary trees for heaps.

## Module 4: Binary search trees, AVL trees and 2-4 trees (3 weeks)

- Binary Search Trees (BSTs): definition, predecessor/successor search and dictionary ADT implementation; why unbalanced BST height may not remain $O(\log n)$.
- AVL trees: height-balance condition, rotations to restore $O(\log n)$ height, and dictionary operations.
- 2-4 trees: multi-way search trees, $O(\log n)$ height and insert/delete operations, with an informal discussion of extension to B-trees.

## Module 5: Hash tables and tries (2 weeks)

- Map ADT and implementation using hash tables; design of hash functions including non-numeric keys.
- Collision resolution schemes: chaining, and open addressing (linear probing, quadratic probing, double hashing).
- Applications of hashing such as finding duplicates and set intersection.
- Tries, compressed tries and suffix tries for implementing the Map ADT.

## Module 6: Sorting and selection (1.5 weeks)

- Bubble sort, insertion sort and selection sort (when $O(n^2)$ algorithms are useful on small or nearly sorted data).
- Merge sort and the divide-and-conquer paradigm.
- Quicksort: average and worst-case analysis, and an intuitive explanation of randomized quicksort.
- Selection based on the partitioning idea used in quicksort.

## Module 7: Graphs, representations and traversal algorithms (2.5 weeks)

- Graph ADTs and applications (such as social networks and the Internet); adjacency list and adjacency matrix representations and their relative merits.
- Basic graph definitions: paths, cycles, trees, spanning trees, connected components and Euler's formula.
- Depth-First Search (DFS) for directed graphs: tree, forward, back and cross edges; applications to cycle finding, topological sort in DAGs and connected components.
- Breadth-First Search (BFS): implementation using queues, shortest-path tree property and running time analysis.

## Advanced modules (desirable)

- Amortized complexity (1 week): binary counter, binomial heaps and extendible arrays; explicit operation counting and implementing a queue using two stacks.
- Randomization in data structures (1 week): skip lists compared with AVL trees, and expected running time of randomized quicksort.

## Textbooks and references

Textbooks: Expert Data Structures with C (R. B. Patel, 4th edition, Khanna); Data Structures and Algorithms in Java (Goodrich and Tamassia, 3rd edition, Wiley); Data Structures and Algorithms in Python (Goodrich and Tamassia, 1st edition, Wiley); Taming Python by Programming (Jeeva Jose, Khanna); Fundamentals of Data Structures (Sartaj Sahni, University Press).

References: NPTEL video series on Data Structures and Algorithms (Naveen Garg); Introduction to Algorithms (Cormen, Leiserson, Rivest and Stein, 4th edition, MIT Press / McGraw-Hill).

## Source

AICTE Model Curriculum for UG Degree Course in Computer Science and Engineering, printed pages 82 to 88: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf. Retrieved 27 November 2026.
