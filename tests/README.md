# 测试目录结构

本目录包含项目的所有测试文件和相关文档。

## 目录结构

- **py/** - Python 测试脚本和工具脚本
  - 单元测试文件 (test_*.py)
  - 调试和清理工具脚本
  
- **sh/** - Shell 测试脚本
  - 集成测试脚本 (test_*.sh)
  - 自动化测试运行脚本

- **md/** - 测试和修复相关文档
  - 功能修复文档 (*_FIX.md)
  - 快速入门指南 (*_QUICKSTART.md)
  - 实现总结 (*_SUMMARY.md)
  - 分析报告 (*_ANALYSIS.md)
  - 使用指南 (*_GUIDE.md)

- **根目录** - 属性测试和核心测试
  - test_*.py - 基于 Hypothesis 的属性测试

## 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_*.py

# 运行 shell 测试
./tests/sh/test_run_all_tests.sh
```
