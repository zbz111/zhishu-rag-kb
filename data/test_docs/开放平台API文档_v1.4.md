# 星海开放平台 API 文档 v1.4

> 基础地址：`https://api.xinghai.example/v1`
> 鉴权方式：请求头 `Authorization: Bearer <token>`
> 限流：单账号 60 次/分钟，超限返回 429

## 一、通用约定

| 项目 | 说明 |
|---|---|
| 编码 | UTF-8 |
| 时间格式 | ISO 8601，如 `2026-09-01T12:00:00+08:00` |
| 分页参数 | `page`（从 1 开始）、`page_size`（默认 20，最大 100） |
| 错误结构 | `{"code": "A001", "message": "参数错误", "request_id": "..."}` |

### 错误码

| code | HTTP | 含义 | 处理建议 |
|---|---|---|---|
| A001 | 400 | 参数缺失或格式错误 | 检查字段类型 |
| A002 | 401 | token 无效或过期 | 重新获取 token |
| A003 | 403 | 无该设备权限 | 确认设备归属 |
| A004 | 404 | 设备不存在 | 核对 device_id |
| A005 | 429 | 触发限流 | 退避重试，建议间隔 2 秒 |
| A006 | 500 | 服务内部错误 | 携带 request_id 联系支持 |

## 二、设备管理

### 2.1 查询设备列表

`GET /devices`

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |
| status | string | 否 | `online` / `offline` / `fault` |

响应示例：

```json
{
  "total": 2,
  "items": [
    {"device_id": "XH-A102-0001", "model": "X1 Pro", "status": "online", "firmware": "1.8.3"},
    {"device_id": "XH-A102-0002", "model": "X1 标准版", "status": "offline", "firmware": "1.8.1"}
  ]
}
```

### 2.2 下发指令

`POST /devices/{device_id}/commands`

请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| command | string | 是 | `reboot` / `volume` / `play` / `stop` |
| payload | object | 否 | 指令参数，如 `{"volume": 60}` |
| timeout_ms | int | 否 | 超时时间，默认 5000 |

**注意**：同一设备 10 秒内最多下发 5 条指令，超出的指令会被丢弃并返回 `A005`。

## 三、固件升级

### 3.1 检查更新

`GET /devices/{device_id}/firmware`

返回当前版本与可升级版本。若 `upgradable` 为 `false`，说明已是最新版本。

### 3.2 触发升级

`POST /devices/{device_id}/firmware/upgrade`

升级过程约 3-5 分钟，期间设备会重启两次，**请勿断电**。升级失败会自动回滚到原版本。

## 四、语音服务

### 4.1 语音识别

`POST /asr`

支持 16kHz、单声道、PCM 或 WAV，单次音频不超过 60 秒，文件不超过 10MB。

### 4.2 语音合成

`POST /tts`

| 参数 | 说明 |
|---|---|
| text | 待合成文本，最长 500 字 |
| voice | 音色，`female_1` / `male_1` / `child_1` |
| speed | 语速 0.5-2.0，默认 1.0 |

## 五、变更记录

| 版本 | 日期 | 变更内容 |
|---|---|---|
| v1.4 | 2026-09-20 | 新增固件升级接口，限流从 30 次/分调整为 60 次/分 |
| v1.3 | 2026-06-11 | 语音合成新增 `child_1` 音色 |
| v1.2 | 2026-03-02 | 设备列表支持 status 过滤 |
