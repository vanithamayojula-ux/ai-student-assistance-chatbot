---
title: Operating Systems Syllabus (AICTE Model Curriculum, B.Tech CSE)
category: syllabus
doc_id: AICTE-OS
origin: official
source: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf
---
# Operating Systems Syllabus (AICTE Model Curriculum, B.Tech CSE)

This is the Operating Systems syllabus from the AICTE Model Curriculum for the UG degree in Computer Science and Engineering (revised 2022), published by AICTE, the All India Council for Technical Education. It is a model syllabus that universities adapt. It is not LPU's own syllabus: LPU does not publish its course syllabi on its public website, so LPU's course code, credits and units for Operating Systems may differ. In LPU's published sample B.Tech CSE curriculum, Operating Systems (with a lab) is a Year 2, Spring term course.

## Topics at a glance

**Q:** What topics are covered in the Operating Systems syllabus?
**A:** The AICTE Operating Systems syllabus covers seven modules: an introduction to operating systems, a computer organization refresher, processes and system calls, memory management and virtual memory, process management and CPU scheduling, concurrency and synchronization (threads, locks, semaphores, deadlocks), and file systems.

## Course details

| Item | Value |
|---|---|
| AICTE course code | PCC CS-403 |
| Course title | Operating Systems |
| Credits | 5 (3 lecture, 0 tutorial, 4 practical hours: 3L:0T:4P) |
| Prerequisites | C/C++ programming, and CS-402 Computer Organization and Architecture |

AICTE asks for Operating Systems to be taught in the semester after Computer Organization and Architecture.

## Module 1: Introduction to operating systems (0.5 week)

- Application requirements; the systems stack and the role of the operating system: resources, abstractions and interfaces.
- Overview of the components of an operating system.
- Examples of different types of operating systems (real-time vs desktop vs mobile), operating systems and OS distributions.

## Module 2: Computer organization refresher (0.5 week)

- Basic organization of the hardware components.
- The role of the operating system relative to hardware, with examples related to the von Neumann architecture.

## Module 3: Processes (1.5 weeks)

- The process abstraction: program vs process, and the Process Control Block (PCB).
- Design of system calls: how they are invoked and how the OS handles them.
- Process control system calls: fork, wait, exec, getpid, getppid and their variants.
- The limited direct execution model.

## Module 4: Memory management (3 weeks)

- Address bus and memory access; the memory view of a process: heap, stack, code and data.
- The address space abstraction using virtual memory, and the related system calls mmap, munmap, sbrk and mprotect.
- Address translation mechanisms: static mapping, segmentation and paging.
- Page faults, page sharing, read/write permissions, swapping, and process vs OS memory.
- Memory bookkeeping and management, with case studies of malloc and of the OS's role in turning a program into a process.

## Module 5: Process management and scheduling (1.5 weeks)

- The process lifecycle, from source code to execution.
- The OS mode of execution: limited direct execution, interrupts and system calls.
- The context switch mechanism and the PCB state.
- Scheduling policies: scheduling metrics, goals and examples (interactive vs real-time, priority scheduling).

## Module 6: Concurrency and synchronization (3 weeks)

- Why concurrency is needed by applications, processes and the OS.
- Threads and the pthread API.
- Synchronization primitives: limits of software-only solutions, atomic instructions, test-and-set, spinlocks, mutexes, condition variables and semaphores; the pthread synchronization API.
- Case studies: producer-consumer, readers-writers and barriers.
- Problems with concurrency: race conditions, deadlocks and order violations.

## Module 7: File systems (2 weeks)

- Persistence and the file abstraction; hard disk architecture and its interfacing.
- System calls for file handling.
- Roles and responsibilities of a file system; file and file system metadata, directory structure and caching optimizations.
- Case study of a file system such as the Unix file system.

## Advanced modules (desirable)

AICTE lists optional advanced modules that use a teaching operating system such as xv6: setting it up, following a system call and a context switch end to end, then modifying it (address translation, interrupt handling, locks, context switching, lazy allocation and demand paging, and synchronization primitives).

## Laboratory work

The practical hours follow the modules: shell tools, fork and exec, strace, pthreads programs, writing a custom memory allocator, and building a simple file system on an emulated disk.

## Textbooks and references

Textbooks: Operating Systems: Three Easy Pieces (Arpaci-Dusseau); The Design of the UNIX Operating System (Maurice Bach); Operating System Concepts (Ekta Walia, Khanna); Advanced Programming in the UNIX Environment (Stevens and Rago); xv6, a simple Unix-like teaching operating system (Cox, Kaashoek and Morris).

References: Modern Operating Systems (Tanenbaum and Bos); Operating System Concepts (Silberschatz, Galvin and Gagne); Linux Kernel Development (Love); Operating Systems: Principles and Practice (Anderson and Dahlin); Computer Systems: A Programmer's Perspective (Bryant and O'Hallaron); NPTEL operating systems courses.

## Source

AICTE Model Curriculum for UG Degree Course in Computer Science and Engineering, printed pages 126 to 132: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf. Retrieved 24 November 2026.
