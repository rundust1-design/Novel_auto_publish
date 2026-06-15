import os


def _anti_detect_init_script():
    """Return a JS init script that hides Playwright automation traces."""
    return """
        // Overwrite the 'webdriver' property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });

        // Overwrite the 'plugins' array to look like a real browser
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Overwrite the 'languages' property
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en'],
        });

        // Remove 'chrome' from runtime if present (Playwright adds it)
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Override the chrome object
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {},
        };

        // Ensure plugins have mimetypes
        if (navigator.plugins && navigator.plugins.length === 0) {
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
                ],
            });
        }
    """


def launch_anti_detect_browser(playwright, headless=False):
    """Launch a Chromium browser with anti-detection measures.

    This helps bypass slider captchas and other bot-detection on platforms
    like Qimao (七猫) that check for automation flags.
    """
    args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-features=IsolateOrigins,site-per-process',
        '--disable-site-isolation-trials',
        '--disable-web-security',
        '--disable-features=BlockInsecurePrivateNetworkRequests',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-gpu',
        '--disable-gpu-compositing',
        '--disable-accelerated-2d-canvas',
        '--disable-accelerated-video-decode',
        '--disable-software-rasterizer',
        '--disable-dev-shm-usage',
    ]

    if headless:
        args.append('--headless=new')

    browser = playwright.chromium.launch(
        headless=False,  # we handle headless via args for better stealth
        args=args,
    )
    return browser


def create_anti_detect_context(browser, storage_state=None):
    """Create a browser context with anti-detection init scripts."""
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        storage_state=storage_state,
    )
    context.add_init_script(_anti_detect_init_script())
    return context
