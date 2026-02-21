import sys
sys.path.insert(0, "cactus/python/src")

import webview
from api import Api

api = Api()
window = webview.create_window(
    "Voice Routines",
    url="frontend/index.html",
    js_api=api,
    width=1200,
    height=800,
)
api.set_window(window)
webview.start(debug=True)
api.cleanup()
