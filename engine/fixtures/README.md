# engine/fixtures — mock 运行样例（读取兼容测试用）

`python -m engine.run --mock --run-id fixture-mock --out engine/fixtures` 生成：契约示例 3 个来访 × mock agent × mock 路径分类器 × mock 来访 × mock 判断器。
`sessions/` 符合契约 session；`trace/` 不是契约，结构以 `engine/README.md` 的 trace 一节为准（含 `path_probs`）。内容是 mock 产物，不代表模型表现；引擎改 trace 结构时重新生成。
