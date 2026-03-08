#!/usr/bin/env python3
import os
import time
import subprocess

def get_ec_scan():
    try:
        # Trigger a read of powermode to get the scan in dmesg
        subprocess.run(["cat", "/sys/bus/platform/drivers/legion/PNP0C09:00/powermode"], 
                       capture_output=True, check=True)
        # Wait a bit for dmesg to update
        time.sleep(0.5)
        # Get last scan from dmesg
        out = subprocess.check_output("sudo dmesg | grep -i 'ec_read_powermode scan' -A 1000 | tail -n 1000", shell=True).decode()
        
        regs = {}
        for line in out.splitlines():
            if "reg 0x" in line:
                parts = line.split()
                try:
                    addr = parts[-3].rstrip(":")
                    val = parts[-1]
                    regs[addr] = val
                except:
                    continue
        return regs
    except Exception as e:
        print(f"Error: {e}")
        return {}

def main():
    print("Monitoring EC registers. Please change pull fan/power modes or press Fn+Q...")
    last_regs = get_ec_scan()
    try:
        while True:
            time.sleep(1)
            current_regs = get_ec_scan()
            if not current_regs:
                continue
                
            changes = []
            for addr, val in current_regs.items():
                if addr in last_regs and last_regs[addr] != val:
                    changes.append(f"{addr}: {last_regs[addr]} -> {val}")
                elif addr not in last_regs:
                    changes.append(f"{addr}: NEW -> {val}")
                    
            if changes:
                print(f"[{time.strftime('%H:%M:%S')}] Changes detected:")
                for c in changes:
                    print(f"  {c}")
                last_regs = current_regs
    except KeyboardInterrupt:
        print("\nStopping.")

if __name__ == "__main__":
    main()
