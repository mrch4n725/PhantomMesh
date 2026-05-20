# PhantomMesh
Advanced Network Traffic Manipulation &amp; Protocol Experimentation Framework

> **Educational network analysis and packet-crafting toolkit built with Scapy**

⚠️ **Important Notice**
This project contains functionality that can disrupt, intercept, or manipulate network traffic. Running these techniques on networks or devices you do not own or explicitly have permission to test may violate laws, policies, or terms of service.

Use this project **only** in:

* Personal lab environments
* Isolated virtual networks
* Authorized penetration testing engagements
* Educational cybersecurity research

---

## Overview

`PhantomMesh` is a Python-based network experimentation toolkit that demonstrates several low-level networking concepts using the Scapy packet manipulation framework.

The project includes:

* Automatic network discovery
* ARP scanning
* MAC address spoofing
* DNS response spoofing
* Packet crafting and fragmentation
* Multi-threaded packet transmission
* Host discovery utilities

This tool is intended for:

* Cybersecurity education
* Understanding LAN protocols
* Testing defensive monitoring systems
* Practicing packet analysis in controlled environments

---

## Features

### Network Discovery

* Automatically detects:

  * Local IP address
  * Network range
  * Gateway IP
  * Interface MAC address
* Retrieves gateway MAC via:

  * ARP cache inspection
  * ARP requests

### Host Enumeration

* ARP-based network scanning
* ICMP ping sweep
* Parallel threaded discovery
* Manual target entry support

### Packet Manipulation

* Custom packet crafting with Scapy
* Randomized TTL values
* Packet fragmentation support
* Randomized source addressing

### MAC Address Handling

* Generates randomized vendor-style MAC addresses
* Attempts interface MAC spoofing
* Restores original MAC on cleanup

### Multi-threading

* Concurrent packet generation threads
* Parallelized host scanning
* Continuous traffic operations

### Cleanup & Recovery

* Attempts ARP restoration
* Restores original MAC address
* Stops forwarding configuration on exit

---

## Requirements

### System Requirements

* Linux-based operating system recommended
* Root privileges required
* Python 3.8+

### Python Dependencies

* `scapy`

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/mrch4n725/networkkiller.git
cd networkkiller
```

### Install Dependencies

```bash
pip install scapy
```

Or simply run the script and it will attempt automatic installation.

---

## Usage

### Run the Script

```bash
sudo python3 phantommesh.py
```

### Typical Workflow

1. Auto-detect local network configuration
2. Discover gateway MAC
3. Scan the local subnet
4. Display discovered hosts
5. Select targets
6. Start packet operations
7. Stop with `Ctrl+C`

---

## Project Structure

```text
phantom_mesh.py
README.md
```

---

## Core Components

| Component                | Description                            |
| ------------------------ | -------------------------------------- |
| `auto_detect_network()`  | Detects local network configuration    |
| `scan_network()`         | Performs host discovery                |
| `ping_sweep_parallel()`  | Threaded ICMP sweep                    |
| `generate_spoofed_mac()` | Creates randomized MAC addresses       |
| `arp_spoof()`            | Demonstrates ARP manipulation concepts |
| `dns_spoof()`            | Demonstrates DNS response spoofing     |
| `packet_flood()`         | Generates randomized ICMP traffic      |
| `syn_flood()`            | Demonstrates TCP SYN packet generation |
| `stop_attacks()`         | Cleanup and restoration logic          |

---

## Example Output

```text
[*] Auto-detecting network configuration...
[+] Your IP: 192.168.1.12
[+] Gateway: 192.168.1.1
[+] Network: 192.168.1.0/24

[*] Scanning network...
[+] Found: 192.168.1.5
[+] Found: 192.168.1.10

[+] Selected 2 target(s)
```

---

## Safety Recommendations

If you are learning network security techniques:

* Use VirtualBox or VMware lab environments
* Create isolated VLANs or host-only networks
* Monitor traffic with Wireshark
* Avoid running against production systems
* Disable internet bridging during experiments

---

## Legal Disclaimer

This software is provided for educational and authorized security research purposes only.

The author is not responsible for:

* Misuse of the software
* Network disruption
* Unauthorized access
* Damages caused by improper operation

You are solely responsible for ensuring compliance with:

* Local laws
* Organizational policies
* ISP terms of service
* Ethical security testing standards

---

## Suggested Improvements

Potential future enhancements:

* Better interface selection
* IPv6 support
* Async scanning engine
* PCAP logging
* Interactive TUI dashboard
* Detection-safe simulation mode
* Docker-based lab deployment
* Unit tests

---

## Learning Resources

Useful topics to study alongside this project:

* ARP protocol internals
* DNS packet structure
* TCP handshake mechanics
* ICMP packet analysis
* Ethernet frame construction
* Network intrusion detection systems (IDS)
* VLAN segmentation
* Packet fragmentation behavior

---

## License

MIT License

---
### Credits
Original (basic) Concept & Core Implementation:
 https://github.com/abbisQQ/Python-Kivy-Network-Killer

Created and originally developed by:

@abbisQQ
---
## Acknowledgements

Built using:

* Scapy
* Python networking libraries
* Linux networking utilities
* This description summarised with (Don't hate, I just have no time to write something like this ;) )
