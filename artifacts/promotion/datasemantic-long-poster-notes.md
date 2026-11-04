# DataSemantic × MyCoWork 宣传长图

- 高清成图：`datasemantic-mycowork-long.png`，2400 × 6495 像素。
- 预览：`datasemantic-mycowork-long-preview.png`。
- 自包含矢量排版：`datasemantic-mycowork-long.svg`，1600 × 4330 设计尺寸，截图与插画均内嵌。
- 排版生成源：`render-long-poster.cjs`。依赖 Node.js 与 sharp，可用 `POSTER_SHARP_PATH` 指定 sharp 模块位置。
- 插画使用内置 image_gen 生成，提示词见 `datasemantic-long-poster-art-prompt.txt`；原文件为 `datasemantic-cow-editorial.png`。

## 版面结构

1. 产品定位与小幅卡通插画。
2. 三组痛点与优势：结构建模、口径沉淀、查询验证。
3. 技术架构：宿主业务工具、语义模型、SQL 规划、可选只读执行、业务数据库。
4. 三组实际 MDL Studio 界面及说明：模型工作空间、模型关联画布、语义视图测试。

## 截图来源

直接嵌入仓库原始截图，保留完整截图视口，仅等比缩放，不重新生成界面内容：

- `../mdl-studio/workspace-list.png`
- `../mdl-studio/relation-canvas.jpg`
- `../mdl-studio/semantic-view-test.jpg`

界面包含演示 / 验证模型。视图测试验证 SQL 规划，不代表业务查询已经执行。图中 MyCoWork 表示经宿主业务工具接入的配套架构，不宣称已实现所有场景的直接集成。

能力文案以仓库 README 的 Studio、模型发布、规划 API 与只读执行说明为依据。
