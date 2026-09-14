import base64
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from Crypto.Cipher import AES

# look for .env file and load environment variables from it to memor
load_dotenv()

# Encryption key as byte string
master_key = os.getenv("MASTER_ENCRYPTION_KEY").encode()


def get_current_utc_time():
    return datetime.now(timezone.utc)


# Decrypts data <16 bytes using base64 and ECB
def decrypt_data(data: str) -> str:
    if not data or data == "N/A":
        return data
    try:
        # esp32 encrypts the data and encodes it as a base64 string
        decoded_bytes = base64.b64decode(data)  # Get bytes from base64 string
        if len(decoded_bytes) % 16 != 0:
            return data
        cipher = AES.new(master_key, AES.MODE_ECB)  # Set up cipher object
        decrypted_raw = cipher.decrypt(decoded_bytes)  # Decrypt using ECB algorithm
        decrypted_data = decrypted_raw.rstrip(b'\x00')  # Remove any null bytes
        return decrypted_data.decode('utf-8')  # Return decoded string
    except Exception as e:
        return f"Error decoding: {e}"  # Show exception
