import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Spin, Result, Card } from 'antd'
import { ArrowLeftOutlined, FileTextOutlined } from '@ant-design/icons'
import { getExamStatus, getExamTimeline } from '../api'
import type { ExamStatus, ExamEvent } from '../types'
import { usePolling } from '../hooks/usePolling'
import VideoPlayer from '../components/VideoPlayer'
import Timeline from '../components/Timeline'
import PipelineProgress from '../components/PipelineProgress'

const ExamDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const examId = parseInt(id || '0', 10)
  
  const [status, setStatus] = useState<ExamStatus | null>(null)
  const [events, setEvents] = useState<ExamEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [currentTime, setCurrentTime] = useState(0)
  const [videoDuration, setVideoDuration] = useState(0)

  const fetchStatus = async () => {
    if (!examId) return
    try {
      const data = await getExamStatus(examId)
      setStatus(data)
      
      if (data.status === 'completed') {
        const timelineData = await getExamTimeline(examId)
        setEvents(timelineData)
        
        if (timelineData.length > 0) {
          const maxTime = Math.max(...timelineData.map(e => e.time_seconds))
          setVideoDuration(Math.max(maxTime + 10, 100))
        }
      }
    } catch (error) {
      console.error('Failed to fetch exam status:', error)
    } finally {
      setLoading(false)
    }
  }

  const isProcessing = status?.status === 'pending' || status?.status === 'processing'
  usePolling(fetchStatus, isProcessing ? 2000 : null, true)

  const handleTimeUpdate = (time: number) => {
    setCurrentTime(time)
    if (time > videoDuration) {
      setVideoDuration(time)
    }
  }

  const handleEventClick = (time: number) => {
    setCurrentTime(time)
  }

  if (loading && !status) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spin size="large" tip="加载中..." />
      </div>
    )
  }

  if (!status) {
    return <Result status="404" title="未找到该考核记录" />
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>返回</Button>
          <h2 className="text-xl font-bold m-0">考核详情 #{examId}</h2>
        </div>
        
        {status.status === 'completed' && (
          <Button 
            type="primary" 
            icon={<FileTextOutlined />} 
            onClick={() => navigate(`/exam/${examId}/report`)}
          >
            查看详细报告
          </Button>
        )}
      </div>

      {isProcessing ? (
        <div className="py-8">
          <div className="text-center mb-8">
            <h3 className="text-2xl font-bold text-slate-800 flex items-center justify-center gap-3">
              <span className="relative flex h-4 w-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-4 w-4 bg-orange-500"></span>
              </span>
              AI多模态分析进行中
            </h3>
            <p className="text-slate-500 mt-2">系统正在对视频和音频进行深度解析，请耐心等待</p>
          </div>
          
          <PipelineProgress 
            progress={status.progress} 
            status={status.status as 'pending' | 'processing' | 'completed' | 'failed'} 
          />
          
          <div className="text-center mt-8 text-slate-400 text-sm">
            预计剩余时间: {Math.max(1, Math.ceil((100 - status.progress) / 10))} 分钟
          </div>
        </div>
      ) : status.status === 'failed' ? (
        <Result
          status="error"
          title="分析失败"
          subTitle="视频处理过程中出现错误，请重新上传。"
          extra={[
            <Button type="primary" key="home" onClick={() => navigate('/')}>
              返回首页
            </Button>
          ]}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
              <VideoPlayer 
                src={`/api/v1/exam/${examId}/video`} 
                currentTime={currentTime}
                onTimeUpdate={handleTimeUpdate}
              />
              <Timeline 
                events={events} 
                duration={videoDuration} 
                currentTime={currentTime}
                onEventClick={handleEventClick}
              />
            </div>
          </div>
          
          <div className="space-y-6">
            <Card title="当前事件" className="shadow-sm">
              <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2">
                {events
                  .filter(e => Math.abs(e.time_seconds - currentTime) < 5)
                  .map(event => (
                    <div key={event.id} className="p-3 bg-blue-50 rounded border border-blue-100">
                      <div className="font-bold text-blue-800">{event.event_type}</div>
                      <div className="text-sm text-gray-600 mt-1">
                        时间: {event.time_seconds}s | 置信度: {(event.confidence * 100).toFixed(1)}%
                      </div>
                      {event.actor && (
                        <div className="text-sm text-gray-600">执行者: {event.actor}</div>
                      )}
                    </div>
                  ))}
                {events.filter(e => Math.abs(e.time_seconds - currentTime) < 5).length === 0 && (
                  <div className="text-gray-400 text-center py-8">当前时间点无显著事件</div>
                )}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}

export default ExamDetail
