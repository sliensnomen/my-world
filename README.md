# my-world / WGP · 世界观治理协议与参考实现

**WGP（World Governance Protocol）**：给多人共创虚构世界的一套机器可审计的治理规则。
协议是产品，代码是参考实现。规则才是护城河，AI 只是 lint 器的一种。

## 有什么

- `PROTOCOL.md` —— 协议本体 **v1.0（已冻结）**：条目格式、canon 状态机、矛盾合法化、政治经济学供应链（depends_on 七层链 + kind 分族）、22 条确定性审计规则（CA 编号）
- `canonlint.py` —— 参考实现：建 id 索引与关系图，跑全部确定性规则，输出规则编号 + 退出码 + JSON + CA504 影响报告
- `tests/` —— 五套测试世界：world-bad（全规则触发夹具）、world-clean（全绿）、三个真实世界 dogfood（魔戒 / 冰与火 / 沙丘，共 52 条真实设定条目）
- `docs/协作流程.md` —— 多人协作的 git 工作流映射（PR=提案、CODEOWNERS=已定档保护、CI=审计门禁）
- `项目文书.md` —— 项目定位、竞争分析、路线图

## 用法

```bash
pip install pyyaml
python3 canonlint.py <世界仓库目录>            # 审计
python3 canonlint.py . --strict               # CI 门禁模式：警告也拦截
python3 canonlint.py . --json                 # 机器可读输出
python3 canonlint.py . --impact spice-melange # CA504：改动波及谁
```

## 三个设计信条

1. **矛盾合法化**——`conflicts_with` 标注即解决，两条叙事都保留；
2. **物质往上供，规范往下压**——粮食养军队，合法性管军队，两条河方向相反；
3. **AI 永不进退出码**——机器判定必须可复现，AI 只递建议条子。

## 授权

代码 [MIT](LICENSE)；协议文本 [CC BY 4.0](LICENSE-PROTOCOL.md)（实现不受限，引用需署名）。
