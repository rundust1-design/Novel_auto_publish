import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from publish import main as publish_main


def main(book_name=None, publish_count=None, volume_num=None, no_prompt=False, headless=False):
    return publish_main(
        platform_key="haiduxiaoshuo",
        book_name=book_name,
        publish_count=publish_count,
        volume_num=volume_num,
        no_prompt=no_prompt,
        headless=headless,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Publish chapters to Haiduxiaoshuo using the shared publisher.")
    parser.add_argument("--book", help="Book folder name to publish. Defaults to first book in --no-prompt mode.")
    parser.add_argument("--count", type=int, help="Number of chapters to publish. Defaults to all.")
    parser.add_argument("--volume", type=int, help="Archive volume number. Defaults to no volume subfolder.")
    parser.add_argument("--no-prompt", action="store_true", help="Never wait for console input; fail fast on manual steps.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode for scheduled tasks.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main(
        book_name=args.book,
        publish_count=args.count,
        volume_num=args.volume,
        no_prompt=args.no_prompt,
        headless=args.headless,
    ))
