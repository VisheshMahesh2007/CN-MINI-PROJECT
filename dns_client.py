import socket
import sys
import time

DOMAIN = sys.argv[1] if len(sys.argv) > 1 else 'web.local'
BROADCAST_IP = sys.argv[2] if len(sys.argv) > 2 else '10.0.0.255'
PORT = 5555
TIMEOUT = 2.0
MAX_ATTEMPTS = 3

def send_query():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(TIMEOUT)

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"[*] Sending query for {DOMAIN} (Attempt {attempt})...")
            start_time = time.time()
            sock.sendto(DOMAIN.encode(), (BROADCAST_IP, PORT))
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                print("[-] Request timed out. Retrying...")
                continue

            latency = (time.time() - start_time) * 1000
            print(f"[+] Response from {addr[0]}: {data.decode()}")
            print(f"[!] Latency: {latency:.2f} ms\n")
            return True

        print(f"[!] Failed to resolve {DOMAIN} after {MAX_ATTEMPTS} attempts.")
        return False
    finally:
        sock.close()

if __name__ == '__main__':
    sys.exit(0 if send_query() else 1)
