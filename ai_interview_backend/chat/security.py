import socket
import struct

from django.conf import settings


def scan_attachment(data: bytes) -> tuple[bool, str, str]:
    host = str(getattr(settings, 'CLAMAV_HOST', '') or '').strip()
    required = bool(getattr(settings, 'CLAMAV_REQUIRED', False))
    if not host:
        if required:
            return False, 'clamav', 'scanner_not_configured'
        return True, 'type_validation', 'clamav_not_configured'
    try:
        with socket.create_connection((host, int(getattr(settings, 'CLAMAV_PORT', 3310))), timeout=15) as sock:
            sock.sendall(b'zINSTREAM\0')
            for offset in range(0, len(data), 64 * 1024):
                chunk = data[offset:offset + 64 * 1024]
                sock.sendall(struct.pack('!I', len(chunk)) + chunk)
            sock.sendall(struct.pack('!I', 0))
            response = sock.recv(4096).decode('utf-8', errors='replace').strip()
        if response.endswith('OK'):
            return True, 'clamav', response[:255]
        return False, 'clamav', response[:255]
    except OSError as exc:
        if required:
            return False, 'clamav', f'scanner_unavailable:{type(exc).__name__}'
        return True, 'type_validation', f'clamav_unavailable:{type(exc).__name__}'
