from __future__ import annotations

from paperclip import artifacts


def test_read_text_artifact_truncates(tmp_path):
    artifacts_root = tmp_path / "artifacts"
    cap_id = "cap1"
    cap_dir = artifacts_root / cap_id
    cap_dir.mkdir(parents=True, exist_ok=True)

    # Write a file larger than max_bytes
    p = cap_dir / "content.txt"
    p.write_text("x" * 5000, encoding="utf-8")

    r = artifacts.read_text_artifact(
        artifacts_root=artifacts_root,
        capture_id=cap_id,
        name="content.txt",
        max_bytes=100,
    )

    assert r["exists"] is True
    assert r["truncated"] is True
    assert "… (truncated)" in r["text"]
