---
title: Compiler Design Syllabus (AICTE Model Curriculum, B.Tech CSE)
category: syllabus
doc_id: AICTE-CD
origin: official
source: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf
---
# Compiler Design Syllabus (AICTE Model Curriculum, B.Tech CSE)

This is the Compiler Design (compiler construction) syllabus from the AICTE Model Curriculum for the UG degree in Computer Science and Engineering (revised 2022), published by AICTE, the All India Council for Technical Education. It is a model syllabus that universities adapt. It is not LPU's own syllabus: LPU does not publish its course syllabi on its public website, and Compiler Design does not appear by name in LPU's published sample B.Tech CSE curriculum.

## Topics at a glance

**Q:** What topics are covered in the Compiler Design syllabus?
**A:** The AICTE Compiler Design syllabus covers eight modules: an introduction to compilers, lexical analysis (LEX and Flex), syntax analysis and parsing (LR or LL), semantic analysis, syntax-directed translation to three-address code, run-time support (activation records and calls), an introduction to code optimization, and code generation.

## Course details

| Item | Value |
|---|---|
| AICTE course code | CS-602 (listed as a professional elective in the course text and as a core course in Semester VII in the summary table) |
| Course title | Compiler Design / Construction |
| Credits | 5 (3 lecture, 0 tutorial, 4 practical hours: 3L:0T:4P) |
| Prerequisites | C, C++ or Java; data structures and algorithms; automata theory |

## Module 1: Introduction to compilers (1 week)

- High-level vs low-level language abstractions.
- Compilation as a series of steps that lower the level of abstraction; the phases of a compiler.
- Bootstrapping and cross-compilation.

## Module 2: Lexical analysis (2 weeks)

- The role of the lexical analyzer; tokens, lexemes and token codes.
- Regular expressions to describe tokens, and deterministic finite automata (DFA) to recognise them.
- Generating a lexical analyzer with LEX or Flex.

## Module 3: Syntax analysis (3 weeks)

- Context-free grammars, parsing, sentences and sentential forms, leftmost and rightmost derivations, parse trees, and ambiguous grammars.
- Overview of top-down and bottom-up parsing.
- One of two options is taught. Option 1, bottom-up: shift-reduce parsing, viable prefixes and valid items, LR(0) items, SLR parsing tables, and parser generators such as YACC or Bison. Option 2, top-down: left factoring, eliminating left recursion, predictive and recursive descent parsing, LL(1) parsing, and parser generators such as ANTLR or JavaCC.

## Module 4: Semantic analysis (1 week)

- Why semantic analysis is needed.
- Abstract syntax trees for expressions, assignments and control flow statements.
- Attribute evaluation and syntax-directed translation schemes (SDTS).

## Module 5: Applications of semantic analysis (3 weeks)

- Using syntax-directed translation for declaration processing and type checking.
- Generating three-address code.

## Module 6: Run-time support (1 week)

- Parameter passing by value, by reference and by name.
- Activation records, and stack and static allocation of activation records.
- Translating a function call: variable offsets, function prologue and epilogue, call and return sequences.

## Module 7: Introduction to code optimization (1 week)

- Control flow graphs.
- Local optimizations: common subexpression elimination, copy propagation and dead code elimination.

## Module 8: Code generation (2 weeks)

- Generating assembly code from three-address code using simple register allocation and instruction selection.

## Advanced topics (desirable)

LR(1) and LALR(1) parsing; global optimizations such as constant propagation and strength reduction; register allocation by graph colouring; optimal code generation for expression trees (Sethi-Ullman and Aho-Johnson algorithms).

## Laboratory work

The lab builds a compiler in stages for a small C-like language: test cases, a lexer, a parser, a type checker, translation to three-address code, and MIPS code generation run on the SPIM simulator.

## Textbooks and references

Textbook: Compilers: Principles, Techniques, and Tools (Aho, Lam, Sethi and Ullman, 2nd edition). Reference: Modern Compiler Implementation in Java (Appel and Palsberg, 2nd edition).

## Source

AICTE Model Curriculum for UG Degree Course in Computer Science and Engineering, printed pages 158 to 162: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf. Retrieved 24 November 2026.
