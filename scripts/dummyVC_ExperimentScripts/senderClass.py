import math
import os
import random
import socket
import struct
import time
 
from rtp import RTPPacket
 
 
class RTPSender:
 
    def __init__(
        self,
        sock,
        peer_ip=None,
        peer_port=None,
        bitrate=2_000_000,
        fps=30,
        payload_size=1200,
    ):
 
        self.sock = sock
        self.peer_ip = peer_ip
        self.peer_port = peer_port
 
        self.sequence = 0
        self.timestamp = 0
        self.ssrc = random.randint(0, 2**32 - 1)
 
        self.bitrate = bitrate
        self.fps = fps
        self.payload_size = payload_size
 
        self.timestamp_increment = 90000 // self.fps
 
        self.bytes_per_second = self.bitrate // 8
        self.bytes_per_frame = self.bytes_per_second / self.fps
 
        self.packets_per_frame = math.ceil(
            self.bytes_per_frame / self.payload_size
        )
 
        self.frame_size = round(self.bytes_per_frame)
 
        self.frame_number = 0
 
        print("===================================")
        print(" RTP Sender")
        print("===================================")
        print(f"SSRC               : {self.ssrc}")
        print(f"Bitrate            : {self.bitrate} bps")
        print(f"FPS                : {self.fps}")
        print(f"Frame Size         : {self.frame_size} bytes")
        print(f"Packets / Frame    : {self.packets_per_frame}")
        print("===================================\n")
    
    def set_peer(self, ip, port):
 
        if self.peer_ip != ip or self.peer_port != port:
            print(f"Peer updated to {ip}:{port}")
 
        self.peer_ip = ip
        self.peer_port = port
 
    def create_frame_packets(self):
 
        packets = []
 
        remaining_bytes = self.frame_size
 
        for packet_in_frame in range(self.packets_per_frame):
 
            app_header = struct.pack(
                "!IH",
                self.frame_number,
                packet_in_frame
            )
 
            current_payload_size = min(
                self.payload_size,
                remaining_bytes
            )
 
            dummy_data = os.urandom(
                current_payload_size - len(app_header)
            )
 
            remaining_bytes -= current_payload_size
 
            payload = app_header + dummy_data
 
            packet = RTPPacket.build(
                sequence=self.sequence,
                timestamp=self.timestamp,
                ssrc=self.ssrc,
                payload=payload
            )
 
            packets.append(packet)
 
            self.sequence = (self.sequence + 1) % 65536
 
        self.frame_number += 1
        self.timestamp += self.timestamp_increment
 
        return packets
 
    def run(self):
 
        print("Starting RTP sender...\n")
 
        while True:
 
            if self.peer_ip is None or self.peer_port is None:
                time.sleep(0.1)
                continue
            
            packets = self.create_frame_packets()
 
            for packet in packets:
 
                self.sock.sendto(
                    packet,
                    (self.peer_ip, self.peer_port)
                )
 
            print(
                f"Sent Frame {self.frame_number - 1} "
                f"({len(packets)} RTP packets)"
            )
 
            time.sleep(1 / self.fps)