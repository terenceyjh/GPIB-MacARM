# 来源、版权和许可

本包以 GPL-2.0-or-later 提供。完整许可证见 LICENSE。

- KAME：Kentaro Kitagawa 及各文件原版权人，源码 https://github.com/northriv/KAME ，固定提交 f451025dc4215c5d85f39b71303f9008ccee66bc。
- 提取路径：modules/charinterface/usermode-linux-gpib。保留该目录中的驱动、兼容层和上游 C++ 包装参考实现，不包含 KAME GUI、测量模块或 AI/MCP 服务。
- Linux-GPIB：Frank Mori Hess、C. Schroeter 及其贡献者。KAME 携带的基础版本为 4.3.6 / git 9813ff8f。原始版权头、AUTHORS、COPYING 保留在 vendor/kame/linux-gpib 中。
- native/driver.cpp 的生命周期和寻址流程基于 KAME 的 NiGpibDriver；独立 C ABI、Python 包装、构建文件、文档和测试为本次提取工作新增，同样采用 GPL-2.0-or-later。
- vendor/kame/osx_compat.h、vendor/kame/linux-gpib/ni_usb_gpib.c 有本地修复。补丁见 vendor/local-fixes.patch，来源及文件哈希见 UPSTREAM.json。
- libusb 是外部链接依赖，本源代码包不包含它的二进制或头文件。请从 Homebrew/MacPorts/系统包安装，libusb 使用 LGPL-2.1-or-later；参见 https://libusb.info/ 。

UPSTREAM.json 中原始哈希对应本次检出的实际文件字节（可能包含 git 的平台换行转换）；这是固定快照记录，不要求不同平台 git checkout 的换行结果相同。普通安装使用已随包提供的 vendor 源码，不调用 git 或下载上游文件。
