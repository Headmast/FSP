"""QA-only stdio launcher using ignored synthetic tokens; product uses protected keyring."""
import json,sys
from pathlib import Path
from fsp_client.http import FspClient
from fsp_client.mcp import serve
values=json.loads(Path(sys.argv[1]).read_text())
api=FspClient(sys.argv[3],values[sys.argv[2]]['mcp'])
try:serve(api)
finally:api.close()
