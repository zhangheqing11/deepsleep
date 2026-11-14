# mocks/user_context — 用户个性化上下文（演示用，未接入会谈）

来源：JiaqiChen-tju 于 2026-11-14 直接上传到仓库根目录的 4 个文件（commit bfce076），原样移到这里，内容未改。

| 文件 | 说明 |
|---|---|
| `schedule.py` | `domain/schedule.py` 的新版本，多了 `context_notes`（≤5 条、每条 ≤2000 字）。**尚未替换** `domain/schedule.py` |
| `schedule-skill.md` | `docs/schedule-skill.md` 的新版本 |
| `image_ocr.py` | 本地 OCR：图片只在内存处理、不落盘 |
| `requirements-ocr.txt` | OCR 的可选依赖（Pillow、rapidocr-onnxruntime），不进根 `requirements.txt` |

团队决定（11/14）：智能家居与日程在路演中**只做 mock 展示，不接进会谈引擎**，以免影响两次运行的可比性。要合并进 `domain/` 请另开 PR，由作者确认。
