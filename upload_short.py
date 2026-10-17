
def cmd_check_slot():
    now = datetime.now(CAIRO)

    allowed = (
        now.date() >= START_DATE
        and now.hour in ALLOWED_HOURS
    )

    output_path = os.environ.get("GITHUB_OUTPUT")

    if output_path:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"allowed={'true' if allowed else 'false'}\n")

    print(f"Cairo time: {now:%Y-%m-%d %H:%M:%S}")
    print(f"Publishing allowed: {allowed}")


def cmd_lock():
    state = load_json(STATE_FILE)
    pending = state.get("pending_upload")

    output_path = os.environ.get("GITHUB_OUTPUT")

    def report_attempt(value):
        if output_path:
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(f"attempt={'true' if value else 'false'}\n")

    if pending is None:
        print("No prepared upload. Nothing to lock.")
        report_attempt(False)
        return

    # Never automatically retry an upload with an uncertain outcome.
    if pending.get("status") == "uploading":
        print(
            "Upload outcome is unresolved. Automatic retry blocked. "
            "Check YouTube and reconcile state.json manually."
        )
        report_attempt(False)
        return

    pending["status"] = "uploading"
    pending["locked_at"] = datetime.now(CAIRO).isoformat()
    save_state(state)

    print("Upload locked. One attempt authorized.")
    report_attempt(True)
