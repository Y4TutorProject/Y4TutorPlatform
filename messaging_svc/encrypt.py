import os, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY = base64.b64decode(os.environ["MESSAGING_KEY"])
aes = AESGCM(KEY)

def encrypt(text: str) -> str:
    nonce = os.urandom(12)  # new random nonce for every message
    ct = aes.encrypt(nonce, text.encode(), None)
    return base64.b64encode(nonce + ct).decode()

def decrypt(blob: str) -> str:
    try:
        raw = base64.b64decode(blob)
        return aes.decrypt(raw[:12], raw[12:], None).decode()
    except Exception:
        return ""
        
# for file uploads and downloads        
def encrypt_bytes(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + aes.encrypt(nonce, data, None)

def decrypt_bytes(blob: bytes) -> bytes:
    # Raises InvalidTag if the data was altered or the key is wrong.
    return aes.decrypt(blob[:12], blob[12:], None)