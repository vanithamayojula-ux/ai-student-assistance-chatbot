---
title: Computer Organization and Architecture Syllabus (AICTE Model Curriculum, B.Tech CSE)
category: syllabus
doc_id: AICTE-COA
origin: official
source: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf
---
# Computer Organization and Architecture Syllabus (AICTE Model Curriculum, B.Tech CSE)

This is the Computer Organization and Architecture syllabus from the AICTE Model Curriculum for the UG degree in Computer Science and Engineering (revised 2022), published by AICTE, the All India Council for Technical Education. It is a model syllabus that universities adapt. It is not LPU's own syllabus: LPU does not publish its course syllabi on its public website. LPU's sample B.Tech CSE curriculum has a related course called Computer Organisation and Design in Year 2, Spring term; its code, credits and units may differ from this model.

## Topics at a glance

**Q:** What topics are covered in the Computer Organization and Architecture syllabus?
**A:** The AICTE Computer Organization and Architecture syllabus covers five modules: an introduction (von Neumann model, performance, data representation), the RISC-V instruction set architecture, the processor (data path, control and pipelining), the memory hierarchy (caches and DRAM), and storage and I/O (disks, flash, interrupts and DMA).

## Course details

| Item | Value |
|---|---|
| AICTE course code | PCC CS-402 |
| Course title | Computer Organization and Architecture |
| Credits | 5 (3 lecture, 0 tutorial, 4 practical hours: 3L:0T:4P) |
| Semester in the AICTE model | Semester IV |

## Module 1: Introduction (6 lectures, 2 weeks)

- The role of abstraction; the basic functional units of a computer.
- The von Neumann model of computation, and a note on Moore's law.
- Instructions per cycle (IPC) and performance.
- Data representation and basic operations.

## Module 2: Instruction set architecture, RISC-V (8 to 9 lectures, 3 weeks)

- CPU registers, instruction format and encoding, addressing modes.
- Instruction set and instruction types; instruction decoding and execution; the basic instruction cycle.
- RISC and CISC; RISC-V instructions; the x86 instruction set.

## Module 3: The processor (6 lectures, 2 weeks)

- Clocking methodology and Amdahl's law.
- Building a data path and control: single-cycle and multi-cycle processors.
- Instruction pipelining and instruction-level parallelism (ILP).
- Data and control hazards, and how they are handled.

## Module 4: Memory hierarchy (8 to 9 lectures, 3 weeks)

- SRAM and DRAM, and locality of reference.
- Caches: indexing mechanisms and the trade-offs of block size, associativity and cache size.
- How the processor and cache interact on a read or write; write-through and write-back caches.
- Average memory access time; cache replacement policies such as LRU; memory interleaving.

## Module 5: Storage and I/O (6 lectures, 2 weeks)

- Magnetic disks (tracks and sectors) and flash memory.
- I/O-mapped and memory-mapped I/O.
- I/O data transfer: programmed I/O, interrupt-driven I/O and DMA.

## Advanced module (desirable)

Module 6, superscalar processors and multicore systems (6 lectures, 2 weeks): the limits of ILP, SMT processors, multicore systems and cache coherence.

## Laboratory work

Five lab modules are offered, of which three are chosen: ARM or RISC-V assembly programming, pipeline and cache simulators such as RIPES and gem5, and building a CPU on an FPGA.

## Textbooks and references

Textbook: Computer Organization and Design: The Hardware/Software Interface (Patterson and Hennessy, 5th edition).

References: Computer Organisation and Architecture (Smruti Ranjan Sarangi); Computer System Architecture (Mano); Computer Organization and Embedded Systems (Hamacher, 6th edition); Computer Architecture and Organization (Hayes, 3rd edition); Computer Organization and Architecture: Designing for Performance (Stallings, 10th edition); Computer System Design and Architecture (Heuring and Jordan, 2nd edition).

## Source

AICTE Model Curriculum for UG Degree Course in Computer Science and Engineering, printed pages 97 to 102: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf. Retrieved 24 November 2026.
