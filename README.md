# Project Handoff · 两台电脑，接着开发

在家收工推送，到公司拉取继续。代码、规则、架构和进度一起保存在 Git 仓库里。

**两个轻量技能：**

- **`brainstorm-lite`**：基于 Superpowers 改编，只对齐需求、输出文档；不附带计划、TDD、子代理等后续流程。
- **`project-handoff`**：初始化项目文档、开工恢复、收工提交并推送。

支持 Codex 的技能发现方式；脚本适用于 Windows、macOS、Linux。需要 **Git、Python 3.10+**，无额外 Python 依赖。Git 提交身份、GitHub 认证和项目运行环境需在两台电脑分别配置。

## 1. 安装：两台电脑各做一次

```bash
git clone https://github.com/FJS3484790561/project-handoff.git
cd project-handoff
python install.py
```

默认安装到 `$CODEX_HOME/skills`，未设置时为 `~/.codex/skills`。在 Codex 新开会话后使用。部分电脑的 Python 命令是 `python3` 或 `py -3`，替换命令中的 `python` 即可。

**如果装过完整 Superpowers，请在客户端停用该插件，避免它继续自动触发其他流程。** 安装器不会修改其他插件或覆盖同名技能。

## 2. 给项目启用交接

在你的业务项目里对 AI 说：

> 使用 $project-handoff 为这个项目启用交接。沿用已有需求和代码，补齐项目文档。日常开发保持轻量。

新项目需要梳理需求时，再说：

> 使用 $brainstorm-lite 帮我对齐需求，输出需求文档。UI 按我的专属规则处理。

AI 会维护这些文件：

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 固定规则与阅读入口，保留已有内容 |
| `docs/product.md` | 确认需求与验收条件 |
| `docs/architecture.md` | 当前架构、运行方法与重要决定 |
| `docs/status.md` | 当前进度、验证结果、下一步 |
| `.handoff.json` | 共同使用的远端和开发分支，无密钥 |

已有文档可以直接引用，不必重写。初始化不会创建 GitHub 仓库；新项目首次使用时，告诉 AI 仓库地址，或要求它创建仓库并明确公开／私有。

## 3. 每天只说两句话

**在家收工：**

> 今天先到这里，更新交接文档，把本次代码和文档提交并推送。

**到公司开工：**

> 拉取这个项目，读取规则、架构和进度，接着上次继续。

公司第一次使用该项目时，附上**业务项目的仓库地址**和保存目录即可。

AI 会在收工时报告已核实的分支、提交和剩余事项；开工同步后重新读取文档，不需要昨天的聊天记录。功能做到一半也能保存，未完成和未验证的部分会明确记录。

## 4. 需要知道的边界

- 技能按你的请求运行，**不是后台自动同步**；突然关机无法上传未保存的工作。
- 一次在一台电脑开发。出现本地修改、分支分叉或远端新提交时，先保留工作再处理差异，不强制覆盖。
- Git 只同步已提交内容。密钥、`.env`、本地数据库、运行中的服务需要单独配置；环境变量模板和数据库迁移可以提交。
- Git 脚本核实提交和推送；AI 负责填写有用的需求、架构和进度。脚本不会替你运行项目测试，也不能保证发现所有秘密。
- 普通开发不额外强制规划、审查、TDD 或子代理。测试按项目和改动的实际需要执行。

## 可选：让技能也跟着业务项目走

在本技能包目录执行（把路径替换为你的业务项目）：

```bash
python install.py --project /path/to/your-project
```

将生成的 `.agents/skills/` 随业务项目提交。另一台电脑克隆后即可发现技能。全局安装和项目安装选一种，避免同名技能重复出现。

更新已安装版本：在本技能包目录先 `git pull --ff-only`，再运行 `python install.py --update`；项目安装时同时带上原来的 `--project` 参数。旧版本备份在安装目录的 `.skill-backups/`，不应提交到业务仓库。

高级参数见 [脚本命令说明](skills/project-handoff/references/commands.md)。开发者可运行 `python -m unittest discover -s tests -v`，测试用本地 bare 仓库模拟两台电脑，不访问 GitHub。

## 来源与许可

MIT。头脑风暴部分改编自 [obra/superpowers](https://github.com/obra/superpowers)，是独立轻量版本，保留上游许可；具体区别见 [来源说明](skills/brainstorm-lite/references/upstream.md)。
