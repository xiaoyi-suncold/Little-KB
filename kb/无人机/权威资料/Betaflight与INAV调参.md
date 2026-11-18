# Betaflight 与 INAV 调参要点

> 来源：Betaflight、INAV 官方文档与源码仓库，检索日期 2026-10-30。两套固件版本差异较大，旧版 Tuning Notes 只用于理解机制，不能直接套到当前固件。

## 一、Betaflight：先让默认配置和硬件正常工作

### 1. 不要从“别人的 diff”开始

官方多次强调：升级后不要把旧版本 CLI `diff` 整段灌回，因为默认值、滤波结构和参数语义会变。先从当前固件默认 PID/滤波和正确硬件配置开始，确认电机不热、无异常噪声，再逐步调。

调参前记录：固件与 Configurator 版本、飞控/ESC 固件、电机极数、桨、机架、PID loop、DShot 协议、Blackbox 存储与采样率。

### 2. RPM 滤波：先验证 RPM，再谈滤波

双向 DShot 让 ESC 通过原控制线回传 eRPM，飞控按电机磁极数换算 RPM，并对各电机及其谐波建立陷波。

官方配置与验证要点：

1. ESC 与飞控必须支持双向 DShot，并在 Configurator/CLI 启用。
2. `motor_poles` 要填电机转子的磁极数，不是定子槽数；填错会导致滤波频率错误。
3. 重新上电，在 Motors 页检查各电机 RPM 与遥测错误。官方要求错误率不应超过 1%；只接 USB 未接动力电池时出现 100% 错误不是有效测试。
4. 保留动态陷波处理机架/桨的固定共振；RPM 滤波并不能消除轴承、风和湍流等全部噪声，低通仍有作用。
5. 已飞稳的机子初次启用 RPM 滤波时，不要同时大改其他滤波；之后一次只改一项，并做短悬停、短飞行、温度检查和 Blackbox 对比。

不同版本对动态陷波的自动配置不同，4.1/4.2/4.3 的官方示例不能混用；当前版本以对应 Tuning Notes 和 Release Notes 为准。

### 3. PID、FF 与 Rates 的分工

- **Rates** 主要决定操控输入到目标角速度的映射和手感，不等于机体跟踪能力。
- **P/Tracking** 影响误差纠正和响应；过高会振荡。
- **I/Drift-Wobble** 处理持续误差与姿态保持；过高可能低频摆动或回弹。
- **D/Damping** 提供阻尼、抑制超调和 propwash，但对高频噪声敏感，过高会加热电机。
- **FF/Stick Response** 提升快速杆量变化时的前馈响应；过高会过冲，不能用不断加 P 代替 FF。

官方 PID Tuning Tab 的滑块会成组改变底层参数；切换 RP/RPY 模式可能覆盖偏航设置。修改前保存 Profile 和 `diff all`。

### 4. Blackbox 驱动的小步迭代

建议保留的数据：gyro（含未滤波）、setpoint、PID P/I/D/FF、motor、RPM、电池和必要 debug。采样率与 debug 要服务于问题，避免无目的全量高速日志影响飞控负载。

每次试验：

1. 保存改前 `diff all`，只改一个滤波或控制方向。
2. 短悬停听声音，落地检查电机温度。
3. 做一段可重复的杆量/油门动作，保存 Blackbox。
4. 用官方 Blackbox Explorer 或 PIDtoolbox 比较频谱、setpoint/gyro 跟踪和电机输出。
5. 若噪声增加、异常研磨声或电机明显升温，立即回滚，不继续“飞开就好”。

## 二、INAV：先主稳定，再导航

INAV 面向多旋翼、固定翼和导航功能，不能把 Betaflight 的 PID/滤波配置直接复制过去。先选择与固件大版本匹配的 Configurator 和文档。

### 1. 调参顺序

- 先完成传感器校准、机架/舵面或电机输出、GPS/罗盘安装与基本失效保护。
- 多旋翼先把主稳定 PID/FF 调好；固定翼先处理 FF、控制权限和巡航状态。
- 导航控制器必须在主稳定、RATES、水平/舵面 trim 都正常后调整。罗盘安装和校准不良、振动、重心或动力不足，不能靠导航 PID 补偿。
- 定高问题先检查 GNSS 质量、气压环境、振动、推力与重心，再查 `nav_*_pos_z_*` 等参数。

### 2. TPA 的适用边界

TPA 在油门超过 breakpoint 后衰减 PID，用于“巡航点已调好，但高油门出现振荡”的情况。breakpoint 应靠近实际巡航/悬停工作点；它不是解决全油门范围错误基础调参的通用补丁。固定翼与多旋翼的曲线语义不同，要按对应版本文档设置。

### 3. 失效保护必须实测

INAV 官方提供 DROP、LAND、RTH、NONE 等不同策略，具体名称与行为随版本变化。重点：

- 接收机断链时必须让飞控能识别 failsafe；不要让接收机输出一组看似正常的固定杆量而飞控无法区分。
- RTH 依赖定位、航向和必要传感器；失去关键传感器可能转为紧急降落。
- 固定翼长时间低油门场景要检查 `failsafe_throttle_low_delay`，避免空中误判落地并上锁。
- 先无桨验证断链、恢复控制和 RTH 行为，再在安全空域做受控实测。恢复遥控时杆量会重新生效，要提前准备。

## 三、不可跨机复制的项目

PID、D 项、滤波截止/陷波 Q、TPA、动态怠速、油门与最低转速、RTH 高度/速度、失控动作。它们都依赖机架刚度、动力、桨、飞控安装、载荷和任务环境。

## 来源

- [Betaflight PID Tuning Guide](https://betaflight.com/docs/wiki/guides/current/PID-Tuning-Guide)
- [Betaflight DShot RPM Filtering](https://www.betaflight.com/docs/wiki/guides/current/DSHOT-RPM-Filtering)
- [Betaflight PID Tuning Tab](https://www.betaflight.com/docs/wiki/app/pid-tuning-tab)
- [Betaflight 4.3 Tuning Notes（版本示例）](https://betaflight.com/docs/wiki/tuning/4-3-Tuning-Notes)
- [Betaflight Releases](https://github.com/betaflight/betaflight/releases)
- [INAV 官方文档](https://inavflight.github.io/)
- [INAV Navigation PID Tuning (FW)](https://inavflight.github.io/next/pid-tuning/navigation-pid-tuning-fw)
- [INAV PID Attenuation and Scaling](https://inavflight.github.io/8.0.1/advanced/PID-Attenuation-and-scaling)
- [INAV Failsafe](https://github.com/iNavFlight/inav/blob/master/docs/Failsafe.md)
- [INAV Blackbox](https://github.com/iNavFlight/inav/blob/master/docs/Blackbox.md)
