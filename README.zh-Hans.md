# 极氪（Zeekr）Home Assistant 集成

[English](README.md) · **简体中文**

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.7%2B-41BDF5?logo=homeassistant&logoColor=white)](#环境要求)
[![集成类型](https://img.shields.io/badge/type-custom%20integration-blue)](#安装)
[![IoT 类型](https://img.shields.io/badge/IoT%20class-cloud%20polling-informational)](#工作原理)

这是一个非官方的 Home Assistant 极氪（Zeekr）车辆集成。它用极氪账号登录，自动发现账号下支持的车辆，并把电量、续航、胎压、位置、哨兵模式以及远程控制暴露成 Home Assistant 的实体和动作。

本集成由一份 Node-RED 流程移植而来，并取代了它：下文给出了实体对照表，方便已有面板迁移。

> [!WARNING]
> 这不是官方集成。它调用的是极氪手机 App 的云端接口，这些接口未公开且随时可能变化，因此集成随时可能失效。远程控制会作用于真实车辆，请只在安全的情况下发送这些指令。

## 目录

- [功能](#功能)
- [环境要求](#环境要求)
- [安装](#安装)
- [配置](#配置)
- [实体](#实体)
- [动作](#动作)
- [哨兵实时视频卡片](#哨兵实时视频卡片)
- [常见问题](#常见问题)
- [工作原理](#工作原理)
- [限制与免责声明](#限制与免责声明)
- [从 Node-RED 迁移](#从-node-red-迁移)
- [开发](#开发)
- [许可证](#许可证)
- [致谢](#致谢)

## 功能

- **自动发现车辆** —— 登录时按账号创建 Home Assistant 设备，一个受支持的新车型 VIN 对应一个设备。
- **每 60 秒轮询状态** —— 电量、剩余续航、车内温度、四轮胎压、总里程、保养间隔、12 V 电瓶电压、平均电耗、中控锁与电子手刹状态，另有一个 GPS 设备追踪实体，附带电量、车速和里程属性。
- **手动刷新** —— 每台车一个 Refresh 按钮，不必等下一轮轮询。
- **远程控制** —— 寻车（鸣笛闪灯）、锁车/解锁、带目标温度和时长的空调、主驾座椅加热、方向盘加热，另外提供原始指令入口，用于尚未封装的命令。
- **哨兵模式开关** —— 启停 RSM 哨兵服务，并从下一次状态轮询中确认实际状态。
- **哨兵实时视频** —— 一个加入车辆哨兵 RTC 房间的 Lovelace 卡片。RTC Web SDK 已随集成一起托管，播放时无需访问公共 CDN。
- **统计与消息** —— 提供返回数据的动作，可查询月度行程统计和车机升级消息。
- **令牌处理** —— 访问令牌会自动轮换并写回配置条目；过期后 Home Assistant 会提示你重新用短信验证码认证。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| Home Assistant | 2024.7 或更高版本（卡片和 SDK 使用 `StaticPathConfig`） |
| 账号 | 可用极氪 App 登录、且注册手机号为 +86 的极氪账号 |
| 车辆 | 该账号下挂牌的新车型；老车型 VIN 会被排除 |
| 网络 | Home Assistant 需能访问 `api-gw-toc.zeekrlife.com`、`api.zeekrline.com`、`snc-tsp-api.zeekrlife.com` 和 `snc-static.zeekrlife.com` |

每个 Home Assistant 实例只允许配置一个极氪账号（`single_config_entry`）。共享车辆会被一并纳入，共享列表在每次登录时重新读取。

## 安装

### 通过 HACS（自定义仓库）

本集成尚未收录进 HACS 默认商店。

1. 打开 HACS → **集成** → 右上角 **⋮** 菜单 → **自定义存储库**。
2. 填入 `https://github.com/Admingyu/zeekr-homeassistant`，类别选择 **Integration**。
3. 安装 **Zeekr**，然后重启 Home Assistant。
4. 进入 **设置 → 设备与服务 → 添加集成**，选择 **Zeekr**。

### 手动安装

把 `custom_components/zeekr` 复制到 Home Assistant 配置目录下，最终路径应为 `custom_components/zeekr`，重启 Home Assistant，然后在 **设置 → 设备与服务 → 添加集成** 中选择 **Zeekr**。

## 配置

配置只有一个登录流程：

1. 输入极氪 App 使用的手机号，集成会下发短信验证码。
2. 输入验证码。集成完成登录、读取车辆列表，并为每台受支持车辆创建设备 `Zeekr <VIN 后六位>`。

Home Assistant 会依据该设备名生成实体 ID 前缀；实体的稳定部分是下文列出的唯一 ID 后缀。首次状态更新在配置过程中完成。

会话令牌保存在配置条目中，App 使用的固定签名参数保留在集成代码里。当 Home Assistant 提示需要重新认证时，重新走一遍短信流程即可；该流程也会重新读取车辆列表，因此账号的共享车辆发生变化后请重新认证。

## 实体

每台车对应一个设备，以下实体都挂在该设备下。

| 实体 | 平台 | 唯一 ID 后缀 | Node-RED 名称 |
| --- | --- | --- | --- |
| 电量 | sensor | `battery` | Battery |
| 剩余续航 | sensor | `distance_to_empty` | DistanceToEmpty |
| 车内温度 | sensor | `interior_temperature` | InteriorTemp |
| 发动机状态 | sensor | `engine_status` | Engine |
| 左前胎压 | sensor | `tire_pressure_front_left` | TyreStatusDriver |
| 右前胎压 | sensor | `tire_pressure_front_right` | TyreStatusPassenger |
| 左后胎压 | sensor | `tire_pressure_rear_left` | TyreStatusDriverRear |
| 右后胎压 | sensor | `tire_pressure_rear_right` | TyreStatusPassengerRear |
| 保养间隔 | sensor | `distance_to_service` | ServiceLD |
| 总里程 | sensor | `odometer` | TravalTotal |
| 蓄电池电压 | sensor | `main_battery_voltage` | mainBattVoltage |
| 平均电耗 | sensor | `average_power_consumption` | averPowerConsumption |
| 中控锁状态 | sensor | `central_locking_status` | CentralLockingStatus |
| 电子手刹状态 | sensor | `electric_park_brake_status` | electricParkBrakeStatus |
| 充电中 | binary_sensor | `charging` | ChargingState |
| 高压电池优化 | binary_sensor | `hv_battery_optimization` | hvBatteryOptimizeFlag |
| 位置 | device_tracker | `location` | Location |
| 刷新 | button | `refresh` | Refresh |
| 寻车 | button | `find_vehicle` | — |
| 锁车 | button | `lock_doors` | — |
| 解锁车 | button | `unlock_doors` | — |
| 哨兵模式 | switch | `sentry_mode` | SentryModeSwitch |

老车型的状态实体不会创建。旧版账号接口仍会在配置阶段调用，用于识别老车型 VIN 并把它们从支持列表中排除。

某个车型的状态响应中缺少某字段时，对应实体会显示为不可用，而不是显示过期或凭空捏造的值。刷新、远程指令和哨兵开关都只轮询受影响的那台车。

## 动作

### 状态查询

| 动作 | 字段 | 返回 |
| --- | --- | --- |
| `zeekr.get_monthly_statistics` | `vin`、`year_month`（`YYYY-MM`）、`account_id` | 服务端返回的月度行程统计 |
| `zeekr.get_app_messages` | `vin` | 服务端返回的车机升级消息列表 |

两者都会返回服务响应，请在支持响应的动作界面，或在带 `response_variable` 的自动化/脚本中调用：

```yaml
action: zeekr.get_monthly_statistics
data:
  vin: YOUR_VIN
  year_month: "2025-10"
  account_id: YOUR_ACCOUNT_ID
response_variable: statistics
```

`account_id` 就是集成配置条目中以 `user_id` 保存的极氪账号标识。

### 远程控制

所有远程指令都发往同一个 App 接口（`/ms-remote-control/v1.0/remoteControl/control`），只是请求体不同。无参数的命令同时以上表的按钮形式提供：

| 动作 | 字段 | 效果 |
| --- | --- | --- |
| `zeekr.find_vehicle` | `vin` | 鸣笛并闪灯 |
| `zeekr.lock_doors` | `vin` | 锁闭所有车门 |
| `zeekr.unlock_doors` | `vin` | 解锁所有车门 |
| `zeekr.set_climate` | `vin`、`enabled`、`temperature`（16–30 °C，默认 22）、`duration`（1–30 分钟，默认 15） | 开启或关闭空调 |
| `zeekr.set_seat_heating` | `vin`、`enabled`、`level`（1–3，默认 3）、`duration`（1–15 分钟，默认 15） | 主驾座椅加热 |
| `zeekr.set_steering_wheel_heating` | 同座椅加热 | 方向盘加热 |
| `zeekr.remote_control` | `vin`、`service_id`、`command`（默认 `start`）、`parameters` | 其他任意 App 指令 |

开启空调，22 °C，运行 15 分钟：

```yaml
action: zeekr.set_climate
data:
  vin: YOUR_VIN
  enabled: true
  temperature: 22
  duration: 15
```

关闭空调：

```yaml
action: zeekr.set_climate
data:
  vin: YOUR_VIN
  enabled: false
```

开启方向盘加热，3 档，运行 15 分钟：

```yaml
action: zeekr.set_steering_wheel_heating
data:
  vin: YOUR_VIN
  enabled: true
  level: 3
  duration: 15
```

发送尚未封装的服务 ID：

```yaml
action: zeekr.remote_control
data:
  vin: YOUR_VIN
  service_id: ZAF
  command: start
  parameters:
    AC: "true"
    AC.temp: "22.0"
    AC.duration: "15"
```

这些命令没有可确认的状态：状态接口不提供稳定的空调、加热或车门状态。因此它们以无状态按钮和动作的形式提供，而不是 switch 或 climate 实体；每条指令执行后集成会额外轮询一次该车，让相关实体更快刷新。只有哨兵模式能读回状态，因为 `basicVehicleStatus.usageMode` 会上报它。

请求体与 App 当前的行为保持一致，包括它并不统一的取值类型——空调和座椅的标志位是字符串 `"true"`/`"false"`，方向盘加热的标志位是 JSON 布尔值，寻车和方向盘加热使用空的 `command`，其余命令发送 `start`。这些请求体以纯函数形式放在 `custom_components/zeekr/remote_control.py`，并由 `tests/test_remote_control.py` 锁定。

目前只封装了主驾座椅（`SH.11`）；其他座位需要用各自的 App 参数键，通过 `zeekr.remote_control` 发送。

## 哨兵实时视频卡片

安装集成会同时托管卡片文件，但 Home Assistant 不会自动把它加到面板上，需要先注册 JavaScript 资源：

1. 打开 **设置 → 面板**，点右上角 **⋮** 菜单，选择 **资源**。
2. 选择 **添加资源**，填入：

   | URL | 类型 |
   | --- | --- |
   | `/api/zeekr/zeekr-sentinel-card.js` | JavaScript 模块 |

3. 保存后使用 **⋮ → 重新加载资源**（或刷新浏览器页面）。
4. 打开面板，选择 **编辑面板 → 添加卡片**，搜索 **Zeekr 哨兵视频**。
5. 如果列表中没有，选择 **手动** 并粘贴：

```yaml
type: custom:zeekr-sentinel-card
```

卡片自带车辆选择器和 **开始观看** 按钮，不需要填写实体 ID。如果 Home Assistant 提示自定义元素不存在，说明资源没加载成功——检查 URL 和类型，重新加载资源，再重新打开面板编辑器。

卡片会向集成申请一个短期的房间会话，然后用固定版本的 `@volcengine/rtc@4.69.2` Web SDK 加入房间并渲染车辆主码流。房间时长或 RTC 令牌过期时它会自动重连。SDK 随集成一起托管，由 `/api/zeekr/volcengine-rtc-4.69.2.js` 提供，因此播放不依赖任何公共 CDN；随附副本的 BSD-3-Clause 许可证位于 `custom_components/zeekr/www/volcengine-rtc-LICENSE`。若该文件加载失败，卡片会回退到 `unpkg.com` 上的同版本文件。

浏览器只会拿到短期的 RTC 会话令牌。极氪账号令牌和请求签名密钥都留在集成后端。

## 常见问题

**集成拒绝手机号，或收不到验证码。** 目前只支持 +86 账号。确认该号码能在极氪 App 正常登录后重试——服务端对频繁索取验证码有限制。

**登录成功但没有出现车辆。** 该账号下没有新车型 VIN。老车型被有意排除，此时日志会给出 `No supported new-model vehicles were found`。

**Home Assistant 提示需要重新认证。** 保存的会话已过期且无法刷新。重新走一遍短信流程即可，这也会重新读取共享车辆列表。

**部分实体一直是不可用。** 该车型的状态响应里没有这个字段。实体可用性跟随响应，不会缓存旧值。

**点击哨兵开关后状态又弹回去了。** 车辆返回了 `000000`，但后续轮询没有上报请求的使用模式。等车辆恢复网络覆盖后重试。

**卡片提示自定义元素不存在。** 它的 JavaScript 资源没有加载，参见 [哨兵实时视频卡片](#哨兵实时视频卡片)。

**卡片状态里显示 RTC 错误、无法播放。** 卡片连不上极氪的 RTC 服务，或引擎无法加入房间。先在极氪 App 里确认该车的哨兵服务是开启的。

## 工作原理

```
config_flow.py ── 短信登录 ─────┐
                                ├─ api.py ── 三套带签名的 HTTP 客户端
signing.py ─────────────────────┘   （网关、旧版账号、新版车辆接口）
                                        │
                                coordinator.py ── 每 60 秒轮询所有 VIN
                                        │
        sensor · binary_sensor · device_tracker · button · switch
```

- **三层鉴权。** 短信登录返回 JWT。网关会为该 JWT 签发一个 auth code，旧版账号接口用它换取会话（提供 `user_id` 和老车型 VIN 列表）；同一个 JWT 也用于登录新版车辆接口。每层的签名方案都在 `signing.py`：网关是对排序后的值做 SHA-1，旧版接口是带 body MD5 的 HMAC-SHA1，新版接口是对排序后的 header、query 和 body 做 HMAC-SHA256，并把 VIN 加密后放进 `X-VIN` 头。
- **每个账号一个协调器。** 单个 `DataUpdateCoordinator` 按 60 秒间隔轮询所有受支持 VIN 并共享结果给各平台；单车操作只刷新该 VIN。
- **没有本地状态回写。** 实体只读协调器数据，不会在本地改写状态，因此不会出现车辆没上报却被显示成某个值的实体。

## 限制与免责声明

- 本集成非官方，与极氪官方无关。所用接口和签名参数均未公开，可能随时变化。
- 账号、车辆和 RTC 调用都依赖极氪云服务。服务中断、不同车型的响应差异以及地域限制都不在本集成控制范围内。
- 远程控制作用于真实车辆。配置锁车、解锁、空调或加热自动化前请确认 VIN，不要把这类命令放在一旦误触发就有危险的位置无人值守运行。
- 空调、加热和车门没有可确认状态，因此自动化无法等待这些命令得到确认。
- 项目仅在一个账号和一台车上验证过。短信登录、当前响应字段、远程指令和面板播放都需要真实凭据才能测试。

## 从 Node-RED 迁移

[实体](#实体)表列出了每个 Node-RED 实体名对应的新平台和唯一 ID 后缀。已有的实体 ID 和自动化不会被自动改写——集成创建好设备后，请把自动化改到新的实体 ID 上。

Node-RED 里的 `Unlock` 按钮只是触发一次刷新；本集成实现了真正的锁车和解锁指令。

## 开发

测试使用标准库 `unittest`，直接导入集成模块，不需要安装 Home Assistant：

```bash
python -m unittest discover -s tests -v
```

| 路径 | 用途 |
| --- | --- |
| `custom_components/zeekr/api.py` | HTTP 客户端、令牌轮换、车辆与哨兵调用 |
| `custom_components/zeekr/signing.py` | 三套请求签名方案 |
| `custom_components/zeekr/remote_control.py` | 远程指令请求体 |
| `custom_components/zeekr/coordinator.py` | 账号运行时与共享状态轮询 |
| `custom_components/zeekr/www/` | Lovelace 卡片与随附的 RTC SDK |
| `tests/` | 签名与请求体的黄金测试 |

新增远程指令时，请先在 `remote_control.py` 里加请求体构造函数，补一条对应的黄金测试，再通过 `api.py` 暴露；如果命令需要参数，再加一个动作。

## 许可证

本仓库目前没有 LICENSE 文件，这意味着默认保留所有权利。如需再分发或派生作品，请先开 issue 讨论许可证。

随附的 RTC SDK（`custom_components/zeekr/www/volcengine-rtc-4.69.2.js`）版权归 The VolcEngineRTC project authors 所有，采用 BSD-3-Clause 许可证，许可证全文已放在该文件旁边。

## 致谢

- 原有的行为与实体集合来自作者的 Node-RED 流程，本集成取代了它。
- 车辆实时视频使用 [火山引擎 RTC](https://www.volcengine.com/product/rtc) Web SDK。
