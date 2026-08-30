#!/usr/bin/env python3
import socket
import threading
import sys
import struct
import time
from datetime import datetime
from collections import defaultdict

class C:
    R = '\033[91m'
    G = '\033[92m'
    Y = '\033[93m'
    B = '\033[94m'
    M = '\033[95m'
    C = '\033[96m'
    E = '\033[0m'
    BOLD = '\033[1m'

stats = defaultdict(lambda: {"count": 0, "bytes": 0, "last": 0, "sni": None})
source_ips = set()
start_time = time.time()

BANNER = f"""
{C.G}{C.BOLD}╔══════════════════════════════════════════════════════════════╗
║         STEALTH SOCKS5 PROXY - TRAFFIC ANALYSIS              ║
║  • SNI extraction from TLS ClientHello                       ║
║  • HTTP header analysis                                      ║
║  • Traffic statistics (type 'stats' to view)                 ║
╚══════════════════════════════════════════════════════════════╝{C.E}
"""

def log(msg, color=C.B):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}]{C.E} {msg}")

def extract_sni(data):
    try:
        if len(data) < 5 or data[0] != 0x16:
            return None
        pos = 5
        if pos >= len(data):
            return None
        if data[pos] != 0x01:
            return None
        pos += 4 + 2 + 32
        if pos >= len(data):
            return None
        session_len = data[pos]
        pos += 1 + session_len
        if pos + 2 > len(data):
            return None
        cs_len = struct.unpack("!H", data[pos:pos+2])[0]
        pos += 2 + cs_len
        if pos >= len(data):
            return None
        cm_len = data[pos]
        pos += 1 + cm_len
        if pos + 2 > len(data):
            return None
        ext_len = struct.unpack("!H", data[pos:pos+2])[0]
        pos += 2
        ext_end = pos + ext_len
        while pos + 4 <= ext_end:
            ext_type = struct.unpack("!H", data[pos:pos+2])[0]
            ext_data_len = struct.unpack("!H", data[pos+2:pos+4])[0]
            if ext_type == 0x00:
                sni_data = data[pos+4:pos+4+ext_data_len]
                if len(sni_data) >= 5:
                    name_len = struct.unpack("!H", sni_data[3:5])[0]
                    if len(sni_data) >= 5 + name_len:
                        return sni_data[5:5+name_len].decode('ascii', errors='ignore')
            pos += 4 + ext_data_len
    except:
        pass
    return None

def extract_http_info(data):
    try:
        text = data.decode('utf-8', errors='ignore')
        lines = text.split('\r\n')
        if not lines:
            return None
        
        info = {"method": None, "host": None, "user_agent": None, "headers": {}}
        
        if lines[0]:
            parts = lines[0].split(' ')
            if len(parts) >= 2:
                info["method"] = parts[0]
                info["path"] = parts[1]
        
        for line in lines[1:]:
            if ':' in line:
                key, val = line.split(':', 1)
                key = key.strip().lower()
                val = val.strip()
                info["headers"][key] = val
                if key == "host":
                    info["host"] = val
                elif key == "user-agent":
                    info["user_agent"] = val
        
        return info if info["method"] else None
    except:
        return None

def handle_client(client_socket, client_addr):
    source_ip = client_addr[0]
    source_ips.add(source_ip)
    
    try:
        data = client_socket.recv(1024)
        if not data or data[0] != 0x05:
            return
        client_socket.send(b'\x05\x00')
        
        data = client_socket.recv(1024)
        if len(data) < 10 or data[0] != 0x05 or data[1] != 0x01:
            return
        
        addr_type = data[3]
        dest_host = dest_ip = None
        
        if addr_type == 0x01:
            dest_ip = socket.inet_ntoa(data[4:8])
            dest_host = dest_ip
            dest_port = struct.unpack("!H", data[8:10])[0]
        elif addr_type == 0x03:
            domain_len = data[4]
            dest_host = data[5:5+domain_len].decode('ascii', errors='ignore')
            dest_port = struct.unpack("!H", data[5+domain_len:7+domain_len])[0]
            try:
                dest_ip = socket.gethostbyname(dest_host)
            except:
                dest_ip = "?"
        elif addr_type == 0x04:
            dest_ip = socket.inet_ntop(socket.AF_INET6, data[4:20])
            dest_host = dest_ip
            dest_port = struct.unpack("!H", data[20:22])[0]
        else:
            return
        
        stats[dest_host]["count"] += 1
        stats[dest_host]["last"] = time.time()
        
        log(f"{C.G}→{C.E} {C.BOLD}{dest_host}{C.E} {C.Y}({dest_ip}){C.E}:{dest_port}", C.C)
        
        remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote.settimeout(10)
        remote.connect((dest_ip if dest_ip != "?" else dest_host, dest_port))
        
        resp = b'\x05\x00\x00\x01' + socket.inet_aton('0.0.0.0') + b'\x00\x00'
        client_socket.send(resp)
        
        def forward(src, dst, direction, dest_host_local):
            try:
                first_packet = True
                while True:
                    data = src.recv(65535)
                    if not data:
                        break
                    
                    stats[dest_host_local]["bytes"] += len(data)
                    
                    if first_packet and direction == "c2s":
                        sni = extract_sni(data)
                        if sni:
                            log(f"  {C.M}  TLS SNI:{C.E} {sni}")
                            stats[dest_host_local]["sni"] = sni
                        
                        http_info = extract_http_info(data)
                        if http_info:
                            log(f"  {C.Y}  HTTP:{C.E} {http_info['method']} {http_info.get('path', '')}")
                            if http_info.get('host'):
                                log(f"  {C.Y}  Host:{C.E} {http_info['host']}")
                            if http_info.get('user_agent'):
                                log(f"  {C.Y}  UA:{C.E} {http_info['user_agent'][:80]}")
                        
                        first_packet = False
                    
                    dst.send(data)
            except:
                pass
            finally:
                try:
                    src.close()
                except:
                    pass
                try:
                    dst.close()
                except:
                    pass
        
        t1 = threading.Thread(target=forward, args=(client_socket, remote, "c2s", dest_host))
        t2 = threading.Thread(target=forward, args=(remote, client_socket, "s2c", dest_host))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
    except Exception as e:
        log(f"Error: {e}", C.R)
    finally:
        try:
            client_socket.close()
        except:
            pass

def print_stats():
    print(f"\n{C.M}{'='*70}{C.E}")
    print(f"{C.BOLD}  TRAFFIC ANALYSIS ({int(time.time()-start_time)}s){C.E}")
    print(f"{C.M}{'='*70}{C.E}")
    
    if source_ips:
        print(f"\n{C.G}{C.BOLD}SOURCE IPs:{C.E}")
        for ip in sorted(source_ips):
            print(f"  {C.C}{ip}{C.E}")
    
    sorted_hosts = sorted(stats.items(), key=lambda x: x[1]["bytes"], reverse=True)
    total_bytes = sum(s["bytes"] for _, s in sorted_hosts)
    total_conn = sum(s["count"] for _, s in sorted_hosts)
    
    print(f"\n{C.BOLD}TRAFFIC SUMMARY:{C.E}")
    print(f"  Total connections: {C.G}{total_conn}{C.E}")
    print(f"  Total bytes: {C.G}{total_bytes/1024:.1f} KB{C.E}")
    print(f"  Unique destinations: {C.G}{len(stats)}{C.E}")
    
    print(f"\n{C.BOLD}TOP DESTINATIONS:{C.E}")
    for i, (host, s) in enumerate(sorted_hosts[:20], 1):
        sni = s.get("sni", "")
        sni_str = f" {C.M}[{sni}]{C.E}" if sni and sni != host else ""
        print(f"  {C.BOLD}{i:2d}.{C.E} {C.G}{host:<40}{C.E} → {s['count']:>3} conn, {s['bytes']/1024:>8.1f} KB{sni_str}")
    
    print()

def main():
    print(BANNER)
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(100)
    
    log(f"Listening on 0.0.0.0:{port}", C.G)
    log(f"Waiting for victim traffic...", C.Y)
    log(f"Type 'stats' to view traffic analysis", C.Y)
    
    import select
    
    try:
        while True:
            ready = select.select([server, sys.stdin], [], [], 0.1)
            
            if server in ready[0]:
                client, addr = server.accept()
                t = threading.Thread(target=handle_client, args=(client, addr), daemon=True)
                t.start()
            
            if sys.stdin in ready[0]:
                cmd = sys.stdin.readline().strip()
                if cmd == 'stats':
                    print_stats()
                elif cmd == 'quit':
                    break
    except KeyboardInterrupt:
        log("\nStopping...", C.Y)

if __name__ == "__main__":
    main()
