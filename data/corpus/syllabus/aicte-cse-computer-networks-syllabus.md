---
title: Computer Networks Syllabus (AICTE Model Curriculum, B.Tech CSE)
category: syllabus
doc_id: AICTE-CN
origin: official
source: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf
---
# Computer Networks Syllabus (AICTE Model Curriculum, B.Tech CSE)

This is the Computer Networks syllabus from the AICTE Model Curriculum for the UG degree in Computer Science and Engineering (revised 2022), published by AICTE, the All India Council for Technical Education. It is a model syllabus that universities adapt. It is not LPU's own syllabus: LPU does not publish its course syllabi on its public website, so LPU's course code, credits and units may differ. In LPU's published sample B.Tech CSE curriculum, Computer Networks is a Year 2, Autumn term course.

## Topics at a glance

**Q:** What topics are covered in the Computer Networks syllabus?
**A:** The AICTE Computer Networks syllabus covers eight modules: an introduction to the Internet, the application layer (DNS, HTTP, SMTP), Linux socket programming, the transport layer (TCP, UDP, congestion control), the IP layer (IPv4, IPv6, NAT, firewalls), routing protocols (link state, distance vector, OSPF, BGP), the data link layer (CRC, CSMA/CD, Ethernet, ARP), and wireless networks (802.11).

## Course details

| Item | Value |
|---|---|
| AICTE course code | PCC CS-601 |
| Course title | Computer Networks |
| Credits | 5 (3 lecture, 0 tutorial, 4 practical hours: 3L:0T:4P) |

## Module 1: Introduction to the Internet (1 week)

- How the Internet works, including what happens when you browse a website.
- Basic terms: browser, web server, URL, domain name, IP address and packets.
- Design principles: packet switching vs circuit switching, store-and-forward networks, and layering; the layers of the Internet.
- Performance metrics: end-to-end throughput, delay, jitter and drop rate, Little's Law, and how performance is measured.

## Module 2: Application layer (2 weeks)

- Internet names and how DNS works.
- Application layer protocols: HTTP, SMTP, SNMP and web applications.
- Peer-to-peer applications and P2P file distribution.
- Audio and video streaming, and the challenges of streaming over best-effort IP.

## Module 3: Linux network programming (0.3 week)

- Socket programming in Linux; building a simple client-server application with TCP and UDP sockets.

## Module 4: Transport layer (2.3 weeks)

- The role of the transport layer and the end-to-end principle.
- TCP and UDP basics: process-to-process delivery, multiplexing, port numbers and header structure.
- Reliable delivery over an unreliable network: sequence numbers, ACKs, timeouts, retransmission, stop-and-wait and sliding window.
- TCP connection setup and teardown.
- Flow control vs congestion control; TCP congestion control: slow start, reaction to timeouts, and loss-based and delay-based congestion avoidance.

## Module 5: The IP layer (2 weeks)

- Network architecture and performance: network topology, router architecture (queueing and switching), link performance (traffic characteristics, performance measures, Kendall's notation).
- The IP protocol: why Internet addresses are needed, hierarchical IP addressing, IPv4 and IPv6, the IP datagram, and IP forwarding.
- NAT, security attacks and defences: DMZ and firewalls.

## Module 6: Routing protocols and Internet architecture (2 weeks)

- Link state routing; distance vector routing, count-to-infinity and routing convergence.
- Structure of the Internet: end-user organisations and ISPs.
- Intra-domain routing (OSPF) vs inter-domain routing (BGP).

## Module 7: Data link layer (2 weeks)

- Error detection and recovery: parity checks and CRC.
- Medium access protocols: polling vs contention-based (TDM, ALOHA, CSMA/CD).
- Switched LANs: layer-2 addressing and ARP, the Ethernet frame, and learning switches.

## Module 8: Wireless networks (1 week)

- Wireless physical layer: signal-to-noise ratio, bit error rate, modulation, multipath and interference.
- Wireless LANs: 802.11 architecture (access points, SSID, channels, beacons, scanning, association), the 802.11 CSMA/CA protocol, and the 802.11 variants.

## Advanced modules (desirable)

- SDN and data centre networking: data centre topology, data-centre transport protocols, software defined networking.
- Mobile data networks: cellular Internet access, mobility management and handovers.
- Streaming media: adaptive streaming, voice over IP, recovering from packet loss and jitter, QoS and real-time protocols.

## Laboratory work

Lab work uses Wireshark, ifconfig and dig, socket programming, iperf, and ns-2 or ns-3 network simulation, following the modules.

## Textbooks and references

Textbooks: Computer Networking: A Top-Down Approach (Kurose and Ross, 6th or 7th edition); An Integrated Approach to Computer Networks (Bhavneet Sidhu, Khanna, 2021).

References: The Art of Computer Systems Performance Analysis (Raj Jain); An Introduction to Queueing Systems (Sanjay Bose); Computer Networks (Tanenbaum and Wetherall, 5th edition); Computer Networks: A Systems Approach (Peterson and Davie, 6th edition).

## Source

AICTE Model Curriculum for UG Degree Course in Computer Science and Engineering, printed pages 138 to 145: https://aicte.gov.in/sites/default/files/Updated-AICTE%20-%20UG%20CSE.pdf. Retrieved 24 November 2026.
