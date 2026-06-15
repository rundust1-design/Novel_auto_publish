from platforms.fanqie_main_webview import Api
import os
import sys
import webview


if __name__ == "__main__":
    api = Api()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = "file://" + os.path.join(current_dir, "platforms", "fanqie_web", "index.html").replace("\\", "/")
    window = webview.create_window(
        "?????? PRO",
        html_path,
        js_api=api,
        width=1100,
        height=770,
        min_size=(700, 500),
        frameless=False,
        text_select=True,
    )
    api.set_window(window)
    webview.start()
