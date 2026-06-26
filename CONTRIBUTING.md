# 贡献指南

感谢你对萦回 (Yinghui) 的关注！在提交贡献之前，请先阅读以下内容。

## 法律前提

本项目采用 AGPL v3 + 商业授权双许可证模式。提交 Pull Request 前请阅读
[CLA.md](CLA.md)（贡献者许可协议）。通过提交 PR，你确认接受 CLA 条款。

## 开发环境搭建

### 后端

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，至少填入 LLM_API_KEY
python -m server.main    # → http://localhost:8000
```

### 前端

```bash
cd frontend
npm install
npm run dev              # → http://localhost:5173
```

### Docker

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
docker compose up -d
```

## 运行测试

```bash
pytest tests/ -v
```

提交 PR 前请确保所有测试通过。

## 提交规范

- 提交信息使用中文
- 描述变更**原因**而非变更内容（代码 diff 已经展示了变更内容）

## 代码风格

- 后端：Python 3.11+，遵循 PEP 8，文件头含 SPDX 版权声明
- 前端：Vue 3 Composition API + `<script setup lang="ts">`

## 问题反馈

- Bug 报告请包含复现步骤、预期行为和实际行为
- 功能建议请描述使用场景和预期效果
