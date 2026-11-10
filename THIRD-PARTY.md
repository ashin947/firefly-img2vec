# 第三方组件与许可

本项目整体以 **GPL-2.0-or-later** 发布。以下组件随发行版一起分发。

## 内置可执行文件（随包分发）

| 组件 | 版本 | 许可 | 位置 | 源码 |
|---|---|---|---|---|
| potrace | 1.16 | **GPL-2.0-or-later** | `bin/potrace/potrace.exe` | https://potrace.sourceforge.net/ |

potrace 的许可证全文见 `bin/potrace/COPYING`，作者与致谢见 `bin/potrace/AUTHORS`。
GPL-2.0 第 3 条要求随二进制提供对应源码，或提供有效期三年的书面源码获取承诺。
本项目的源码仓库同时包含打包脚本与全部自研代码；potrace 自身的源码可从
https://potrace.sourceforge.net/#downloading 获取，本项目未对其做任何修改。

## Python 依赖

| 组件 | 许可 | 用途 |
|---|---|---|
| vtracer | MIT | 彩色位图描迹（Rust 实现） |
| reportlab | BSD-3-Clause | 从几何 IR 直接发射 PDF |
| Pillow | MIT-CMU | 读写位图、二值化输入 |
| numpy | BSD-3-Clause | 数值计算 |
| pypdfium2（含 PDFium） | Apache-2.0 / BSD-3-Clause | 质量自检时把 PDF 栅格化回来对比 |

## 调用方式说明

`potrace` 通过**独立子进程**调用（`subprocess`），只通过命令行参数与 SVG 文件交换数据，
本项目不链接、不修改其代码。`vtracer` 与 `reportlab` 作为 Python 库导入使用。

## 不分发的情况

仅自己或团队内部使用、不对外提供副本时，GPL 不产生任何义务。
一旦把本程序上传公开仓库、或在网页上提供下载，就构成分发，需保持 GPL 合规
（保留 `LICENSE`、`bin/potrace/COPYING` 与源码获取方式）。
