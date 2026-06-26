以下是你本次创作依赖的全部数据。

## 输入数据

### 世界设定

**世界名称**：{world.name}
**世界描述**：{world.description}
**世界历史**：{world.world_history}
**世界规则**：{world.rules}

### 角色列表

每个角色包含以下字段。`核心执念` 和 `致命缺陷` 为可选字段——若未提供，
须在 plan.md 中自行推导并显式写出。

- **核心执念**：驱动角色所有行为的底层欲望（可选）
- **致命缺陷**：阻碍角色达成目标的性格弱点（可选）

{characters}

### 初始事件

- **事件内容**： {initial_event.content}
- **事件时间**： {initial_event.time}

### 时间线事件

#### 时间线事件数据格式

多个事件按发生顺序列出。每个事件含 `type` 和 `content`：

- `scene_setting` — 场景设定事件（每轮开场的场景锚点）
- `action` — 角色行动。附带 `character`（角色名）、`motive`（行动动机）、
  `inner_thoughts`（内心想法）、`source`（`perception` 感知驱动 /
  `interaction` 互动驱动）
- `conflict` — 结构性冲突
- `relationship` — 关系变化
- `user_decision` — 用户选择的分支
- `user_intervene` — 用户在轮间干预的剧情事件

#### 时间线事件数据

{timeline events}

---

根据以上数据，创作一部"现象级"中文群像小说。
从制定规划开始，逐步完成所有章节的写作、审稿、修订，直到你认为可以组装成书。
