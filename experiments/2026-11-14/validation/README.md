# 本次归档验收

- 工作区 HEAD：58c256c7e7ddad8f5d59604e72693667e9eb3f3c；分支 zhq/experiments-1114。仅只读 Git 查询，没有 fetch/rebase/add/commit。
- 初次命令：`PYTHONDONTWRITEBYTECODE=1 SAFETY_EVAL_NO_DOTENV=1 /Users/zhangheqing/bohack/ds-safety/.venv/bin/python -m pytest -q --ignore=api -p no:cacheprovider`。结果 **1225 passed, 2 failed**，18.61 秒，日志 [pytest.txt](pytest.txt)。两项均为 privacy/data/sft 被忽略的 JSONL 导出不存在，不是归档触发的逻辑错误。
- 查阅 privacy/data/README.md 后，用仓库现有 build_sft 在临时目录从原 synth/gold 只读生成 8 个导出，核对 dataset_info 与仓库原件逐字节一致，只为测试临时接入缺失 JSONL。
- 复验命令：`PYTHONDONTWRITEBYTECODE=1 /Users/zhangheqing/bohack/ds-safety/.venv/bin/python experiments/2026-11-14/scripts/validate_checkout.py`。内部执行同一指定 pytest 命令，**1227 passed in 19.68s**，见 [pytest-with-prerequisites.txt](pytest-with-prerequisites.txt) 和 [前置生成记录](sft-prerequisites.txt)。测试后 8 个链接全部移除，原数据及源码未改；因此新 checkout 裸跑仍应先按项目说明生成这些忽略产物。
- 契约命令：临时将本地 .venv 链接到指定 ds-safety 现有环境，然后 `make -o .venv/.requirements-installed contracts`；**10 个示例通过**，见 [contracts.txt](contracts.txt)。-o 只跳过安装戳依赖，不跳过校验；未安装依赖，执行后 .venv 链接已移除。没有把示例通过说成所有历史报告通过当前 schema。
- 安全/完整性命令：`python3 experiments/2026-11-14/scripts/verify_archive.py`；最终结果见 [security-scan.json](security-scan.json)，**0 命中**，包括解压检查全部 1924 个 gzip 成员，且全部 2595 条来源记录的归档 SHA256 一致。扫描不打印匹配值。
- 大小命令：`du -sh experiments/2026-11-14` 与 `du -sh experiments/2026-11-14/* experiments/2026-11-14/data/*`，见 [sizes.txt](sizes.txt)。无单文件或压缩包大于 20 MB。
- 测试通过仓库 offline fixture 禁止 socket 联网；没有执行历史实验驱动、真实 API、模型或供应商探针。版本库测试在 pytest 临时目录使用测试 git 库，不写当前或来源项目的 Git 元数据。未 commit。
