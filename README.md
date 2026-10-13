# LookinServerInject

将 [LookinServer](https://github.com/QMUI/LookinServer) 编译为通用 iOS 动态库，加载到目标 App 进程后，使用 Mac 上的 [Lookin](https://lookin.work/) 查看 UIKit 视图层级和属性。

本项目不绑定具体 App。目标 App 由注入工具选择，或在生成安装包时通过 `--bundle-id` 指定，无需修改源码。iPhone 和 iPad 使用同一套入口与提示逻辑。

## 为什么新增 rootless 构建入口

原有流程依赖 MonkeyDev 编译，再将 dylib 交给 TrollFools 等工具注入。现在增加 `scripts/build_rootless.py`，可以直接使用 Xcode 工具链生成 dylib，并按需生成适用于 ElleKit rootless 环境的 `.deb` 安装包。

rootless 包采用 `/var/jb` 安装前缀和 `iphoneos-arm64` 包架构标识，适配这类越狱环境的目录布局。原有 `LookinInject/Package` 模板使用 rootful 路径，新脚本独立生成包结构，不沿用该模板。关于目录与包架构约定，见 [Theos rootless 文档](https://theos.dev/docs/rootless)。

新增入口让已经安装的 App 可以通过越狱环境的 tweak loader 在启动时加载 LookinServer。此路径不需要修改目标 App 的 IPA，也不需要重新签名、重新安装目标 App；Mac 端构建无需 MonkeyDev、Theos 或 dpkg。

**当前新增的是 rootless 支持，尚未实现 RootHide 专用打包或路径适配。** RootHide 使用自己的 jbroot 与路径规则，不能仅凭“都是无根环境”判断安装包兼容，详见 [RootHide 官方说明](https://github.com/roothide/Developer/blob/main/roothide.md)。

## 选择使用方式

| 环境 / 需求 | 使用方式 | 产物 |
| --- | --- | --- |
| 具备 `/var/jb` 布局、ElleKit 和可用 tweak 注入的 rootless 越狱环境 | 生成 `.deb`，安装后重新启动目标 App | dylib + Filter plist + deb |
| 使用 TrollFools 或其他可用的 dylib 注入工具 | 仅构建 dylib，由工具选择目标 App | dylib |
| 已配置 MonkeyDev | 保留原有 Xcode 工程编译流程 | dylib |

设备与系统是否支持所选越狱或注入工具，需要按对应工具的支持范围确认。构建脚本的最低系统参数不代表该系统一定能越狱。

## 快速开始

Mac 需要 Python 3 和完整 Xcode，且 `xcrun` 能找到 iPhoneOS SDK。命令均在仓库根目录执行。

```bash
git clone https://github.com/swlfigo/LookinServerInject.git
cd LookinServerInject

# 仅构建通用 dylib，不指定 App。
python3 scripts/build_rootless.py

# 为 rootless / ElleKit 环境打包；替换为目标 App 的真实 Bundle ID。
python3 scripts/build_rootless.py --bundle-id com.example.App
```

默认输出到 `build/rootless/`，使用 `arm64`，最低系统版本为 iOS 15.0。传入 Bundle ID 后额外生成 `LookinInject.plist` 和 `LookinInject.deb`。

将 `.deb` 传到设备并安装，完全退出再打开目标 App，随后通过 USB 在 Mac 的 Lookin 中选择设备和 App。完整的环境准备、Bundle ID 查询、安装与卸载命令见 [注入指南](docs/injection.md)。

同时为多个 App 启用时，重复传入参数：

```bash
python3 scripts/build_rootless.py \
  --bundle-id com.example.FirstApp \
  --bundle-id com.example.SecondApp
```

Bundle ID 只用于生成安装包的 Filter；dylib 内没有目标 App 列表。不传 Bundle ID 时只构建通用 dylib，不生成覆盖所有 App 的安装包，不支持通配符。

## 注入成功提示

默认在 Lookin 服务就绪、App 进入前台且有可用窗口时，在顶部显示：

> Lookin 已注入<br>
> 可在电脑上连接查看 UI

提示约 3 秒后自动消失，每个 App 进程只显示一次，不拦截触摸、不弹出模态窗口。支持 iPhone、iPad、多窗口 App，以及 iPad 上以兼容模式运行的 iPhone App，布局使用当前窗口的安全区域。

提示表示进程内的 Lookin 服务已经就绪；USB 配对与 Mac 客户端连接是否成功，需要在 Lookin 中确认。入口也会处理向已经处于前台的 App 加载 dylib 的情况。

关闭提示并保留 Lookin 服务：

```bash
python3 scripts/build_rootless.py --bundle-id com.example.App --no-notice
```

## 构建参数

| 参数 | 说明 |
| --- | --- |
| `--bundle-id com.example.App` | 目标 App 的精确 Bundle ID；可重复。不传时只生成 dylib |
| `--no-notice` | 关闭注入成功提示 |
| `--arch arm64 --arch arm64e` | 按需构建双架构；默认 `arm64` 适用于通常的第三方 App 进程 |
| `--min-ios 13.6` | 指定最低系统版本；仅构建 dylib 时支持 13.0 及以上，rootless 包要求 15.0 及以上 |
| `--package-version 0.2.1` | 设置 deb 版本；默认 `0.2.0` |
| `--output-dir build/custom` | 指定输出目录 |

输出目录中的 `LookinInject.dylib`、`LookinInject.plist`、`LookinInject.deb` 和 `build-info.json` 由脚本管理。不传 Bundle ID 重建时，会移除该目录之前生成的 Filter 和 deb；需要保留多套配置时请使用不同输出目录。

## 原有 MonkeyDev 流程

1. 安装 [MonkeyDev](https://github.com/AloneMonkey/MonkeyDev)，打开 `LookinInject.xcodeproj`。
2. 编译 `LookinInject` target，取得生成的 dylib。
3. 将 dylib 导入设备上可用的注入工具，选择目标 App，再重新打开 App。
4. 在 Mac 的 Lookin 中连接并查看层级。

此流程也默认显示成功提示。在 Xcode 的预处理器宏中增加 `LOOKIN_INJECT_SHOW_NOTICE=0` 可以关闭。原有包模板不用于新脚本的 rootless 打包。

## 文档

- [注入指南：环境、操作步骤、更新、卸载和排查](docs/injection.md)
- [注入原理：构建、加载、服务启动与 USB 连接](docs/injection.md#注入原理)
- [rootless 与 RootHide 的区别](docs/injection.md#rootless-与-roothide)
