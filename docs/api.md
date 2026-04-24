# API 文档

Base URL: `http://localhost:8000/api/v1`

## 认证

### 注册
```
POST /auth/register
Content-Type: application/json

{
  "username": "examiner01",
  "password": "password123"
}

Response 201:
{
  "id": 1,
  "username": "examiner01",
  "is_active": true,
  "created_at": "2026-04-24T10:00:00"
}
```

### 登录
```
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=examiner01&password=password123

Response 200:
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

## 考试管理

所有考试接口需要 Bearer Token:
```
Authorization: Bearer <access_token>
```

### 上传考试视频
```
POST /exam/upload
Content-Type: multipart/form-data

file: <video_file>

Response 200:
{
  "exam_id": 1,
  "task_id": "abc-123-def",
  "status": "pending"
}
```

支持格式: .mp4, .mov, .avi, .mkv, .webm
最大文件: 2048MB

### 查询处理状态
```
GET /exam/{exam_id}/status

Response 200:
{
  "id": 1,
  "status": "processing",
  "progress": 45
}
```

status 取值: pending / processing / completed / failed
progress: 0-100

### 获取评分结果
```
GET /exam/{exam_id}/result

Response 200:
{
  "exam_id": 1,
  "total_score": 72.5,
  "max_total": 100.0,
  "items": [
    {
      "phase": "phase1_before_arrival",
      "rule_code": "carry_defibrillator",
      "rule_name": "携带除颤监护一体机",
      "max_score": 1.0,
      "actual_score": 1.0,
      "deduction_reason": null
    }
  ],
  "phase_scores": {
    "phase1_before_arrival": {"score": 4.0, "max_score": 5.0},
    "phase2_arrival_step1": {"score": 5.0, "max_score": 5.0}
  }
}
```

### 获取事件时间轴
```
GET /exam/{exam_id}/timeline

Response 200:
{
  "events": [
    {
      "id": 1,
      "exam_id": 1,
      "time_seconds": 12.5,
      "actor": "SPEAKER_00",
      "event_type": "chest_compression",
      "event_data": null,
      "source": "video",
      "confidence": 0.93
    }
  ]
}
```

### 获取HTML报告
```
GET /exam/{exam_id}/report

Response 200: (HTML content)
```

### 获取考试列表
```
GET /exams?page=1&page_size=20

Response 200:
{
  "items": [...],
  "total": 15
}
```

## 健康检查
```
GET /health

Response 200:
{
  "status": "ok",
  "service": "Emergency-AI-Examiner"
}
```
