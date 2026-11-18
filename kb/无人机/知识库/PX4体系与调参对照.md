# PX4 体系与调参对照

> 来源：PX4 中文文档（main 分支），2026-10-30 抓取。重点记录与 ArduPilot 的差异，方便两套系统来回切。

## 1. 控制栈

```
位置/速度 (mc_pos_control) → 姿态 (mc_att_control) → 角速度 (mc_rate_control) → 混控 (mc_mixer)
```

与 ArduPilot 的结构一致，但 PX4 是**模块 + uORB 消息**，每层可独立替换；ArduPilot 是单体 + 参数表。

## 2. 核心参数

| 作用 | PX4 | ArduPilot 对应 |
| --- | --- | --- |
| 角速度 P/I/D | `MC_ROLLRATE_P/I/D` | `ATC_RAT_RLL_P/I/D` |
| 角速度前馈 | `MC_ROLLRATE_K`（标准型）| `ATC_RAT_RLL_FF` |
| 角速度限幅 | `MC_ROLLRATE_MAX` | `ATC_RATE_R_MAX` |
| 角度 P | `MC_ROLL_P` | `ATC_ANG_RLL_P` |
| 偏航角度 P | `MC_YAW_P` | `ATC_ANG_YAW_P` |
| 悬停油门 | `MPC_THR_HOVER` | `MOT_THST_HOVER` |
| 推力曲线 | `MPC_THR_CURVE` | `MOT_THST_EXPO` |
| 气动模式 | `MC_AIRMODE` | 无直接对应（ArduPilot 靠混控余量）|
| 特技手感 | `MC_ACRO_EXPO` / `MC_ACRO_SUPEXPO` / `MC_ACRO_R_MAX` | `ACRO_RP_EXPO` / `ACRO_RP_RATE` |

## 3. 调参流程（官方口径）

1. **先关 `MC_AIRMODE`**（调参时禁用，避免混控饱和掩盖问题）；
2. 机体必须先"欠调"——P、D 都偏低，确保振荡不是控制器引起的；
3. 每次调 20–30%，找到临界后**回撤 5–10%**；
4. 在**悬停推力点附近**整定；高推力段有非线性/振荡时用 `MPC_THR_CURVE`；
5. 角速度环调好后再动角度环；
6. 需要更细的跟踪评估时开 `SDLOG_PROFILE` 高频率日志。

## 4. 滤波链（PX4 的层次比 ArduPilot 更显式）

| 环节 | 参数 | 说明 |
| --- | --- | --- |
| 陀螺片上 DLPF | 传感器内部 | 硬件级，先开 |
| 陀螺低通 | `IMU_GYRO_CUTOFF` | 主低通，降它换噪声、加延迟 |
| D 项低通 | `IMU_DGYRO_CUTOFF` | D 专用，通常比陀螺低通更低 |
| 静态陷波 1/2 | `IMU_GYRO_NF0_FRQ/BW`、`NF1_*` | 固定频率峰（结构共振） |
| 动态陷波 | `IMU_GYRO_DNF_EN/HMC/BW/MIN` | 随 ESC 转速或 FFT 移动 |
| 陀螺采样率 | `IMU_GYRO_RATEMAX` | 控制周期与噪声的折中 |

官方观点：**每加一级滤波都增加延迟；延迟降低 1 ms 都能换来更高的 P**。这与 ArduPilot 的 `INS_GYRO_FILTER` + `INS_HNTCH_*` 是同一套逻辑，只是命名与默认值不同。

## 5. 两套系统怎么选

| 场景 | 建议 |
| --- | --- |
| 行业作业、参数可审计、模式齐全 | ArduPilot |
| ROS2/视觉/集群、需要模块替换 | PX4 |
| 已有 CUAV/Holybro 硬件 | 两者都支持，看团队熟悉度 |

**不要混用参数值**：同样的角速度环 P，两套系统量纲与归一化方式不同。

## 6. 校核清单

- [ ] 传感器校准（加速度计六面、罗盘、水平）在 QGC 里完成
- [ ] 角速度环先单独调，角度环后调
- [ ] 调参时关闭 Airmode，调完再开
- [ ] 高推力段单独验证（推力曲线）
- [ ] 日志用 Flight Review / PlotJuggler 复核，而不是只看手感

## 来源

- [多旋翼 PID 调参（中文）](https://docs.px4.io/main/zh/config_mc/pid_tuning_guide_multicopter.html)
- [滤波与控制延迟（中文）](https://docs.px4.io/main/zh/config_mc/filter_tuning.html)
- [PX4 参数参考](https://docs.px4.io/main/zh/advanced_config/parameter_reference.html)
- 本库：[飞控生态对比](飞控生态对比.md)、[姿态控制原理](姿态控制原理.md)
