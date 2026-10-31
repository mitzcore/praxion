"""Connectivity smoke test for the Meta Model API. Prints model id and usage, never the key."""
import os
import sys
import time
from pathlib import Path

from openai import OpenAI


def load_key() -> str:
    if os.environ.get("MODEL_API_KEY"):
        return os.environ["MODEL_API_KEY"].strip()
    key_file = Path(os.environ.get("MODEL_API_KEY_FILE", Path.home() / "meta.key"))
    if key_file.exists():
        return key_file.read_text().strip()
    sys.exit("MODEL_API_KEY not set and ~/meta.key not found")


def main() -> None:
    client = OpenAI(base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"), api_key=load_key())
    for model in sys.argv[1:] or [os.getenv("MUSE_MODEL", "muse-spark-1.3"), "muse-wonder-1.0"]:
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply exactly: ready"}],
            )
            print(f"[ok] model={r.model!s} reply={r.choices[0].message.content!r} usage={r.usage} {time.time()-t0:.1f}s")
        except Exception as e:  # noqa: BLE001
            print(f"[fail] model={model} {type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    main()
