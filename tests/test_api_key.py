import os
import pyzipper
import tempfile
import pytest

# Constants
LOCKED_ZIP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../locked_secrets/api_key.zip"))
PASSWORD = "Quantom2321999"

@pytest.fixture
def temp_workspace():
    """Provides a temporary directory for extraction tests"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

def test_api_key_unlock_success(temp_workspace):
    """Verifies that the API key zip can be successfully unlocked with the correct password."""
    assert os.path.exists(LOCKED_ZIP_PATH), "locked_secrets/api_key.zip is missing!"
    
    with pyzipper.AESZipFile(LOCKED_ZIP_PATH) as z:
        z.pwd = PASSWORD.encode('utf-8')
        z.extractall(temp_workspace)
        
    extracted_path = os.path.join(temp_workspace, "api_key.txt")
    assert os.path.exists(extracted_path), "api_key.txt was not extracted!"
    
    with open(extracted_path, "r") as f:
        key_content = f.read().strip()
        assert key_content.startswith("sk-or-v1-"), "Extracted API key doesn't have OpenRouter prefix!"

def test_api_key_unlock_failure(temp_workspace):
    """Verifies that providing an incorrect password fails securely."""
    assert os.path.exists(LOCKED_ZIP_PATH), "locked_secrets/api_key.zip is missing!"
    
    with pytest.raises(Exception):
        with pyzipper.AESZipFile(LOCKED_ZIP_PATH) as z:
            z.pwd = b'WrongPassword123'
            z.extractall(temp_workspace)
