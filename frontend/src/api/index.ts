import axios from 'axios'
import type { Exam, ExamStatus, ScoreResult, ExamEvent, SensorData, ExamDebugData } from '../types'

const api = axios.create({
  baseURL: '/api/v1',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 默认设备码 - 页面上传时若未指定, 统一使用此值
const DEFAULT_DEVICE_CODE = '8888888'

// 满分 CPR 指标 - 与后端 PERFECT_MOCK_METRICS 保持一致
const PERFECT_METRICS = {
  session_duration_sec: 180.0,
  compression_duration_sec: 150.0,
  press_total: 200,
  press_correct: 190,
  press_wrong: 10,
  press_frequency: 110.0,
  press_avg_depth: 52.0,
  blow_total: 20,
  blow_correct: 19,
  blow_wrong: 1,
  blow_avg_volume: 540.0,
  shoulder_tapped: true,
}

export const uploadExam = async (
  file: File,
  deviceCode: string = DEFAULT_DEVICE_CODE,
  metrics: Record<string, unknown> | null = PERFECT_METRICS,
): Promise<{ exam_id: number; task_id: string }> => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('device_code', deviceCode)
  if (metrics) {
    formData.append('metrics', JSON.stringify(metrics))
  }
  const response = await api.post<{ exam_id: number; task_id: string }>('/exam/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

export const getExamStatus = async (id: number): Promise<ExamStatus> => {
  const response = await api.get<ExamStatus>(`/exam/${id}/status`)
  return response.data
}

export const getExamResult = async (id: number): Promise<ScoreResult> => {
  const response = await api.get<ScoreResult>(`/exam/${id}/result`)
  return response.data
}

export const getExamTimeline = async (id: number): Promise<ExamEvent[]> => {
  const response = await api.get<{ events: ExamEvent[] }>(`/exam/${id}/timeline`)
  return response.data.events
}

export const getExamScores = async (id: number): Promise<ScoreResult> => {
  const response = await api.get<ScoreResult>(`/exam/${id}/result`)
  return response.data
}

export const getSensorData = async (id: number): Promise<SensorData | null> => {
  try {
    const response = await api.get<SensorData>(`/sensor/${id}`)
    return response.data
  } catch {
    return null
  }
}

export const generateMockSensor = async (id: number): Promise<SensorData> => {
  const response = await api.post<SensorData>(`/sensor/mock/${id}`)
  return response.data
}

// 下载考核结果 PDF - 后端返回 application/pdf 二进制流
export const downloadExamReportPdf = async (id: number): Promise<void> => {
  const response = await api.get(`/exam/${id}/report/pdf`, {
    responseType: 'blob',
  })

  // 优先从 Content-Disposition 取文件名 (RFC 5987 UTF-8 编码)
  const disposition = response.headers['content-disposition'] || ''
  let filename = `院外心脏骤停急救考核评分表_${id}.pdf`
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (utf8Match) {
    try {
      filename = decodeURIComponent(utf8Match[1])
    } catch {
      // 解码失败时退回默认中文名
    }
  }

  const blob = new Blob([response.data], { type: 'application/pdf' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export const getExamDebugData = async (id: number): Promise<ExamDebugData | null> => {
  try {
    const response = await api.get<ExamDebugData>(`/exam/${id}/debug`)
    return response.data
  } catch {
    return null
  }
}

export const getExams = async (
  page = 1,
  pageSize = 10,
  deviceCode?: string,
): Promise<{ items: Exam[]; total: number }> => {
  // 历史考核记录页面默认列出所有设备的记录, 因此不再强制传 device_code
  // 传了 deviceCode 时仅过滤该设备的数据 (兼容按设备筛选场景)
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (deviceCode) {
    params.device_code = deviceCode
  }
  const response = await api.get<{ items: Exam[]; total: number }>('/exams', {
    params,
  })
  return response.data
}

export const login = async (username: string, password: string): Promise<{ access_token: string }> => {
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  const response = await api.post<{ access_token: string }>('/auth/login', formData)
  return response.data
}

export const register = async (username: string, password: string): Promise<{ id: number; username: string }> => {
  const response = await api.post<{ id: number; username: string }>('/auth/register', { username, password })
  return response.data
}
