# 命令

用当前已加载技能目录下的绝对脚本路径替换 `<脚本>`，不要把它误认为业务项目里的相对路径。

```text
python <脚本> init --project <目录> [--branch dev] [--remote origin]
python <脚本> inspect --project <目录>
python <脚本> start --project <目录>
python <脚本> finish --project <目录> --message "保存登录进度" --files docs/status.md src/login.py
python <脚本> finish --project <目录> --message "保存进度" --files-from <文件列表.json>
python <脚本> finish --project <目录>
```

`init`：只在指定的仓库根目录操作。空目录会初始化 Git；位于其他仓库内部的普通子目录会拒绝。配置已存在时保持原样，传入不同 branch/remote 会拒绝。已有文件不覆盖；规则块只追加一次。检查生成的交接文件是否被 Git 忽略。

`inspect`：只读，输出本地分支、HEAD、修改列表和配置。不会联网，不把缓存的远端引用当作实时远端状态。

`start`：要求配置分支、干净工作区、远端分支存在；fetch 后验证祖先关系，只执行快进。不自动安装依赖。

`finish`：先 fetch 检查远端没有未整合的新提交，再处理明确选中的文件。预先暂存的文件也必须包含在选择中。任何提交都需要 `docs/status.md` 有本次变化。只推送 HEAD 到配置的远端分支，不设置其他分支、不带 tags、不使用 force。没有新文件时可重试推送已存在的提交；由代理先核实其内容。

文件参数是相对于仓库根目录的精确文件名，不能是目录、绝对路径、父路径或 Git pathspec。删除／重命名文件需要包含 Git 状态中涉及的旧、新文件名。JSON 文件是 UTF-8 字符串数组，可放在仓库外的临时目录。

轻量敏感信息检查阻止 `.env`、常见私钥／凭据文件、部分已知令牌模式及超过 20 MiB 的新暂存文件；允许 `.env.example` 等模板，但仍检查内容。不能保证发现所有秘密。确需提交的特殊文件由用户审阅后使用普通 Git 处理，不提供自动绕过开关。

成功返回退出码 0；失败返回 1，JSON 包含 error、stage、hint 和当前 HEAD（可获取时）。推送失败可能已产生本地提交，提交失败可能留下暂存文件；不自动撤销或清理。finish 的 `remaining` 列出没有同步的本地修改；`complete=false` 时不得宣称整个工作区已同步。

`.handoff.json` 是受版本控制的无密钥配置：

```json
{"version": 1, "remote": "origin", "branch": "main"}
```

首次迁移分支时，由代理在两端核对分支后明确修改配置；不自动猜测“最新的那个分支”。
