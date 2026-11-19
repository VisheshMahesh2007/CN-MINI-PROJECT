import socket
import sys
import time

SERVER_IP = sys.argv[1] if len(sys.argv) > 1 else '0.0.0.0'
PORT = 5555
LOOKUP_DELAY = 0.5

RECORDS = {
    'web.local': '192.168.1.100',
    'mail.local': '192.168.1.101',
    'ftp.local': '192.168.1.102',
    'db.local': '192.168.1.103',
}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((SERVER_IP, PORT))
print(f"[*] DNS Server listening on {SERVER_IP}:{PORT}")

try:
    while True:
        data, addr = sock.recvfrom(1024)
        domain = data.decode(errors='ignore').strip()
        print(f"[+] Received query for {domain} from {addr[0]}:{addr[1]}")

        time.sleep(LOOKUP_DELAY)

        answer = RECORDS.get(domain, 'NXDOMAIN')
        sock.sendto(f"{domain}: {answer}".encode(), addr)
        print(f"[+] Replied {domain} -> {answer}")
except KeyboardInterrupt:
    print("\n[!] Server stopped")
finally:
    sock.close()
