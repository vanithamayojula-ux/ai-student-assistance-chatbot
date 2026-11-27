---
title: Introduction to Database Systems Syllabus (AICTE Model Curriculum, B.Tech CSE)
category: syllabus
doc_id: AICTE-DBMS
origin: official
source: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf
---
# Introduction to Database Systems Syllabus (AICTE Model Curriculum, B.Tech CSE)

This is the Introduction to Database Systems (DBMS) syllabus from the AICTE Model Curriculum for the UG degree in Computer Science and Engineering (revised 2022), published by AICTE, the All India Council for Technical Education. It is a model syllabus that universities adapt. It is not LPU's own syllabus: LPU does not publish its course syllabi on its public website, so LPU's course code, credits and units may differ. In LPU's published sample B.Tech CSE curriculum, Database Management Systems is a Year 1, Spring term course.

## Topics at a glance

**Q:** What topics are covered in the Database Systems (DBMS) syllabus?
**A:** The AICTE Introduction to Database Systems syllabus covers eight modules: motivation and data models, the relational model and relational algebra, SQL and database application programming, semi-structured data and MongoDB, ER modeling and normalization (3NF and BCNF), physical storage and B+-tree indexing, query processing and optimization, and transaction processing (ACID, 2PL concurrency control and undo/redo recovery).

## Course details

| Item | Value |
|---|---|
| AICTE course code | PCC CS-505 |
| Course title | Introduction to Database Systems |
| Credits | 5 (3 lecture, 0 tutorial, 4 practical hours: 3L:0T:4P) |
| AICTE semester | Semester V |

## Module 1: Introduction (about 1 week)

- Motivation for database management systems.
- Introduction to data models: relational, semi-structured and Entity-Relationship (ER).

## Module 2: Relational databases (about 1.5 weeks)

- Relational data model and relational algebra.
- Optional: relational calculus and its connection to first-order logic.
- Lab practice using pen-and-paper exercises and the RelaX relational algebra calculator.

## Module 3: SQL and interacting with a database (about 3 weeks)

- DDL (schema definition), `INSERT`, `DELETE` and `UPDATE`.
- Simple queries (select, project, join and aggregate queries) and complex queries (`WITH` clause, nested subqueries and views).
- Programming in a standard language and interfacing with a database backend using connectors such as JDBC or ODBC (PostgreSQL preferred, or MySQL/SQLite).

## Module 4: Big data and semi-structured data (about 1 week)

- Key-value stores and semi-structured data using JSON and MongoDB, with small hands-on exercises.

## Module 5: Database design (about 2 weeks)

- Introduction to the Entity-Relationship (ER) model and mapping ER designs to relational tables.
- Functional dependencies and normalization (BCNF, and optionally 3NF).

## Module 6: Physical design (about 2 weeks)

- Overview of physical storage (hard disks, flash/SSD and RAM), sequential vs random I/O, and reliability via RAID.
- Storage organization: records, pages, files, database buffers and database metadata.
- Indexing and B+-trees, including interactive visualization exercises.

## Module 7: Query processing and optimization (about 2 weeks)

- Query processing: external sort, nested-loop joins and indexed nested-loop joins.
- Overview of query optimization: equivalent relational expressions, cost-based optimization, examining query plans using `EXPLAIN` and verifying the benefit of indexes.

## Module 8: Transaction processing (about 2 weeks)

- Concept of transactions and schedules, and ACID properties.
- Conflict-serializability and recoverability.
- Concurrency control: locks, Two-Phase Locking (2PL), Strict 2PL and optional isolation levels.
- Crash recovery using undo and redo logs.

## Textbooks and references

Textbooks: Database System Concepts (Silberschatz, Korth and Sudarshan, 7th edition, McGraw-Hill Indian Edition, 2021); Fundamentals of Database Systems (Elmasri and Navathe, 7th edition, Pearson, 2017); Principles of Database Management (Lemahieu, Broucke and Baesens, Cambridge University Press, 2018); Database Management Systems (R. P. Mahapatra, Khanna, 2020); Database Management Systems (Krishnan, McGraw-Hill).

Online resources: RelaX relational algebra calculator; PostgreSQL, MySQL/MariaDB or SQLite; University of San Francisco B+-tree visualization; MongoDB; PDBM playground.

## Source

AICTE Model Curriculum for UG Degree Course in Computer Science and Engineering, printed pages 116 to 118: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf. Retrieved 27 November 2026.
