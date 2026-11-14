# 日程个性化技能（首版）

## 当前能力

- 用户通过上层界面手动维护每周重复的工作/上课时段；本模块不解析上传文件，也不连接日历。
- 每条时段只保存星期、开始/结束时间、安排类型和可调整分钟数。允许跨午夜时段；不收集单位/学校名称、地点或活动详情。
- 保存必须显式传入 `consent_granted=True`。档案仅写到调用方明确指定的本机路径；没有默认路径，不会隐式写入仓库。
- `build_schedule_context` 生成只含已确认时段的紧凑上下文。`find_conflicts` 可检查建议时段与固定安排是否重叠。
- 用户撤回同意时调用 `ScheduleProfileStore.delete()`。文件为本机 JSON，当前未加密；产品接入时需选择应用专属用户数据目录，并避免同步到日志、分析事件或评测报告。

## 接入示例

```python
from domain.schedule import ScheduleBlock, ScheduleProfile
from engine.schedule_skill import ScheduleProfileStore, load_schedule_context

store = ScheduleProfileStore(user_data_dir / "schedule-profile.json")
profile = ScheduleProfile(
    (ScheduleBlock(weekday=0, start="09:00", end="17:00", kind="work"),)
)
store.save(profile, consent_granted=user_confirmed_save)
agent_context = load_schedule_context(store)
```

把 `agent_context` 作为可选的会谈上下文传给建议生成步骤；没有档案或档案为空时返回 `None`。对话应只把日程作为可执行性约束：遇到冲突时说明原因并询问用户可调整的部分，不自行改动安全规则或建议边界。

## 接入限制

当前工作区尚无会谈 agent、API 或前端，因此本次提供的是可测试的领域模型、上下文适配器和本机存储，不包含录入界面或端到端会谈接线。工作区演示仍应使用合成档案；启用真实用户数据前需补齐产品授权、存储位置和删除流程审查。

运行针对性测试：

```bash
python -m pytest tests/test_schedule_skill.py -q
```
