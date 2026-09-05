# llm-regress

LLM 应用的回归测试工具（CI for Prompts）。改了 prompt 或模型版本？跑一遍用例集，和基线对比，回归一目了然。

## Quickstart（CLI）

```bash
pip install llm-regress-ci       # 从 PyPI 安装（包名 llm-regress-ci，命令仍为 llm-regress）
# 或从源码安装：pip install -e .
export DEEPSEEK_API_KEY=sk-...   # 任意 OpenAI 兼容端点
llm-regress init suite.yaml      # 生成示例用例集
llm-regress baseline suite.yaml  # 建立基线
# … 修改 prompt 或换模型后：
llm-regress run suite.yaml       # 有回归则退出码 1，可直接挂 CI
```

`init` 生成的 YAML 中 `api_key_env` 字段指定了运行所需的 API key 环境变量（默认 `DEEPSEEK_API_KEY`），执行 `baseline` / `run` 前必须先设置该变量。

## CI 集成

### GitHub Action（推荐）

仓库根目录自带 composite action，一行接入：

```yaml
- uses: nsfxdyj/llm-regress@main
  with:
    suite-file: suite.yaml      # 必填，用例集路径
    # python-version: "3.12"    # 可选，运行 llm-regress 的 Python 版本
    # format: github            # 可选：github（默认，::error 注解 + Job Summary）| junit | html
    # output: report.xml        # 可选，仅当 format 为 junit/html 时生效
```

完整可复制的工作流（含 HTML 报告 artifact 与 PR 评论）见 [examples/github-action.yaml](examples/github-action.yaml)。

### 报告格式（JUnit / GitHub / HTML）

`run` / `baseline` 支持可重复的 `--format` 与 `--output`；`--output` 按顺序与文件类 `--format`（`junit` / `html`）一一配对，`console` 永远照常打印：

```bash
# console 之外追加 JUnit XML（可直接被 CI 的测试结果面板消费）
llm-regress run suite.yaml --format junit --output report.xml

# GitHub Actions 原生输出：::error 注解 + $GITHUB_STEP_SUMMARY 摘要（不消费 --output）
llm-regress run suite.yaml --format github

# 独立 HTML 报告（单文件、无外部依赖，适合作为 artifact）
llm-regress run suite.yaml --format html --output report.html

# 多种文件类格式一次生成，按顺序配对
llm-regress run suite.yaml --format junit --format html --output report.xml --output report.html
```

退出码语义不变：有回归 → 1，用例执行出错 → 2，配置/环境错误 → 3，可直接挂 CI。

### PR 评论

每次运行会在 `.llm-regress/runs/` 落盘一份 JSON；`comment` 子命令把它发布（或幂等更新）为 PR 评论：

```bash
export GITHUB_TOKEN=...   # 需要 pull-requests 写权限
llm-regress comment --repo owner/name --pr 123 --run-file .llm-regress/runs/<stamp>.json
```

评论正文与 GitHub Job Summary 共用同一份 markdown 摘要；重复执行会更新同一条评论而不是刷屏。

## Web 管理台

```bash
llm-regress-server               # 后端 http://127.0.0.1:8000
cd web && npm install && npm run dev   # 前端 http://localhost:5173
```

## 评测分三层

1. **规则断言**（关键词 / JSON / 正则 / 长度）——零成本、可复现
2. **语义相似度**（embedding 余弦）——低成本
3. **LLM-as-judge**（rubric 打分 / 成对比较）——裁判模型绑定基线，更换裁判需重建基线

## 开发

```bash
pip install -e '.[dev]' && pytest          # 后端与核心（130+ 测试）
cd web && npm test                          # 前端
```

配置文件即代码：用例集是 YAML，可 git 管理、可 CI 运行。
