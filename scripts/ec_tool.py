#!/usr/bin/env python3
import sys
import os
import glob
import time

def find_debug_attributes():
    # Look for the debug attributes in the platform device directory
    # The path is likely something like /sys/devices/platform/legion/* or /sys/bus/platform/devices/legion/*
    paths = glob.glob("/sys/bus/platform/devices/legion/debug_ec_addr")
    if not paths:
        # Try searching wider if not found there
        paths = glob.glob("/sys/devices/platform/legion*/debug_ec_addr")
    
    if not paths:
        return None, None
        
    base_dir = os.path.dirname(paths[0])
    return os.path.join(base_dir, "debug_ec_addr"), os.path.join(base_dir, "debug_ec_val")

def read_ec(addr):
    addr_path, val_path = find_debug_attributes()
    if not addr_path:
        print("Error: Could not find debug_ec sysfs attributes. Is the module loaded with debug support?")
        sys.exit(1)
        
    try:
        with open(addr_path, "w") as f:
            f.write(hex(addr))
            
        with open(val_path, "r") as f:
            val = f.read().strip()
            return int(val, 16)
            
    except Exception as e:
        print(f"Error reading EC register: {e}")
        sys.exit(1)

def write_ec(addr, value):
    addr_path, val_path = find_debug_attributes()
    if not addr_path:
        print("Error: Could not find debug_ec sysfs attributes.")
        sys.exit(1)
        
    try:
        with open(addr_path, "w") as f:
            f.write(hex(addr))
            
        with open(val_path, "w") as f:
            f.write(hex(value))
            
        print(f"Wrote 0x{value:02x} to 0x{addr:04x}")
            
    except Exception as e:
        print(f"Error writing EC register: {e}")
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: ec_tool.py <read|write> <addr> [value]")
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    
    try:
        addr = int(sys.argv[2], 0)
    except ValueError:
        print("Invalid address")
        sys.exit(1)
        
    if cmd == "read":
        val = read_ec(addr)
        print(f"0x{addr:04x}: 0x{val:02x}")
        
    elif cmd == "write":
        if len(sys.argv) < 4:
            print("Usage: ec_tool.py write <addr> <value>")
            sys.exit(1)
            
        try:
            val = int(sys.argv[3], 0)
        except ValueError:
            print("Invalid value")
            sys.exit(1)
            
        write_ec(addr, val)
        
    else:
        print("Unknown command")
        sys.exit(1)

if __name__ == "__main__":
    main()
