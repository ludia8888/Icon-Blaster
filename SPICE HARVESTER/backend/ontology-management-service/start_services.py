#!/usr/bin/env python3
"""
Start BFF and OMS services for testing
"""

import subprocess
import time
import sys
import os
import signal
import requests

def start_service(name, path, command, port):
    """Start a service and verify it's running"""
    print(f"\nStarting {name}...")
    
    # Change to service directory
    original_dir = os.getcwd()
    os.chdir(path)
    
    # Start the service
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid
    )
    
    os.chdir(original_dir)
    
    # Wait for service to start
    max_attempts = 30
    for i in range(max_attempts):
        try:
            response = requests.get(f"http://localhost:{port}/health")
            if response.status_code == 200:
                print(f"✅ {name} started successfully on port {port}")
                return process
        except (requests.ConnectionError, requests.Timeout):
            # 서비스가 아직 시작 중일 수 있음 - 정상적인 상황
            pass
        except Exception as e:
            # 다른 예외는 로그를 남김
            print(f"⚠️ {name} health check error: {type(e).__name__}: {e}")
        
        # Check if process is still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            print(f"❌ {name} failed to start!")
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            return None
            
        time.sleep(1)
        
    print(f"❌ {name} failed to respond after {max_attempts} seconds")
    return None

def stop_services(processes):
    """Stop all services"""
    print("\nStopping services...")
    for name, process in processes.items():
        if process:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                print(f"✅ Stopped {name}")
            except ProcessLookupError:
                # 프로세스가 이미 종료됨 - 정상
                pass
            except Exception as e:
                print(f"⚠️ Error stopping {name}: {type(e).__name__}: {e}")

def main():
    processes = {}
    
    # Paths
    oms_path = "/Users/isihyeon/Desktop/SPICE HARVESTER/backend/ontology-management-service"
    bff_path = "/Users/isihyeon/Desktop/SPICE FOUNDRY/backend/backend-for-frontend"
    
    # Ensure BFF directory exists
    os.makedirs(bff_path, exist_ok=True)
    
    # Check if main.py exists in both locations
    if not os.path.exists(os.path.join(oms_path, "main.py")):
        print(f"❌ OMS main.py not found at {oms_path}")
        return 1
        
    if not os.path.exists(os.path.join(bff_path, "main.py")):
        print(f"❌ BFF main.py not found at {bff_path}")
        # Try to find it
        print("Searching for BFF main.py...")
        for root, dirs, files in os.walk("/Users/isihyeon/Desktop/SPICE FOUNDRY"):
            if "main.py" in files and "backend-for-frontend" in root:
                bff_path = root
                print(f"Found BFF at: {bff_path}")
                break
    
    try:
        # Start OMS first (backend)
        oms_process = start_service(
            "OMS",
            oms_path,
            "python -m uvicorn main:app --host 0.0.0.0 --port 8000",
            8000
        )
        
        if not oms_process:
            return 1
            
        processes["OMS"] = oms_process
        
        # Start BFF (frontend)
        bff_process = start_service(
            "BFF", 
            bff_path,
            "python -m uvicorn main:app --host 0.0.0.0 --port 8002",
            8002
        )
        
        if not bff_process:
            stop_services(processes)
            return 1
            
        processes["BFF"] = bff_process
        
        print("\n✅ All services started successfully!")
        print("\nServices running:")
        print("  - OMS: http://localhost:8000")
        print("  - BFF: http://localhost:8002")
        print("\nPress Ctrl+C to stop services...")
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        stop_services(processes)
        
    return 0

if __name__ == "__main__":
    sys.exit(main())