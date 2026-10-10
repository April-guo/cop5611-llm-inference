# 实验复现清单

每次正式跑实验前，把下面的空都填好；以后哪一项改了，就在这里更新。

下面的路径都在 HiPerGator 的 `/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/` 下。

---

## 1. 代码

- dllama 的 commit：`59af889085c6c0316a4524a92b42f04caa4bcc6d`（上游 b4rtaz/distributed-llama）
- 我们改过的 dllama 的 commit（没改就写"无"）：无（目前没有修改）
- 本仓库的 commit：

## 2. 编译

- 在哪个分区编译：hpg-turin
- 编译器版本：gcc 12.2.0（`module load gcc/12.2.0`）
- conda 环境：`envs/dllama-py310`（完整包列表在 `envs/dllama-py310.explicit.txt`）
- `dllama` 的 sha256：
- `dllama-api` 的 sha256：

> 只编译一次，所有实验都用这同一份程序。环境用 `source scripts/dllama-env.sh` 加载。

## 3. 模型

- 8B 来源：b4rtaz/Llama-3_1-8B-Q40-Instruct-Distributed-Llama（版本 `c4b7e78`）
- 8B 文件路径：`models/llama3_1_8b_instruct_q40/dllama_model_llama3_1_8b_instruct_q40.m`
- 8B 的 sha256：`3d4ea2faf8581a50ce4c6ca3b4467980042618ea471c0c175f6a102ee2f22304`
- 70B 来源：b4rtaz/Llama-3_3-70B-Q40-Instruct-Distributed-Llama（版本 `15da94e`）
- 70B 文件路径：`models/llama3_3_70b_instruct_q40/dllama_model_llama3_3_70b_instruct_q40.m`
- 70B 的 sha256：`0d2d2349fecf99cc9e5e141fde925029a822cedac4b76530ac1a51c484b66aad`（官方只公布了 11 个分段的值，都已核对；这是拼接后整个文件的值，由我们计算）
- tokenizer 的 sha256：`c83472ef1171f5fc2c306cf19b45f1639e6f3c260d5fb6a4888fffe5e86a4220`（8B 和 70B 的 tokenizer 是同一个文件）

> 核对方法：进入模型目录，运行 `sha256sum -c SHA256SUMS`。

## 4. 数据集

- ShareGPT 来源：anon8231489123/ShareGPT_Vicuna_unfiltered（版本 `192ab21`）
- ShareGPT 文件路径：`datasets/sharegpt/ShareGPT_V3_unfiltered_cleaned_split.json`
- ShareGPT 的 sha256：`35f0e213ce091ed9b9af2a1f0755e9d39f9ccec34ab281cd4ca60d70f6479ba4`
- LongBench 来源：zai-org/LongBench，原名 THUDM/LongBench（版本 `5e628be`）
- LongBench 文件路径：`datasets/longbench/data/`（从 `datasets/longbench/data.zip` 解压）
- LongBench 的 sha256：`cb45b11a4133c6bc1d6a44b0f8e701335ff1e543195db1103472e575857f7f64`（`data.zip`；解压出的每个文件的值在 `datasets/longbench/SHA256SUMS`）
- 用了哪些子集：

> 核对方法：进入数据集目录，运行 `sha256sum -c SHA256SUMS`。

## 5. 硬件

- 分区和 GPU 型号：hpg-turin，NVIDIA L4（23,034 MiB 显存）
- 每个节点用几块 GPU：
- 一共几个节点：
- 每个节点的 CPU 核数：
- 每个节点的内存：
- 跨节点用哪张网卡：

## 6. 运行参数

- TP 大小：
- seed：
- temperature：
- top-p：
- max-seq-len：
- net-turbo：
- buffer-float-type：q80（Q40 模型必须用这个）
- nthreads：1（GPU 后端要求）

> dllama 的 seed 默认每次都不一样，temperature 默认是 0.8，所以这些必须写死。

## 7. 输出长度

- 每个请求生成多少个 token：
- 遇到结束符停不停：

> 不同配置下生成的长度如果不一样，延迟就没法比较。

## 8. 工作负载

- trace 文件路径：
- trace 的 sha256：
- 抽样用的 seed：
- 请求数量：
- 请求到达的方式和速率：

## 9. 测量方法

- 热身几次（不计入结果）：
- 每个配置重复几次：
- 报告哪些统计量：

## 10. 每次运行要保存的记录

- 作业号、节点、开始和结束时间
- 完整的运行命令
- 驱动版本
- 同一节点上还有哪些别人的作业
- 结果文件的位置
