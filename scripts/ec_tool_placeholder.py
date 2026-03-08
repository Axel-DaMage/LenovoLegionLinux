#!/usr/bin/env python3
import sys
import os

EC_BASE = 0xC400
EC_SIZE = 0x300

def read_ec(offset):
    # This relies on the driver's debugfs or similar if available, 
    # OR we can abuse the powermode scan if we didn't remove it.
    # But wait, the driver exposes 'fancurve' and other things.
    # Actually, we can use the 'fan_fullspeed' attribute to trigger a write?
    # No, we want arbitrary access.
    # The 'legion-laptop' driver doesn't expose raw EC access to userspace easily 
    # unless we added a debugfs interface.
    # HOWEVER, we can stick to using the 'monitor_ec.py' approach of parsing dmesg 
    # AFTER triggering a read via a known attribute?
    # Better: We can use /dev/port if we know the port? 
    # Legion uses EC RAM via MMIO or Port IO.
    # The driver maps it.
    pass

# Simplified: We will compile a small C program that uses ioctl or iopl if possible?
# No, easier: update legion-laptop.c to expose a debug sysfs file for reading/writing arbitrary EC.
# OR, use the existing 'monitor_ec.py' parsing logic and 'echo' to known attributes.
# But we want to WRITE arbitrary values.

# Let's modify legion-laptop.c to add a 'debug_ec_reg' and 'debug_ec_val' attribute.
pass
