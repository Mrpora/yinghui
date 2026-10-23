# 萦回 (Yinghui) — AI 互动叙事引擎

[![AGPL v3](https://img.shields.io/badge/license-AGPL_v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-20+-green.svg)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](docker-compose.yml)
[![Tests](https://img.shields.io/badge/tests-120_passed-brightgreen.svg)](tests/)
[![Stars](https://img.shields.io/github/stars/mrpora/yinghui?style=social)](https://github.com/mrpora/yinghui)

![世界演化 Demo](docs/gifs/demoC-2.gif)

> 创建架空世界，然后放手——角色自主互动、冲突、和解，世界在你眼前自行演化。
> 演化结束后一键生成章节体小说，进入任意角色视角与 ta 对话。ta 记得你。

[🚀 快速开始](#快速开始)　[🎬 观看完整 Demo](#demo)　[⭐ Star 本项目](https://github.com/mrpora/yinghui)

> **这是一个 Demo 项目**，它不追求功能完整或生产级质量，仅供学习、
> 研究和概念验证。

萦回是一个 AI 原生产品：剥离 AI，它归零。它不是一个把 AI 塞进现有流程的写作工具，
而是以 AI 为核心创造前所未有的体验——让虚构世界自己运转、生长、讲故事。

## 目录

- [Demo](#demo)
- [功能](#功能)
- [快速开始](#快速开始)
- [架构](#架构)
- [项目结构](#项目结构)
- [配置](#配置)
- [API 概览](#api-概览)
- [技术栈](#技术栈)
- [开发指南](#开发指南)
- [贡献指南](#贡献指南)
- [License](#license)
- [致谢](#致谢)

## Demo

> 🎬 以下为完整 Demo 演示视频，点击缩略图跳转 B站观看。README 顶部嵌有 GIF 预览。

Demo 视频完整展示了 C 线（世界演化）和 A 线（角色对话）的核心流程。

### C 线：世界自主演化

| 序号 | 内容 | 演示 |
|------|------|------|
| C-1 | 创建世界——设定背景、规则、角色、初始事件 | [![创建世界](docs/images/thumbnails/cover-C1-world-create-v1.png)](https://www.bilibili.com/video/BV1q6Kb6FEAq?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| C-2 | 角色自主互动——导演 Agent 调度角色，角色自主决策、对话 | [![角色自主互动](docs/images/thumbnails/cover-C2-interaction-v1.png)](https://www.bilibili.com/video/BV1ZBKb6hEao?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| C-3 | 角色冲突——目标对立产生冲突，自主推进升级或化解 | [![角色冲突](docs/images/thumbnails/cover-C3-conflict-v1.png)](https://www.bilibili.com/video/BV1qBKb6hE67?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| C-4 | 生成小说——演化记录一键转为章节体小说 | [![生成小说](docs/images/thumbnails/cover-C4-novel-v1.png)](https://www.bilibili.com/video/BV1XKKb6pE93?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| C-5 | 角色导入对话——小说角色从纸面走出，进入对话界面 | [![角色导入对话](docs/images/thumbnails/cover-C5-import-v1.png)](https://www.bilibili.com/video/BV1MEKb6LEcQ?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |

### A 线：沉浸式角色对话

| 序号 | 内容 | 演示 |
|------|------|------|
| A-1 | 角色主动开场——无需用户先说话，角色主动发起问候 | [![角色主动开场](docs/images/thumbnails/cover-A1-greeting-v1.png)](https://www.bilibili.com/video/BV1XKKb6pEXa?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| A-2 | 记忆写入——Agent 提取用户信息存入永久记忆，后续对话自然唤起 | [![记忆写入](docs/images/thumbnails/cover-A2-memory-v1.png)](https://www.bilibili.com/video/BV19PKb69E94?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| A-3 | 时间感知与情绪覆写——角色感知时段，据此调整问候和情绪 | [![时间感知与情绪覆写](docs/images/thumbnails/cover-A3-time-v1.png)](https://www.bilibili.com/video/BV1QuKb6nEnm?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| A-4 | 跨角色记忆共享——不同角色共享对用户的认知，主动提起过往 | [![跨角色记忆共享](docs/images/thumbnails/cover-A4-share-v1.png)](https://www.bilibili.com/video/BV1QuKb6nEpt?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| A-5 | 安全风控——检测到违规内容时拒绝回复并记录日志 | [![安全风控](docs/images/thumbnails/cover-A5-safety-v1.png)](https://www.bilibili.com/video/BV1GTKb6XE2J?vd_source=692e2948ccafe3cc25d3ab2a13e09089) |
| A-6 | 报警日志——触发安全阈值后自动通知管理员（涉及隐私，未公开） | ![报警日志](docs/images/thumbnails/cover-A6-alert-v1.png) |

## 功能

| 功能 | 说明 | Demo |
|------|------|------|
| **世界创建** | 设定世界规则、角色身份/性格/目标/关系（3-10 个角色），AI 自动补全未尽细节 | C-1 |
| **世界自主演化** | 导演 Agent 分回合调度角色 Agent，每轮产出新事件和关系变化 | C-2 |
| **角色互动** | 角色基于自身设定自主决策、对话、行动，无需人工编写剧本 | C-2 |
| **角色冲突** | 角色间因目标或立场对立产生冲突，自主推进冲突升级或化解 | C-3 |
| **剧情分支选择** | 导演在关键节点暂停演化，提供多条分支供用户选择 | C-2, C-3 |
| **用户干预** | 演化过程中随时插入自定义事件，改变剧情走向 | C-2, C-3 |
| **演化可视化** | 时间线展示每轮完整记录——事件、对话、关系变化 | C-2, C-3 |
| **小说一键生成** | 演化记录自动转为章节体小说。写作 Agent 逐章创作，审查 Agent 润色 | C-4 |
| **角色导入对话** | 小说角色从纸面走出，进入对话界面——C 线到 A 线的完整闭环 | C-5 |
| **沉浸式角色对话** | 选择角色进入其视角对话——角色恪守自身认知边界，只知亲身经历 | A-1, A-2 |
| **多层记忆系统** | 即时记忆 + 永久记忆（BM25 + 向量混合检索），跨角色共享对用户的认知 | A-2, A-4 |
| **主动关怀** | 角色感知时间流逝，根据时段和上次对话间隔主动发起话题 | A-3 |
| **安全风控** | 内容安全检测 + 报警日志，保障对话安全可控 | A-5, A-6 |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- [可选] Docker & Docker Compose
- [可选] yinghui-dsh-plug（bridge + DSH）——不启动时纯领域功能可用，触发 LLM 的接口返回 503

### 源码安装

**1. 克隆仓库**

```bash
git clone https://github.com/mrpora/yinghui.git
cd yinghui
```

**2. 后端**

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env（无必填项；BRIDGE_URL 默认 http://127.0.0.1:8100）
```

如需向量记忆检索（推荐）：

```bash
huggingface-cli download BAAI/bge-large-zh-v1.5 --local-dir models/bge-large-zh-v1.5
```

不下载嵌入模型也可运行——自动回退到 BM25 关键词检索。

```bash
python -m server.main    # → http://localhost:8000
```

**3. 前端**

```bash
cd frontend
npm install
npm run dev              # → http://localhost:5173
```

**4. agent 编排（可选，完整体验必需）**

世界演化、角色对话、小说生成等 LLM 编排由外部 yinghui-dsh-plug 承担：

```bash
# 另见 yinghui-dsh-plug 仓库 README——安装 DSH preset、启动 bridge（:8100）
```

### Docker 启动

```bash
cp .env.example .env
# 编辑 .env（无必填项；agent 编排需另行启动 yinghui-dsh-plug bridge）
docker compose up -d
# 后端 → http://localhost:8000
# 前端 → http://localhost:80
```

## 架构

yinghui 是**纯领域服务**（进程内无任何 LLM 调用）；全部 agent 编排外移至
yinghui-dsh-plug 桥接进程，由 DeepSeek Harness（DSH）驱动。

```
Vue 前端（零改动；/api/* 契约 + 3 条 SSE 词汇表不变）
   │
   ▼
yinghui FastAPI :8000 —— 纯领域服务（无任何 LLM 调用）
   ├─ 前端路由原样保留；LLM 类路由改调 BridgeDispatcher
   ├─ 新增 /api/agent/*：领域操作接口（MCP 工具的后端实现，仅回环使用）
   └─ BridgeDispatcher ──HTTP 127.0.0.1:8100──► plug bridge
                                                    │ RPC /api/session/* + WS /api/remote.mux
                                                    ▼
                                          DSH desktop（agent 编排）
                                                    │ stdio MCP
                                                    ▼
                                          plug mcp_server ──REST──► yinghui /api/agent/*
```

调用方向约定：**前端→yinghui 不变；yinghui→bridge 触发；DSH→MCP→yinghui 回写**。
数据唯一真相源始终是 yinghui 的 SQLite；DSH 会话只是上下文载体，可随时重建。

### 组件职责

| 组件 | 职责 |
|------|------|
| routers（前端 API） | 世界/演化/小说/对话/记忆的 REST + SSE 契约保持不变；触发 LLM 的 7 条路由改向 bridge 分发（触发失败 503，中文 detail） |
| /api/agent/*（内部接口） | 领域操作面：时间线/分支/轮次收束/记忆检索/章节硬门等回写与读取，供 MCP 工具与 bridge flows 调用（仅回环，不对外暴露） |
| services | 记忆（BM25+向量混合检索、衰减）、关怀、安全、会话/时间线/关系存储、precheck 硬门——纯领域逻辑 |
| BridgeDispatcher | yinghui→bridge 的唯一出站通道（httpx.AsyncClient）：fire-and-forget 触发（10s）与 oneshot 同步代理（300s/600s） |
| storage / sse | SQLite + sqlite-vec；SSEManager 发布-订阅（演化/对话/小说三通道词汇冻结） |

### 运行前置

触发 LLM 的功能（演化推演、角色对话、小说生成、世界补全、角色提取）需要先启动：

1. **DSH desktop**（DeepSeek Harness）
2. **yinghui-dsh-plug bridge**（默认 127.0.0.1:8100，`BRIDGE_URL` 可覆盖）

bridge 缺席时：纯领域功能（世界管理、时间线、记忆 CRUD 等）不受影响；
触发类接口返回 503 `桥接服务未启动：请先运行 yinghui-dsh-plug bridge（默认 127.0.0.1:8100）`。

### 记忆系统

每轮对话持久化到 SQLite。用户透露的个人信息由对话编排（bridge 侧）提取，
经 /api/agent 写入永久记忆（BM25 关键词索引 + 向量嵌入混合检索）。
记忆回响基于时间衰减算法，让角色在合适时机主动提起用户过往经历。

## 项目结构

```
yinghui/
├── server/
│   ├── routers/              # REST API（7 组前端路由 + /api/agent/* 领域操作面）
│   ├── services/             # 记忆/嵌入/关怀/安全/会话管理 + 桥接分发器
│   ├── storage/              # SQLite + sqlite-vec 向量表
│   ├── sse/                  # Server-Sent Events 发布-订阅
│   ├── models/               # Pydantic 模型定义
│   └── utils/                # 工具函数（字体混淆等）
├── frontend/
│   └── src/
│       ├── pages/            # 12 个页面组件
│       ├── components/       # UI 组件 + 对话/演化专用组件
│       ├── stores/           # Pinia 状态管理（5 个 store）
│       ├── api/              # 后端 API 调用层 + SSE 客户端
│       ├── types/            # TypeScript 类型定义
│       └── router/           # Vue Router 路由配置
├── scripts/                  # Token 成本模型 + 字体生成
├── data/                     # SQLite 数据库 + 工作目录
├── models/                   # 本地嵌入模型
├── docs/                     # Demo 视频与素材
├── tests/                    # 后端测试（pytest）
└── .env.example              # 环境变量模板
```

## 配置

所有配置项通过 `.env` 文件设置，完整列表见 `.env.example`。

<details>
<summary><b>桥接</b></summary>

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `BRIDGE_URL` | yinghui-dsh-plug bridge 地址（agent 编排所在的外部进程） | `http://127.0.0.1:8100` |

</details>

<details>
<summary><b>演化</b></summary>

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `EVOLUTION_DEFAULT_ROUNDS` | 默认演化轮数 | `20` |
| `EVOLUTION_MAX_ROUNDS` | 演化轮数上限（默认轮数按角色数正比缩放后封顶） | `100` |

</details>

<details>
<summary><b>记忆系统</b></summary>

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `MEMORY_LIMIT` | 永久记忆上限 | `10` |
| `INSTANT_MEMORY_SIZE` | 即时记忆条数 | `200` |
| `CARE_COOLDOWN_HOURS` | 主动关怀冷却时间 | `24` |
| `DECAY_HALF_LIFE_DAYS` | 记忆衰减半衰期（天） | `15.0` |
| `EMBEDDING_MODEL` | 嵌入模型路径 | `models/bge-large-zh-v1.5` |

</details>

<details>
<summary><b>小说（precheck 硬门）</b></summary>

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `NOVEL_CHAPTER_MIN_CHARS` | 每章最少字数 | `3000` |
| `NOVEL_CHAPTER_MAX_CHARS` | 每章最多字数 | `5000` |
| `NOVEL_WORK_DIR_BASE` | 任务工作目录 | `data/work` |

</details>

## API 概览

| 路由 | 说明 |
|------|------|
| `/api/auth` | 用户登录（昵称即身份，无需注册） |
| `/api/worlds` | 世界 CRUD + AI 补全配置 |
| `/api/evolutions` | 演化会话管理 + 轮次推进 + 分支选择 + 用户干预 + 时间线 |
| `/api/novels` | 小说异步生成 + 任务轮询 + SSE 进展推送 + 角色导入 |
| `/api/chats` | 角色列表 + SSE 流式对话 + 历史消息 |
| `/api/memories` | 记忆查询/删除/过期管理/清空 |
| `/api/settings` | 主动关怀等级设置 |
| `/api/agent` | 领域操作接口（**内部接口**——供 yinghui-dsh-plug 的 MCP 工具与 bridge flows 回环调用，不对外暴露） |

对话和小说生成接口提供 **SSE 流式输出**，关键状态节点实时推送到客户端。

启动后端后访问 `http://localhost:8000/docs` 查看完整的 Swagger API 文档。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ · FastAPI · SQLite + sqlite-vec · asyncio |
| AI | OpenAI 兼容 API · sentence-transformers · jieba |
| 前端 | Vue 3 + TypeScript · Vite · Tailwind CSS · Pinia |
| 测试 | pytest · pytest-asyncio |
| 部署 | Docker · Docker Compose |
| 字体 | Noto Serif SC · ZCOOL XiaoWei |

## 开发指南

### 运行测试

```bash
# 全部测试（120 个）
pytest tests/ -v

# 按模块运行
pytest tests/test_api.py -v            # API 端点
pytest tests/test_session_manager.py -v # 会话管理器
pytest tests/test_config.py -v         # 配置解析
```

### 代码风格

- Python：遵循 PEP 8，文件头含 SPDX 版权声明
- Vue 3：Composition API + `<script setup lang="ts">`
- 提交信息：中文，描述变更原因而非内容

### 环境变量

所有配置项通过 `.env` 文件管理。开发前：

```bash
cp .env.example .env
# 无必填项；如需完整体验，BRIDGE_URL 保持默认并启动 yinghui-dsh-plug bridge
```

## 贡献指南

本项目采用 AGPL v3 + 商业授权的双许可证模式。
提交 Pull Request 前请先阅读 [CLA.md](CLA.md)——贡献者许可协议。
通过提交 PR，你确认接受 CLA 条款。

在提交 PR 前请确保：

- 代码通过现有测试（`pytest tests/`）
- 新增功能包含测试
- 遵循项目的代码风格

欢迎提交 Issue 和 Pull Request。

## License

本项目以 **GNU Affero General Public License v3.0（AGPL v3）** 开源。

### 分场景指引

| 你的使用场景 | 适用许可证 | 费用 |
|-------------|-----------|------|
| 个人学习、研究、非商业项目 | AGPL v3 | 免费 |
| 商业使用，愿意将修改后的源码全部公开 | AGPL v3 | 免费 |
| 商业使用，不想公开源码 | 商业许可证 | 付费 |
| 将本软件集成到闭源产品中分发 | 商业许可证 | 付费 |

AGPL v3 不禁止商业使用——它只要求通过网络提供服务时公开源码。
如果你愿意遵守，商用也是免费的。只有当你希望闭源使用时才需购买商业许可证。

- 商业许可咨询：mrpora@163.com
- 许可证详情见 [LICENSE](LICENSE) 文件

## 附录

### AI 工具 vs AI 产品

传统的"AI 写作工具"本质是通用对话界面加上补全引擎，写作只是无数用例之一。
真正的 AI 叙事产品应该做到：拿走 AI，这个需求根本不存在。

![AI 工具 vs AI 产品](docs/images/ai-tool-vs-ai-product.png)

### AI 认知金字塔

这是在实际使用 AI 的过程中总结出的一个分层框架——从底层的"消费者"到顶层的"引领者"，
左侧为能力成长路径，右侧为角色与影响力的升级。一家之言，抛砖引玉。

萦回定位于第 3 层：从"用 AI"转向"造 AI 产品"——不是调用已有模型做表层应用，
而是自研 Agent 引擎，把 AI 作为产品的核心驱动力。

![AI 认知金字塔](docs/images/ai-cognition-pyramid.png)

### Token 成本实测

基于 Demo 运行日志的实测 token 消耗数据——演化、对话、小说生成的单次成本可精确度量。

![Token 成本实测](docs/images/token-cost-measured.png)

## 致谢

本项目受益于以下开源项目：

- [sqlite-vec](https://github.com/asg017/sqlite-vec) — SQLite 向量检索扩展
- [sentence-transformers](https://github.com/UKPLab/sentence-transformers) — 嵌入模型框架
- [BAAI/bge-large-zh-v1.5](https://huggingface.co/BAAI/bge-large-zh-v1.5) — 中文嵌入模型
- [jieba](https://github.com/fxsjy/jieba) — 中文分词
- [FastAPI](https://github.com/fastapi/fastapi) — Web 框架
- [Vue.js](https://github.com/vuejs/core) — 前端框架

---

**作者：mrpora** · [mrpora@163.com](mailto:mrpora@163.com)
