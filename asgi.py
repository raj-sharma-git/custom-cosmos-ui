import importlib.util
from a2wsgi import WSGIMiddleware

# Dynamically import the cosmos-ui module because hyphens in filenames
# prevent standard Python imports (e.g. `import cosmos-ui` is a SyntaxError).
spec = importlib.util.spec_from_file_location("cosmos_ui", "cosmos-ui.py")
cosmos_ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cosmos_ui)

# Wrap the WSGI Flask app with a2wsgi so Uvicorn can run it natively as ASGI
app = WSGIMiddleware(cosmos_ui.app)
