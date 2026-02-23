import pyzipper
import os

key_path = "api_key.txt"
zip_path = "locked_secrets/api_key.zip"

with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
    zf.setpassword(b'Quantom2321999')
    zf.write(key_path, os.path.basename(key_path))
print("Zipped successfully")
