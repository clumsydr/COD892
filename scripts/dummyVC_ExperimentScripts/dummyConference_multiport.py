import socket
import threading

from senderClass import RTPSender
from receiverClass import RTPReceiver

# ----------------------------
# Configuration
# ----------------------------
LOCAL_IP = "0.0.0.0"
PEER_IP = "34.131.126.205"  # Target peer IP address

# Define all the ports you want to capture/send data on
PORTS = [5004, 5006]  

threads = []
sockets = []

print(f"[*] Initializing Multi-Port Conference Endpoint across ports: {PORTS}\n")

for port in PORTS:
    # ----------------------------
    # 1. Create & Bind Socket per Port
    # ----------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Enable address/port reuse if quickly restarting script
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    sock.bind((LOCAL_IP, port))
    sockets.append(sock)
    print(f"[+] Socket bound on {LOCAL_IP}:{port}")

    # ----------------------------
    # 2. Instantiate Sender & Receiver
    # ----------------------------
    # Note: If your RTPReceiver requires passing the socket, update it like: RTPReceiver(sock=sock)
    sender = RTPSender(
        sock=sock,
        peer_ip=PEER_IP,
        peer_port=port,
        bitrate=5_000_000,
        fps=30,
        payload_size=1200,
    )

    receiver = RTPReceiver()

    # ----------------------------
    # 3. Create Threads for Port
    # ----------------------------
    sender_thread = threading.Thread(
        target=sender.run,
        name=f"Sender-Port-{port}",
        daemon=True
    )
    
    receiver_thread = threading.Thread(
        target=receiver.run,
        name=f"Receiver-Port-{port}",
        daemon=True
    )

    threads.extend([sender_thread, receiver_thread])

# ----------------------------
# Start All Threads
# ----------------------------
for t in threads:
    t.start()

print(f"\n[✓] Multi-Port Conference Endpoint active ({len(threads)} worker threads running).\n")

# ----------------------------
# Keep Main Thread Alive
# ----------------------------
try:
    for t in threads:
        t.join()
except KeyboardInterrupt:
    print("\n[*] Shutting down multi-port endpoint...")
    for s in sockets:
        s.close()