# 当前架构

## 组成

- `skills/brainstorm-lite/`：需求对齐技能及上游来源／MIT 许可。
- `skills/project-handoff/`：交接指令、命令参考和 `scripts/handoff.py`。
- `install.py`：全局或项目安装；遇到不同内容需明确更新，更新前备份。
- `tests/test_handoff.py`：本地 bare remote 与两个工作区的集成测试。
- `.github/workflows/tests.yml`：在 Windows、macOS、Linux 上运行 Python 3.10 测试。

## 交接路径

AI 维护项目文档 → finish 检查分支／远端 → 暂存明确选择的文件 → 检查交接更新与常见秘密 → commit → 非强制 push → ls-remote 核实 → 报告未同步修改。

另一端 start 检查干净工作区与约定分支 → fetch → 仅快进 → AI 重读规则、需求、架构、状态 → 核对代码后继续。

## 实现选择

Python 3.10+ 标准库与 Git，无 pip 依赖。文件为 UTF-8，Git 调用使用参数数组，无 shell 拼接。脚本以 JSON 返回结果。Git 失败不自动 reset、clean、stash 或撤销提交。

脚本保证可检查的 Git 行为；进度文档的语义准确性、测试选择和未推送历史的审阅由 AI 负责。密钥检测只是基础检查。

## 维护

运行 `python -m unittest discover -s tests -v`。身份由 Git 配置，认证由当前机器的 Git 凭据管理处理，不保存在技能或 `.handoff.json`。新会话读取本仓库的四份交接文档即可继续维护。
