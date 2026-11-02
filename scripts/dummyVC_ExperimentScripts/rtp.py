import struct

RTP_VERSION = 2
RTP_PAYLOAD_TYPE = 96


class RTPPacket:
    HEADER_SIZE = 12

    @staticmethod
    def build(sequence, timestamp, ssrc, payload):
        """
        Build an RTP packet.
        """

        # Byte 0
        version = RTP_VERSION << 6
        padding = 0 << 5
        extension = 0 << 4
        csrc_count = 0

        byte1 = version | padding | extension | csrc_count

        # Byte 1
        marker = 0 << 7
        payload_type = RTP_PAYLOAD_TYPE

        byte2 = marker | payload_type

        header = struct.pack(
            "!BBHII",
            byte1,
            byte2,
            sequence,
            timestamp,
            ssrc
        )

        return header + payload

    @staticmethod
    def parse(packet):
        """
        Parse an RTP packet.
        """

        header = packet[:12]
        payload = packet[12:]

        byte1, byte2, sequence, timestamp, ssrc = struct.unpack(
            "!BBHII",
            header
        )

        version = byte1 >> 6
        payload_type = byte2 & 0x7F
        marker = byte2 >> 7

        return {
            "version": version,
            "payload_type": payload_type,
            "marker": marker,
            "sequence": sequence,
            "timestamp": timestamp,
            "ssrc": ssrc,
            "payload": payload
        }