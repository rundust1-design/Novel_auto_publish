import argparse
import os
from playwright.sync_api import sync_playwright
from platform_config import DEFAULT_PLATFORM, get_platform
from platform_utils import attach_dialog_handler, detect_web_security_block, dismiss_platform_popups
from anti_detect import launch_anti_detect_browser, create_anti_detect_context


def resolve_existing_state_file(platform):
    candidates = [platform["state_file"], *platform.get("fallback_state_files", [])]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def login(platform_key=DEFAULT_PLATFORM, headless=False):
    if platform_key == "fanqie" and not headless:
        from platforms.fanqie_login import login as fanqie_login
        return fanqie_login()

    platform = get_platform(platform_key)
    state_file = platform["state_file"]
    existing_state_file = resolve_existing_state_file(platform)

    print(f"Starting browser for {platform.get('product_name', platform['key'])}...")
    with sync_playwright() as p:
        browser = launch_anti_detect_browser(p, headless=headless)
        if existing_state_file:
            print(f"Found {existing_state_file}; loading existing login state...")
            context = create_anti_detect_context(browser, storage_state=existing_state_file)
        else:
            context = create_anti_detect_context(browser)

        page = context.new_page()
        attach_dialog_handler(page)
        print(f"Opening {platform.get('product_name', platform['key'])} writer backend...")
        try:
            page.goto(platform["login_url"], timeout=60000)
        except Exception as e:
            print(f"Failed to open page, please check network: {e}")
            print(f"Browser remains open; manually visit {platform['login_url']} if needed.")

        print("\n" + "=" * 50)
        print(f"Please log in to your {platform.get('product_name', platform['key'])} writer account in the browser.")
        print("After the writer dashboard appears, return here and press Enter to save state.")
        print("=" * 50 + "\n")

        input(">>> Press Enter after login is complete: ")
        try:
            if platform["key"] == "faloo":
                page.goto(platform["book_manage_url"], timeout=60000)
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                detect_web_security_block(page)
                dismiss_platform_popups(page, platform)
        except Exception as exc:
            print(f"[WARN] Failed to verify writer backend before saving state: {exc}")
        context.storage_state(path=state_file)
        print(f"\nLogin state saved to {state_file}.")
        print("Future publish runs will load this state automatically.")
        browser.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Save writer backend login state.")
    parser.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM, help="Platform key, e.g. qidian, fanqie, faloo, or qimao.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Not recommended for manual login.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    login(args.platform, headless=args.headless)
