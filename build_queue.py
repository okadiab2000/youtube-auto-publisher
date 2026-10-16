
import json
from pathlib import Path
from datetime import datetime
from collections import Counter

# Folder containing your videos
BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "videos"
OUTPUT_FILE = BASE_DIR / "queue.json"

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"
}


def main():
    if not VIDEO_DIR.is_dir():
        print(f"ERROR: Videos folder not found: {VIDEO_DIR}")
        print("Create a folder named 'videos' next to this script.")
        return

    files = [
        path
        for path in VIDEO_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]

    if not files:
        print("No supported video files found.")
        return

    # Sort by Date modified, oldest first.
    # Use the relative path to make ties deterministic.
    files.sort(
        key=lambda path: (
            path.stat().st_mtime,
            path.relative_to(VIDEO_DIR).as_posix().casefold()
        )
    )

    queue = []

    for index, path in enumerate(files, start=1):
        stat = path.stat()

        queue.append({
            "position": index,
            "filename": path.name,
            "relative_path": path.relative_to(VIDEO_DIR).as_posix(),
            "modified_timestamp": stat.st_mtime,
            "modified_time": datetime.fromtimestamp(
                stat.st_mtime
            ).astimezone().isoformat(timespec="seconds"),
            "size_bytes": stat.st_size
        })

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(queue, file, ensure_ascii=False, indent=2)

    # Count identical modification timestamps
    timestamp_counts = Counter(
        item["modified_timestamp"] for item in queue
    )
    tied_groups = sum(
        1 for count in timestamp_counts.values() if count > 1
    )

    print(f"\nFound {len(queue)} videos.")
    print(f"Queue saved to: {OUTPUT_FILE}")
    print("Order: oldest Date modified -> newest Date modified")

    if tied_groups:
        print(
            f"Note: {tied_groups} timestamp group(s) contain "
            "multiple files. Relative paths break ties."
        )

    print("\nFirst 10 videos in the queue:")

    for item in queue[:10]:
        print(
            f"{item['position']:04d}. "
            f"{item['modified_time']} | "
            f"{item['relative_path']}"
        )

    print("\nLast 3 videos in the queue:")

    for item in queue[-3:]:
        print(
            f"{item['position']:04d}. "
            f"{item['modified_time']} | "
            f"{item['relative_path']}"
        )


if __name__ == "__main__":
    main()
