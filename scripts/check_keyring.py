"""Native secure-storage round trip with disposable synthetic data; no secret output."""
import os,secrets,tempfile
from fsp_client.config import Connections
with tempfile.TemporaryDirectory() as directory:
    os.environ['FSP_CONFIG_DIR']=directory
    config=Connections()
    token=secrets.token_urlsafe(32)
    try:
        config.login('qa','https://qa.invalid',token,{'role':'candidate','token_kind':'mcp'})
        assert config.load('qa')[1]==token
        assert token not in config.path.read_text()
        print('Native secure keyring round trip: PASS ('+type(config.backend()).__module__+')')
    finally:
        if 'qa' in config.read():config.logout('qa')
