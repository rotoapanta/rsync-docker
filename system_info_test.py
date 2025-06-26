# system_info_test.py

import requests
import json

RASPBERRY_URL = "http://192.168.190.29:8000/status"

def fetch_raspberry_status():
    try:
        response = requests.get(RASPBERRY_URL, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[!] Error fetching Raspberry Pi status: {e}")
        return None

def display_status(data):
    print("📡 Raspberry Pi Status")
    print(f"🖥️ Hostname: {data['hostname']}")
    print(f"🌐 IP: {data['ip']}")
    print(f"💽 CPU: {data['cpu']} %")
    print(f"🧠 RAM: {data['ram']} %")
    print(f"📀 Disk: {data['disk']} %")
    print(f"🌡️ Temp: {data['temp']} °C")
    print(f"🔋 Battery: {data['battery']['voltage']} V | {data['battery']['status']}")

if __name__ == "__main__":
    status = fetch_raspberry_status()
    if status:
        display_status(status)
