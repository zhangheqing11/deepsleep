"""Generate final data report, including aborted calls and reflector recovery."""
import shutil
from analysis.gate_diagnose import OLD
from analysis.gate_fix import OUT, REPORT, read, write_json, table
from analysis.gate_report import audit, render


def main():
    raw = OUT/'network-retries-continuation.json'
    if not raw.exists():
        shutil.copyfile(OUT/'network-retries.json', raw)
    before = read(OUT/'reflector-failed-attempt/network-retries.json')
    after = read(raw)
    write_json(OUT/'network-retries.json', {k: before[k]+after[k] for k in ('attempts','retries')})
    audit()
    render()
    failed = read(OUT/'reflector-failed-attempt/reflection.json')
    final = read(OUT/'reflection.json')
    recovery = read(OUT/'continuation.json')
    attempts = []
    for name, result in [('首次反思', failed), ('第二次反思', final)]:
        for attempt in result['attempts']:
            attempts.append([name,attempt['role'],attempt['model'],attempt['duration_s'],attempt['success']])
    extra = '\n\n## 反思失败与恢复的完整记录\n\n'
    extra += '首次主反思器在300秒上限处超时，自动降级ds flash返回无效JSON，无候选进入C门禁。仅将本次实验的反思超时上限延长至600秒，复用已完成的r0a/r0b；模型、effort、prompt、失败案例与评估配置不变。第二次主反思器成功返回后才开始C基线。上述全部请求计入总预算。\n\n'
    extra += table(['反思','尝试','模型','秒','成功'], attempts)
    extra += '\n恢复记录：`'+str(recovery)+'`。\n\n'
    extra += 'HTTP尝试包含失败、取消和重试，不等同于服务商计费条数。主表的正式重测墙钟覆盖两批A、两次反思及全部C评估（含进程恢复间隔）；停止的首次修复运行另列时间跨度。\n\n'
    extra += f'测试与SDK探针：[validation]({OUT}/validation)。当前安装的OpenAI SDK与httpx2.MockTransport离线探针：连续两次连接失败后第三次成功，记录2次重试、0次网络请求。\n'
    labels = ['r0a','r0b','C/v0','C/v0+c1','C/v0+c2','C/v0+c3']
    totals = {}
    for name, root in [('旧LLM渲染',OLD),('新template',OUT)]:
        values = [read(root/label/'summary.json') for label in labels]
        totals[name] = {'HTTP': sum(v['http_attempts'] for v in values),
                       '异常': sum(v['http_statuses'].get('error',0)+v['http_statuses'].get('http_error',0) for v in values),
                       '取消': sum(v['http_statuses'].get('cancelled',0) for v in values),
                       '降级会谈': sum(v['accounting']['degraded_sessions'] for v in values),
                       '批次墙钟之和': sum(v['wall_s'] for v in values)}
        totals[name]['异常率'] = totals[name]['异常']/totals[name]['HTTP']
    write_json(OUT/'common-six-batches.json', totals)
    extra += '\n## 相同规模六批汇总\n\n'
    extra += '仅汇总两次A40与四次C32，共208场会谈；不含反思请求、首次修复停止批次或新增r1。旧新候选内容不同，表中按序号比较运行质量。\n\n'
    extra += table(['实验','HTTP','异常','异常率','取消','降级会谈','批次墙钟之和'],
                   [[name]+[v[k] for k in ('HTTP','异常','异常率','取消','降级会谈','批次墙钟之和')] for name,v in totals.items()])
    extra += '\n## A组运行自身否决结果\n\n'
    extra += table(['运行','veto通过','原因'], [[name,read(OUT/name/'run_report.json')['veto']['passed'],
                   str(read(OUT/name/'run_report.json')['veto']['reasons'])]
                  for name in ('r0a','r0b','r1') if (OUT/name/'run_report.json').exists()])
    extra += '\nr1复用反思来源所在的A40；本次没有运行新的B组独立评估。\n'
    REPORT.write_text(REPORT.read_text()+extra)
    audit()


if __name__ == '__main__':
    main()
