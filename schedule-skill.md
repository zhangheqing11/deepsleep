# 日程与图片上下文技能

## 当前能力

- 用户可通过上层界面维护每周重复的工作/上课时段；本模块不连接日历。
- 每条时段只保存星期、开始/结束时间、安排类型和可调整分钟数。允许跨午夜时段；不收集单位/学校名称、地点或活动详情。
- 上传图片后可用 `engine.image_ocr.extract_image_text()` 在本机 OCR；当前接受 JPEG、PNG、WebP、BMP，单张不超过 10 MiB / 20 MP。动图不支持。图片只在内存处理，不落盘、不发给外部服务。
- OCR 结果必须先展示给用户确认和编辑，之后才可作为 `ScheduleProfile.context_notes` 保存并进入 agent 上下文；最多 5 条、每条 2000 字。上下文会明确标注 OCR 文本可能有误，含糊信息应先向用户确认。
- 本地 OCR 不会上传图片；但确认后的上下文若随会谈发送给云端模型，会成为模型请求内容。产品接入需向用户说明并取得相应同意。
- 保存必须显式传入 `consent_granted=True`。档案仅写到调用方明确指定的本机路径；没有默认路径，不会隐式写入仓库。
- `build_schedule_context` 生成只含已确认时段与文字的紧凑上下文。`find_conflicts` 可检查建议时段与固定安排是否重叠。
- 用户撤回同意时调用 `ScheduleProfileStore.delete()`。文件为本机 JSON，当前未加密；产品接入时需选择应用专属用户数据目录，并避免同步到日志、分析事件或评测报告。

安装可选 OCR 依赖：

```bash
python -m pip install -r requirements-ocr.txt
```

无需 OCR 时，不需要安装这些可选依赖。

## 接入示例

```python
from engine.image_ocr import extract_image_text
from domain.schedule import ScheduleBlock, ScheduleProfile
from engine.schedule_skill import ScheduleProfileStore, load_schedule_context

# Web/API 上传处理器将上传内容读成 bytes；先把识别文本展示给用户确认/编辑。
ocr_result = extract_image_text(uploaded_image_bytes)
confirmed_text = user_review_and_edit(ocr_result.text)

store = ScheduleProfileStore(user_data_dir / "schedule-profile.json")
profile = ScheduleProfile(
    (ScheduleBlock(weekday=0, start="09:00", end="17:00", kind="work"),),
    context_notes=(confirmed_text,),
)
store.save(profile, consent_granted=user_confirmed_save)
agent_context = load_schedule_context(store)
```

把 `agent_context` 作为可选的会谈上下文传给建议生成步骤；没有档案或档案为空时返回 `None`。对话应只把日程作为可执行性约束：遇到冲突时说明原因并询问用户可调整的部分，不自行改动安全规则或建议边界。

## 接入限制

当前交付提供领域模型、本机 OCR、上下文适配器和本机存储；没有上传 UI/API，也没有自动从 OCR 表格推断结构化日程。上层接入时应允许用户预览/编辑识别结果，明确同意后再保存；演示仍应使用合成档案。图片和 OCR 内容可能包含隐私信息，启用真实用户数据前需审查授权、存储位置、访问控制和删除流程。

运行针对性测试：

```bash
python -m unittest tests.test_schedule_skill -v
```
