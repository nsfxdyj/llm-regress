# llm-regress

LLM 应用的回归测试工具（CI for Prompts）。改了 prompt 或模型版本？跑一遍用例集，和基线对比，回归一目了然。

## Quickstart（CLI）

```bash
pip install -e .
export DEEPSEEK_API_KEY=sk-...   # 任意 OpenAI 兼容端点
llm-regress init suite.yaml      # 生成示例用例集
llm-regress baseline suite.yaml  # 建立基线
# … 修改 prompt 或换模型后：
llm-regress run suite.yaml       # 有回归则退出码 1，可直接挂 CI
```

`init` 生成的 YAML 中 `api_key_env` 字段指定了运行所需的 API key 环境变量（默认 `DEEPSEEK_API_KEY`），执行 `baseline` / `run` 前必须先设置该变量。

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
pip install -e '.[dev]' && pytest          # 后端与核心（80+ 测试）
cd web && npm test                          # 前端
```

配置文件即代码：用例集是 YAML，可 git 管理、可 CI 运行。
