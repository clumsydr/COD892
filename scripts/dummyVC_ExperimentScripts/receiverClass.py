import struct
 
from rtp import RTPPacket
 
 
class RTPReceiver:
 
    def __init__(self, sock, sender):
 
        self.sock = sock
        self.sender = sender
 
        print("===================================")
        print(" RTP Receiver")
        print("===================================")
        print("Receiver is ready.")
        print("===================================\n")
 
    def process_packet(self, packet, addr):
 
        # Parse RTP
        info = RTPPacket.parse(packet)
 
        # Parse application header
        frame_number, packet_number = struct.unpack(
            "!IH",
            info["payload"][:6]
        )
 
        print("----------------------------------")
        print(f"Received From : {addr}")
        print(f"Frame         : {frame_number}")
        print(f"Packet        : {packet_number}")
        print(f"Sequence      : {info['sequence']}")
        print(f"Timestamp     : {info['timestamp']}")
        print(f"SSRC          : {info['ssrc']}")
        print(f"Payload Size  : {len(info['payload'])} bytes")
 
    def run(self):
 
        print("Receiver started...\n")
 
        while True:
 
            packet, addr = self.sock.recvfrom(2048)
            self.sender.set_peer(addr[0], addr[1])
            print("received address", addr[0], addr[1])
            self.process_packet(packet, addr)
 