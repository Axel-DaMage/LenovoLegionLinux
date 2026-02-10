#!/usr/bin/env python3
\"\"\"
Real-time Fan Speed Monitor for Lenovo Legion Linux
Displays current RPM for Fan CPU and Fan GPU
\"\"\"

import time
import sys
import glob
import os

def clear_screen():
    \"\"\"Clear the terminal screen\"\"\"
    os.system('clear' if os.name == 'posix' else 'cls')

def find_hwmon_path():
    \"\"\"Find the legion hwmon directory\"\"\"
    pattern = \"/sys/class/hwmon/hwmon*/name\"
    for name_file in glob.glob(pattern):
        try:
            with open(name_file, 'r') as f:
                if 'legion' in f.read().lower():
                    return os.path.dirname(name_file) + '/'
        except:
            continue
    return None

def read_fan_rpm(hwmon_path, fan_num):
    \"\"\"Read current RPM for specified fan\"\"\"
    try:
        fan_file = f\"{hwmon_path}fan{fan_num}_input\"
        with open(fan_file, 'r') as f:
            return int(f.read().strip())
    except:
        return -1

def read_temp(hwmon_path, sensor_num):
    \"\"\"Read temperature in Celsius\"\"\"
    try:
        temp_file = f\"{hwmon_path}temp{sensor_num}_input\"
        with open(temp_file, 'r') as f:
            # Temperature is in millidegrees
            return int(f.read().strip()) / 1000.0
    except:
        return -1

def main():
    \"\"\"Main monitoring loop\"\"\"
    hwmon_path = find_hwmon_path()
    
    if not hwmon_path:
        print(\"Error: No se encontró el hwmon de Legion\")
        print(\"Asegúrate de que el módulo legion_laptop esté cargado\")
        sys.exit(1)
    
    print(f\"Monitoreando desde: {hwmon_path}\")
    print(\"Presiona Ctrl+C para salir\\n\")
    time.sleep(2)
    
    try:
        while True:
            clear_screen()
            
            # Read fan speeds
            fan1_rpm = read_fan_rpm(hwmon_path, 1)
            fan2_rpm = read_fan_rpm(hwmon_path, 2)
            
            # Read temperatures
            cpu_temp = read_temp(hwmon_path, 1)
            gpu_temp = read_temp(hwmon_path, 2)
            
            # Display header
            print(\"=\" * 50)
            print(\"    LENOVO LEGION - MONITOR DE VENTILADORES\")
            print(\"=\" * 50)
            print()
            
            # Display fan speeds
            print(\"┌─── VELOCIDAD DE VENTILADORES ────────────────┐\")
            print(\"│                                               │\")
            
            if fan1_rpm >= 0:
                rpm_bar1 = \"█\" * int(fan1_rpm / 100)
                print(f\"│  Fan CPU:  {fan1_rpm:4d} RPM  {rpm_bar1:<45}│\")
            else:
                print(\"│  Fan CPU:  ---- RPM  [Error]                  │\")
            
            print(\"│                                               │\")
            
            if fan2_rpm >= 0:
                rpm_bar2 = \"█\" * int(fan2_rpm / 100)
                print(f\"│  Fan GPU:  {fan2_rpm:4d} RPM  {rpm_bar2:<45}│\")
            else:
                print(\"│  Fan GPU:  ---- RPM  [Error]                  │\")
            
            print(\"│                                               │\")
            print(\"└───────────────────────────────────────────────┘\")
            print()
            
            # Display temperatures
            print(\"┌─── TEMPERATURAS ──────────────────────────────┐\")
            print(\"│                                               │\")
            
            if cpu_temp >= 0:
                temp_bar_cpu = \"█\" * int(cpu_temp / 2)
                print(f\"│  CPU:      {cpu_temp:5.1f}°C  {temp_bar_cpu:<40}│\")
            else:
                print(\"│  CPU:      -----°C  [Error]                   │\")
            
            print(\"│                                               │\")
            
            if gpu_temp >= 0:
                temp_bar_gpu = \"█\" * int(gpu_temp / 2)
                print(f\"│  GPU:      {gpu_temp:5.1f}°C  {temp_bar_gpu:<40}│\")
            else:
                print(\"│  GPU:      -----°C  [Error]                   │\")
            
            print(\"│                                               │\")
            print(\"└───────────────────────────────────────────────┘\")
            print()
            
            # Update timestamp
            current_time = time.strftime(\"%Y-%m-%d %H:%M:%S\")
            print(f\"Última actualización: {current_time}\")
            print(\"\\nPresiona Ctrl+C para salir...\")
            
            time.sleep(1)  # Update every second
            
    except KeyboardInterrupt:
        clear_screen()
        print(\"\\nMonitoreo detenido.\")
        sys.exit(0)

if __name__ == \"__main__\":
    main()
