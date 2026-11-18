# ArduPilot 多旋翼官方调参流程

> 来源：ArduPilot Copter 官方文档，检索日期 2026-10-30。本文是流程摘要，未对某一实机验证；参数适用范围以本机固件文档为准。

## 结论

官方顺序不是“先跑 AutoTune”，而是：

**机械与动力正确 → 初始参数 → 稳定首飞 → 评估当前控制 → 配置噪声陷波 → 手动调参或 QuikTune → AutoTune → 输入整形与日志复核。**

滤波不能掩盖机械问题，AutoTune 也不能把一架尚不能安全悬停的机子自动变好。

## 1. 调参前置条件

### 机械与电气

- 机架类型、电机编号、转向和桨型必须与混控一致；无桨完成电机测试。
- 遥控器先校准，再按电调类型处理校准。DShot、CAN 等数字电调不按传统 PWM 方式做行程校准。
- 机臂、电机座、桨座无松动；桨、电机和桨夹无明显不平衡；飞控安装遵循制造商减振要求，线束不能把飞控重新“硬连”到机架。
- 电调、电池、导线和配电能够承受实际电流；电压/电流监测先与外部仪表比对。

### 初始参数组

官方“Setting the Aircraft Up for Tuning”重点包括：

| 参数组 | 作用与注意 |
| --- | --- |
| `MOT_BAT_VOLT_MAX` / `MOT_BAT_VOLT_MIN` | 电池电压范围，用于电压变化下的推力补偿；按实际电芯类型和串数设置 |
| `MOT_THST_EXPO` | 电机/电调/桨组合的推力非线性；专业机型建议用拉力台测量，不直接相信宣传曲线 |
| `MOT_PWM_MIN/MAX` | PWM 输出端点，数字协议或固定范围电调按制造商手册 |
| `MOT_SPIN_ARM` / `MOT_SPIN_MIN` | 无桨电机测试确定可靠启动与最小连续运转区间；过高会压缩低端控制余量 |
| `MOT_THST_HOVER` | 初始估计可偏保守，后续结合悬停学习/实测修正 |
| `INS_GYRO_FILTER`、`INS_ACCEL_FILTER`、`ATC_RAT_*_FLT*` | 初始滤波范围与机型/桨径相关，不能跨机照搬 |
| `ATC_ACC_P/R/Y_MAX` | 各轴最大角加速度需求，应与机体惯量和执行能力匹配 |

官方也提供 Mission Planner 的 Initial Parameter Setup 和 Methodic Configurator 作为分阶段入口。

## 2. 初始试飞：先获得“稳定但未优化”的状态

官方 Initial Tuning Flight 的核心安全动作：

1. 使用 Stabilize；确认机架类型、电机编号和方向；设置并测试紧急停桨/上锁方式。
2. 在低风、空旷场地，先做一次解锁后立即上锁，验证操作流程。
3. 缓慢加油门，一旦离地就轻柔落回，检查是否有振荡、异常声音或控制方向错误。
4. 再次起飞，低高度悬停并给很小横滚/俯仰输入；出现振荡立即落地。
5. 若起飞即振荡，官方流程是成组降低横滚和俯仰的 `ATC_RAT_*_P/I/D`，直至可以无可见/可闻振荡悬停，再开展后续测试。
6. AltHold 要在 Stabilize 起飞后切换验证，不要把未经验证的高度控制当成首飞保障。

此阶段目标只是“可安全做后续试验”，不是追求手感或最小超调。

## 3. AutoTune 前的控制评估

官方 Evaluating the Aircraft Tune 的测试方法：

- 在 AltHold 或 Stabilize 中，从小角度横滚/俯仰输入开始，逐渐增加到满杆并快速回中。
- 观察回正后的超调和振荡；如果明显超调或持续振荡，应停止测试，先手动调参。
- 可在官方指导下通过 `ATC_RATE_FF_ENAB` 暂时区分输入整形与基础稳定环的影响，测试结束后恢复。

只有当前控制能承受 AutoTune 的连续扰动，才进入下一步。

## 4. 动态谐波陷波：先看频谱，再选频率源

第一组参数以 `INS_HNTCH_` 为前缀，第二组以 `INS_HNTC2_` 为前缀。启用后需重启飞控显示完整参数。

| 频率来源 | 主要设置 | 适用条件与限制 |
| --- | --- | --- |
| 油门位置 | `INS_HNTCH_MODE = 1`，并设置参考值等 | 无 RPM 也可使用，但配置依赖推力模型；载荷变化后需复核 |
| ESC 遥测 | `INS_HNTCH_MODE = 3` | 官方通常优先推荐，前提是 RPM 快速、可靠；可按各电机分别陷波 |
| 飞行中 FFT | `INS_HNTCH_MODE = 4`，并启用 FFT | 需要固件和处理器支持；两组陷波不能同时都使用 FFT |
| RPM 传感器 / 静态 | 对应模式与频率参数 | 用于特定传感器或已知固定噪声峰 |

验证闭环：

1. 用 IMU Batch Sampler 或原始 IMU 日志获得噪声频谱。
2. 配置中心频率来源、谐波数量和必要选项。
3. 短试飞并再次采集滤波后的数据。
4. 用 ArduPilot Filter Review/WebTools 比较前后频谱，再决定是否增加谐波或第二组陷波。

**CPU 是约束条件。** 电机数 × 谐波数 × 多峰/多重陷波会快速增加滤波器数量，尤其不能为了“滤得干净”在低端飞控上全开。混叠、过软安装和结构共振应回到机械层面处理。

## 5. AutoTune 的条件、过程与保存

官方要求 Copter 在 AltHold 中已经基本可飞，并建议先完成噪声陷波及 QuikTune/手动基础调参。常见失败原因包括强风、高陀螺噪声、错误推力 Expo、柔性机架或载荷安装、过软减振、非线性电调响应和动力过载。

执行要点：

- 在空旷、低风环境，以 AltHold 为基础，配置可随时退出的开关或模式。
- AutoTune 会主动施加横滚/俯仰扰动；操控者仍可 reposition，并必须准备随时中止。
- 完成后先对比新旧增益；只有按官方流程保留新增益并降落上锁，结果才会保存。
- 出现强风、明显振荡或异常时，回到上一步，不要用多次 AutoTune 掩盖问题。

## 6. 日志复核与常用判据

| 检查 | 官方日志/工具 | 要看什么 |
| --- | --- | --- |
| 振动 | `VIBE.VibeX/Y/Z` | 官方经验值：通常宜低于 30 m/s²；高于 30 可能出问题，高于 60 几乎总会影响位置/高度保持。它是经验筛查，不代替频谱和机型判断 |
| 削波 | `VIBE.Clip0/1/2` | 理想为 0；持续增长是严重机械/振动问题的信号 |
| 姿态跟踪 | `ATT.DesRoll/Roll`、`DesPitch/Pitch` | 突然且持续分离更像动力/机械失效；周期性误差结合 RATE/PID 判断控制问题 |
| 控制输出 | RATE、PID、电机输出 | 是否饱和、长期偏置、同频振荡；不要只看姿态曲线 |
| 频谱 | Raw IMU/Batch + WebTools | 主振频、谐波、滤波前后变化、是否随转速移动 |
| 定位影响 | EKF、GPS、气压与创新量 | 振动或磁干扰是否已影响估计，而非单纯“手感不好” |

## 7. 常见错误

- 未做电机方向/编号检查就首飞。
- 把别人的整套 `.param` 直接灌入不同动力和机型。
- 机械振动未处理就反复压低滤波或提高 D。
-  AutoTune 前没有稳定基础调参，或在大风中执行。
- 启用大量陷波后不看 CPU、日志和电机温度。
- 为了“能解锁”长期关闭 Pre-Arm 检查；官方要求先解决失败原因。

## 来源

- [Tuning Process Instructions](https://ardupilot.org/copter/docs/tuning-process-instructions.html)
- [Setting the Aircraft Up for Tuning](https://ardupilot.org/copter/docs/setting-up-for-tuning.html)
- [Initial Tuning Flight](https://ardupilot.org/copter/docs/initial-tuning-flight.html)
- [Evaluating the Aircraft Tune](https://ardupilot.org/copter/docs/evaluating-the-aircraft-tune.html)
- [Dynamic Harmonic Notch Filters](https://ardupilot.org/copter/docs/common-imu-notch-filtering.html)
- [AutoTune](https://ardupilot.org/copter/docs/autotune.html)
- [Measuring Vibration](https://ardupilot.org/dev/docs/common-measuring-vibration.html)
- [Diagnosing Problems Using Logs](https://ardupilot.org/dev/docs/common-diagnosing-problems-using-logs.html)
- [Pre-Arm Safety Checks](https://ardupilot.org/copter/docs/common-prearm-safety-checks.html)
