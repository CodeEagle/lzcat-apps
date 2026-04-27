from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.discord_attachment_recognition import (
    AttachmentRecognitionConfig,
    AttachmentRecognitionResult,
    build_attachment_instruction,
    classify_attachment,
    recognize_message_attachments,
)


class DiscordAttachmentRecognitionTest(unittest.TestCase):
    def test_classify_image_and_audio_attachments(self) -> None:
        self.assertEqual(classify_attachment({"content_type": "image/png", "filename": "shot.png"}), "image")
        self.assertEqual(classify_attachment({"content_type": "audio/ogg", "filename": "voice.ogg"}), "audio")
        self.assertEqual(classify_attachment({"content_type": "application/zip", "filename": "data.zip"}), "")

    def test_build_attachment_instruction_includes_recognition_results(self) -> None:
        instruction = build_attachment_instruction(
            "看一下这个",
            [
                AttachmentRecognitionResult(
                    kind="image",
                    filename="shot.png",
                    url="https://cdn.example/shot.png",
                    status="recognized",
                    text="图片中是一个报错弹窗。",
                ),
                AttachmentRecognitionResult(
                    kind="audio",
                    filename="voice.m4a",
                    url="https://cdn.example/voice.m4a",
                    status="recognized",
                    text="请继续处理 piclaw。",
                ),
            ],
        )

        self.assertIn("看一下这个", instruction)
        self.assertIn("附件识别结果", instruction)
        self.assertIn("图片中是一个报错弹窗", instruction)
        self.assertIn("请继续处理 piclaw", instruction)

    def test_recognize_message_attachments_logs_inputs_outputs_and_decisions(self) -> None:
        repo_root = Path(tempfile.mkdtemp(prefix="attachment-recognition-test-"))
        config = AttachmentRecognitionConfig(repo_root=repo_root, enabled=True)
        calls: list[dict[str, object]] = []

        def recognizer(attachment: dict[str, object], kind: str) -> AttachmentRecognitionResult:
            calls.append({"attachment": attachment, "kind": kind})
            return AttachmentRecognitionResult(
                kind=kind,
                filename=str(attachment["filename"]),
                url=str(attachment["url"]),
                status="recognized",
                text=f"{kind} text",
            )

        results = recognize_message_attachments(
            {
                "id": "message-1",
                "attachments": [
                    {"filename": "shot.png", "content_type": "image/png", "url": "https://cdn.example/shot.png"},
                    {"filename": "voice.ogg", "content_type": "audio/ogg", "url": "https://cdn.example/voice.ogg"},
                ],
            },
            config,
            now="2026-04-27T10:00:00Z",
            recognizer=recognizer,
        )

        self.assertEqual([result.kind for result in results], ["image", "audio"])
        self.assertEqual(len(calls), 2)
        log_path = repo_root / "registry" / "auto-migration" / "logs" / "attachment-runs" / "20260427T100000Z.jsonl"
        events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[0]["stage"], "attachment_recognition")
        self.assertEqual(events[0]["item_id"], "message-1")
        self.assertEqual(events[0]["inputs"]["attachment"]["filename"], "shot.png")
        self.assertEqual(events[0]["outputs"]["text"], "image text")
        self.assertEqual(events[0]["decision"]["status"], "recognized")


if __name__ == "__main__":
    unittest.main()
