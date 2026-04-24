import axios from 'axios'
import type { Exam, ExamStatus, ScoreResult, ExamEvent } from '../types'

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

export const uploadExam = async (file: File): Promise<Exam> => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post<Exam>('/exam/upload', formData, {
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
  const response = await api.get<ExamEvent[]>(`/exam/${id}/timeline`)
  return response.data
}

export const getExams = async (page = 1, pageSize = 10): Promise<{ items: Exam[]; total: number }> => {
  const response = await api.get<{ items: Exam[]; total: number }>('/exams', {
    params: { page, pageSize },
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
