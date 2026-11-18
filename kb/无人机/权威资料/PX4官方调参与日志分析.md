# PX4 多旋翼官方调参与日志分析

> 来源：PX4、QGroundControl 官方文档，检索日期 2026-10-30。链接含 `main` 的为开发版文档，使用时应切换至本机稳定版本。

## 结论

PX4 的控制器是串级的：**速率环最内层，其上是姿态环，再上是速度与位置环。** 调参按同一顺序进行。AutoTune 适合多数基础机型；手动精细调参、滤波和日志分析用于非线性、振动或高推力振荡等情况。

## 1. 前置条件

- 在 QGroundControl 选择最接近的真实机架，并完成执行器配置、传感器校准、遥控校准和电调/电机检查。
- PWM 电调按官方流程校准；DShot 等数字协议不要套用 PWM 校准。
- 无桨确认输出映射、电机编号、转向、最低输出下不会停转。
- 配置可用的 Kill switch/退出方式；手动调参和 AutoTune 都是在真实飞行中进行的。
- 调速率环时使用足够快的遥测链路，QGC 的 PID Tuning 页面可显示设定值与响应曲线。
- 按官方要求，在调参阶段处理 `MC_AIRMODE`，不要把它与待诊断的控制问题混在一起。

## 2. 手动 PID：从速率环向外

### 速率环

横滚、俯仰、偏航分别对应 `MC_ROLLRATE_*`、`MC_PITCHRATE_*`、`MC_YAWRATE_*` 参数组。官方 Advanced 文档同时说明 Parallel 与 Standard 两种等价形式及 `K` 增益，不应只复制 P/I/D 数字而忽略形式。

典型现象：

- P 过低：响应迟缓；过高：高频振荡。
- D 用于阻尼和抑制超调，但会放大噪声；过高可能造成电机抖动和发热。
- I 用于消除持续误差；过高可能引入低频振荡或回弹。

官方建议逐步调整、落地后改参数，并围绕悬停推力点调参。推力非线性或高推力振荡要使用推力曲线/相应补偿，而不是无限增加增益。

### 姿态环

速率环稳定后再调 `MC_ROLL_P`、`MC_PITCH_P`、`MC_YAW_P`。姿态环过快而速率环跟不上时，会出现较慢的振荡；不要把所有振荡都归因于速率 P 过高。

### 速度与位置环

在 Position 模式下观察速度/位置设定值与实际响应，处理超调、刹车过冲和轨迹滞后。若执行器已饱和或动力余量不足，应先改动力、重量或控制分配，而不是继续加增益。

## 3. AutoTune：先通过预测试，再允许它激励机体

官方预测试要求飞机已经能自行稳定：

1. 正常完成飞行前检查，在低高度安全悬停。
2. 分别对横滚、俯仰施加小角度扰动并回中，逐步增加幅度。
3. 官方判据是扰动后能在约两次振荡内稳定，才适合继续；否则先按故障排查降低相应姿态/速率增益。

执行时：

- 选择空旷、低风场地，使用官方推荐模式，并准备通过换模式或开关随时中止。
- 在 QGC `Vehicle Setup → PID Tuning` 启用 AutoTune，观察进度，不要离开或做无关操作。
- 多旋翼通常在降落并上锁后应用新增益；`MC_AT_APPLY` 决定不应用、上锁后应用或立即应用，默认值需按本机版本核实。
- 应用后再次小心起飞验证。若出现强振荡，立即落地并回到预测试故障排查。
- 激励不足导致辨识失败时，官方提供 `MC_AT_SYSID_AMP` 等调整入口，但应在理解风险后逐步调整，不能用来强行救一架不稳定飞机。

## 4. 滤波：在控制延迟与噪声之间取舍

官方滤波链主要包括：

| 环节 | 参数/功能 | 用途与风险 |
| --- | --- | --- |
| 静态陀螺陷波 | `IMU_GYRO_NF0_FRQ/BW`，以及第二组 `NF1` | 处理固定窄带峰；频率和带宽必须来自本机频谱 |
| 动态陷波 | `IMU_GYRO_DNF_*`；来源可为 ESC RPM 或机载 FFT | 跟踪旋翼相关噪声；RPM 必须正确，电机极数配置错误会使频率整体错位 |
| 陀螺低通 | `IMU_GYRO_CUTOFF` | 提高截止可降低延迟，但会让更多噪声进入控制与电机 |
| D 项低通 | `IMU_DGYRO_CUTOFF` | D 对噪声更敏感，可单独滤波；与陀螺低通过度失配也会影响表现 |
| 高速日志 | `SDLOG_PROFILE` | 为 Flight Review 的 FFT 和调参评估提供足够数据 |

官方 Filter Tuning 的基本方法：先做一轮偏保守的基础 PID，确保看到的是噪声而不是控制振荡；用相似的短时悬停/横滚/俯仰/油门动作采集日志，再比较低通设置。出现明显机械振动时先修机械，不靠滤波“救机”。

每次改滤波后做短试飞，听异常声音、落地检查电机温度，并复核日志。官方示例截止值只对应示例机型，不是通用推荐值。

## 5. Flight Review / ULog 分析顺序

入口：[https://review.px4.io/](https://review.px4.io/)。建议按以下顺序读图：

1. **飞行事件与模式**：确认异常发生时的模式、告警和日志完整性。
2. **速率与姿态跟踪**：比较 setpoint 与 actual，识别超调、滞后、周期振荡。
3. **执行器输出**：检查电机是否饱和、长期偏置或控制分配余量不足。
4. **IMU 波形与频谱**：看主振频、谐波、削波，及其与油门/RPM 的时间对应关系。
5. **位置与速度**：在内环已稳定后评估轨迹、刹车和抗风表现。
6. **EKF2 状态与创新量**：判断振动、传感器不一致是否已污染状态估计。

关键辨别：

- 设定值平滑而实际持续振荡：结合内环增益与机械频谱排查。
- 电机长期一顶一底：查重心、机架、动力差异和控制分配。
- 电机频繁饱和：不是继续加 P 的理由。
- 主振频随 RPM 移动：优先查桨、电机、轴承、桨座与 RPM 滤波；固定窄峰则考虑结构模态或静态陷波。

## 6. 版本与回滚

- `main` 页面可能包含尚未进入本机稳定版的参数；先记录固件版本并切换文档。
- 每次保存改前参数、QGC 参数快照和对应 ULog；一次只改一类变量。
- 新增益/新滤波只有在复飞和日志都通过后才接受，不能仅凭“感觉更跟手”。

## 来源

- [Multicopter PID Tuning Guide (Manual/Advanced)](https://docs.px4.io/main/en/config_mc/pid_tuning_guide_multicopter)
- [Autotune](https://docs.px4.io/main/en/config/autotune.html)
- [MC Filter Tuning & Control Latency](https://docs.px4.io/main/en/config_mc/filter_tuning.html)
- [Flight Review](https://docs.px4.io/main/en/log/flight_review)
- [Flight Log Analysis](https://docs.px4.io/main/en/dev_log/flight_log_analysis.html)
- [QGroundControl Tuning](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/setup_view/tuning_px4.html)
- [QGroundControl Sensors](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/setup_view/sensors_px4.html)
