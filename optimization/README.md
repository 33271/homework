# GateANN 搜索预算优化原型

这是课程适配器之外的按工作负载分桶选择 L 的批处理原型，不修改 GateANN C++ 搜索内核。
使用时将 optimization 目录放在课程仓库根目录，与原有 adapters 目录并列；代码包不包含数据、索引或第三方系统源码。
校准输入必须来自独立校准查询；留出评测查询不能参与预算选择。
对每个桶，从三轮 Recall 均达到目标的配置中选最小 L，并限制 L≤2560。
若任一桶没有合格配置，拒绝生成策略，不能把低召回配置包装成优化成功。
运行阶段校验固定源码提交，使用课程适配器执行搜索并保留其原有日志。

```bash
python3 optimization/test_budget.py -v
python3 optimization/gateann_budget.py calibrate --csv calibration.csv --output policy.json --calibration-id separate-calibration-v1 --target 90 --max-L 2560
python3 optimization/gateann_budget.py run --policy policy.json --bucket low --repo systems/GateANN-public --dataset-root datasets/yfcc_course_v1 --run-root course_runs --run-id heldout-r1 --dry-run
```

去掉 `--dry-run` 才会执行 Linux 查询；每个桶用不同 run-id 重复三轮。
K=10、threads=1、beamwidth=8、FullAdj=32、mem_L=0、cache_budget=0 固定。
尚未实现逐查询标签路由和逐查询截止时间。只有 L 上限，没有延迟保证。
策略记录源码版本和校准 CSV 的 SHA-256；工具不能自动证明两份查询集没有重叠，需由实验者核验。

test_budget.py 使用合成测试夹具，仅验证最小预算选择、召回拒绝、上限、重复轮和配置校验以及命令构造，不是性能数据。
已有正式结果只在 High 的部分配置达到90%；Low/Medium 无合格配置，不能由此生成完整策略。
现阶段未完成独立校准、留出集端到端测量，不能声称已提高 Recall 或降低延迟。

GitHub 交付仓库：https://github.com/33271/homework
上传时将整个 optimization 文件夹放在仓库根目录，保留目录结构。
使用时仍需把该目录放回课程仓库根目录，与原有 adapters 并列。
