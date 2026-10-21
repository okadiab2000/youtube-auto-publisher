import json
from pathlib import Path


BASE = Path(__file__).resolve().parent
QUEUE_FILE = BASE / "queue.json"
TITLES_FILE = BASE / "titles.txt"
STATE_FILE = BASE / "state.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def queue_entries(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("videos", "queue"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("queue.json must be a list or contain a videos/queue list")


def main():
    videos = queue_entries(load_json(QUEUE_FILE))
    state = load_json(STATE_FILE)
    titles = [
        line.strip()
        for line in TITLES_FILE.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]

    if not videos:
        raise RuntimeError("Queue is empty")
    if not titles:
        raise RuntimeError("titles.txt has no non-empty titles")

    video_index = int(state.get("next_video_index", 0))
    title_index = int(state.get("next_title_index", 0))

    if title_index < 0:
        raise RuntimeError(f"Invalid next_title_index={title_index}")
    if title_index >= len(titles):
        print("READ-ONLY NEXT-ITEM PREVIEW")
        print(f"Title count: {len(titles)}")
        print("TITLE_EXHAUSTED: all titles have been used; no upload should be prepared.")
        print("State and queue were not modified. No Google APIs called; no video uploaded.")
        return

    if video_index < 0 or video_index >= len(videos):
        raise RuntimeError(
            f"next_video_index={video_index} is outside queue size {len(videos)}"
        )

    video = videos[video_index]
    if not isinstance(video, dict):
        raise RuntimeError(f"Queue item {video_index} is not an object")

    filename = video.get("filename") or video.get("name") or video.get("relative_path")
    if not filename:
        raise RuntimeError(f"Queue item {video_index} has no filename")

    title = titles[title_index]

    print("READ-ONLY NEXT-ITEM PREVIEW")
    print(f"Queue size: {len(videos)}")
    print(f"Title count: {len(titles)}")
    print(f"Next video position: {video_index + 1}")
    print(f"Next filename: {filename}")
    print(f"Next title position: {title_index + 1}")
    print(f"Next title: {title}")
    print("State and queue were not modified. No Google APIs called; no video uploaded.")


if __name__ == "__main__":
    main()
