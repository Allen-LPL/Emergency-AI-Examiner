import React from 'react'
import { Tooltip } from 'antd'
import type { ExamEvent } from '../types'

interface TimelineProps {
  events: ExamEvent[]
  duration: number
  currentTime: number
  onEventClick: (time: number) => void
}

const Timeline: React.FC<TimelineProps> = ({ events, duration, currentTime, onEventClick }) => {
  const getSourceColor = (source: string) => {
    switch (source) {
      case 'video': return '#1677ff'
      case 'audio': return '#52c41a'
      case 'sensor': return '#fa8c16'
      case 'fusion': return '#722ed1'
      default: return '#8c8c8c'
    }
  }

  const getSourceLabel = (source: string) => {
    switch (source) {
      case 'video': return '视频'
      case 'audio': return '音频'
      case 'sensor': return '传感器'
      case 'fusion': return '多模态融合'
      default: return '未知'
    }
  }

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <div className="mt-6">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-lg font-medium">事件时间轴</h3>
        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#1677ff]"></span>视频</div>
          <div className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#52c41a]"></span>音频</div>
          <div className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#fa8c16]"></span>传感器</div>
          <div className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#722ed1]"></span>融合</div>
        </div>
      </div>
      
      <div className="timeline-container" onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect()
        const x = e.clientX - rect.left
        const percent = x / rect.width
        onEventClick(percent * duration)
      }}>
        <div 
          className="timeline-progress" 
          style={{ width: `${progressPercent}%` }}
        />
        
        <div 
          className="timeline-playhead" 
          style={{ left: `${progressPercent}%` }}
        />
        
        {events.map((event) => {
          const leftPercent = duration > 0 ? (event.time_seconds / duration) * 100 : 0
          
          return (
            <Tooltip 
              key={event.id}
              title={
                <div>
                  <div className="font-bold">{event.event_type}</div>
                  <div>时间: {event.time_seconds}s</div>
                  <div>来源: {getSourceLabel(event.source)}</div>
                  {event.actor && <div>执行者: {event.actor}</div>}
                  {typeof event.event_data?.speaker_role === 'string' && (
                    <div>角色: {event.event_data.speaker_role}</div>
                  )}
                  {typeof event.event_data?.text === 'string' && event.event_data.text && (
                    <div className="max-w-[320px] break-words">文本: {event.event_data.text}</div>
                  )}
                  <div>置信度: {(event.confidence * 100).toFixed(1)}%</div>
                </div>
              }
            >
              <div 
                className="timeline-marker"
                style={{ 
                  left: `${leftPercent}%`,
                  backgroundColor: getSourceColor(event.source)
                }}
                onClick={(e) => {
                  e.stopPropagation()
                  onEventClick(event.time_seconds)
                }}
              />
            </Tooltip>
          )
        })}
      </div>
    </div>
  )
}

export default Timeline
