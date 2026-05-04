import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Spin, Result, Card, Progress, Tag, Table, Collapse, Statistic } from 'antd'
import { ArrowLeftOutlined, FileTextOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { getExamStatus, getExamTimeline, getExamScores, getSensorData, generateMockSensor } from '../api'
import type { ExamStatus, ExamEvent, ScoreResult, SensorData } from '../types'
import { usePolling } from '../hooks/usePolling'
import VideoPlayer from '../components/VideoPlayer'
import Timeline from '../components/Timeline'
import PipelineProgress from '../components/PipelineProgress'
import RadarChart from '../components/RadarChart'

const { Panel } = Collapse;

const phaseNameMapping: Record<string, string> = {
  phase1_before_arrival: "到达现场前 (5分)",
  phase2_arrival_step1: "到达现场(一) (5分)",
  phase3_arrival_step2: "到达现场(二) (10分)",
  phase4_arrival_step3: "到达现场(三) (30分)",
  phase5_arrival_step4: "到达现场(四) (5分)",
  phase6_arrival_step5: "到达现场(五) (5分)",
  objective_compression: "客观-按压质量 (10分)",
  objective_ventilation: "客观-通气质量 (10分)",
  objective_ccf: "客观-CCF (20分)"
}

const ExamDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const examId = parseInt(id || '0', 10)
  
  const [status, setStatus] = useState<ExamStatus | null>(null)
  const [events, setEvents] = useState<ExamEvent[]>([])
  const [scoreResult, setScoreResult] = useState<ScoreResult | null>(null)
  const [sensorData, setSensorData] = useState<SensorData | null>(null)
  const [loading, setLoading] = useState(true)
  const [currentTime, setCurrentTime] = useState(0)
  const [videoDuration, setVideoDuration] = useState(0)
  const [generatingSensor, setGeneratingSensor] = useState(false)

  const fetchStatus = async () => {
    if (!examId) return
    try {
      const data = await getExamStatus(examId)
      setStatus(data)
      
      if (data.status === 'completed') {
        const [timelineData, scores, sensor] = await Promise.all([
          getExamTimeline(examId),
          getExamScores(examId),
          getSensorData(examId)
        ])
        
        setEvents(timelineData)
        setScoreResult(scores)
        setSensorData(sensor)
        
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

  const handleGenerateMockSensor = async () => {
    setGeneratingSensor(true)
    try {
      const data = await generateMockSensor(examId)
      setSensorData(data)
    } catch (error) {
      console.error('Failed to generate mock sensor data:', error)
    } finally {
      setGeneratingSensor(false)
    }
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

  const renderScoreOverview = () => {
    if (!scoreResult) return null;
    
    const scoreColor = scoreResult.total_score < 40 ? 'text-red-500' : scoreResult.total_score < 70 ? 'text-orange-500' : 'text-green-500';
    const audioEventsCount = events.filter(e => e.source === 'audio').length;
    
    return (
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100 flex justify-between items-center">
        <div>
          <div className="text-gray-500 text-sm mb-1">总分</div>
          <div className={`text-4xl font-bold ${scoreColor}`}>
            {scoreResult.total_score.toFixed(1)} <span className="text-xl text-gray-400">/ {scoreResult.max_total}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-gray-500 text-sm mb-1">考核概况</div>
          <div className="text-lg font-medium text-gray-700">
            {Object.keys(scoreResult.phase_scores).length}个评分阶段 | {events.length}个事件 | {audioEventsCount}段语音
          </div>
        </div>
      </div>
    )
  }

  const renderPhaseCards = () => {
    if (!scoreResult) return null;

    const phases = Object.keys(scoreResult.phase_scores);
    
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {phases.map(phase => {
          const phaseScore = scoreResult.phase_scores[phase];
          const items = scoreResult.items.filter(item => item.phase === phase);
          const percent = phaseScore.max_score > 0 ? (phaseScore.score / phaseScore.max_score) * 100 : 0;
          
          return (
            <Card key={phase} title={phaseNameMapping[phase] || phase} className="shadow-sm h-full" bodyStyle={{ padding: '12px' }}>
              <div className="flex justify-between items-center mb-2">
                <span className="font-bold text-lg">{phaseScore.score}/{phaseScore.max_score}</span>
                <Progress percent={percent} showInfo={false} size="small" className="w-24" status={percent === 100 ? 'success' : percent > 60 ? 'normal' : 'exception'} />
              </div>
              <div className="space-y-2 mt-4 max-h-48 overflow-y-auto pr-1">
                {items.map((item, idx) => {
                  const isFullScore = item.actual_score === item.max_score;
                  return (
                    <div key={idx} className="text-sm border-b border-gray-50 pb-2 last:border-0">
                      <div className="flex items-start gap-2">
                        {isFullScore ? (
                          <CheckCircleOutlined className="text-green-500 mt-1" />
                        ) : (
                          <CloseCircleOutlined className="text-red-500 mt-1" />
                        )}
                        <div className="flex-1">
                          <div className="text-gray-700">{item.rule_name}</div>
                          {!isFullScore && item.deduction_reason && (
                            <div className="text-red-500 text-xs mt-1">{item.deduction_reason}</div>
                          )}
                        </div>
                        <div className="text-gray-500 whitespace-nowrap">{item.actual_score}/{item.max_score}</div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </Card>
          )
        })}
      </div>
    )
  }

  const renderSensorData = () => {
    return (
      <Card title="传感器数据 (客观评分)" className="shadow-sm h-full">
        {sensorData ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <Progress type="dashboard" percent={sensorData.compression_compliance_rate * 100} format={percent => `${percent?.toFixed(1)}%`} />
                <div className="mt-2 font-medium text-gray-700">按压达标率</div>
              </div>
              <div className="text-center">
                <Progress type="dashboard" percent={sensorData.ventilation_compliance_rate * 100} format={percent => `${percent?.toFixed(1)}%`} />
                <div className="mt-2 font-medium text-gray-700">通气达标率</div>
              </div>
              <div className="text-center">
                <Progress type="dashboard" percent={sensorData.ccf_percentage * 100} format={percent => `${percent?.toFixed(1)}%`} />
                <div className="mt-2 font-medium text-gray-700">CCF (胸外按压分数)</div>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50 p-4 rounded-lg">
              <Statistic title="平均按压深度" value={sensorData.avg_compression_depth || 0} suffix="mm" valueStyle={{ fontSize: '1.25rem' }} />
              <Statistic title="平均按压频率" value={sensorData.avg_compression_rate || 0} suffix="次/分" valueStyle={{ fontSize: '1.25rem' }} />
              <Statistic title="总按压次数" value={sensorData.total_compressions || 0} valueStyle={{ fontSize: '1.25rem' }} />
              <Statistic title="总通气次数" value={sensorData.total_ventilations || 0} valueStyle={{ fontSize: '1.25rem' }} />
            </div>
          </div>
        ) : (
          <div className="text-center py-8">
            <div className="text-gray-400 mb-4">暂无传感器数据</div>
            <Button type="primary" onClick={handleGenerateMockSensor} loading={generatingSensor}>
              生成模拟数据
            </Button>
          </div>
        )}
      </Card>
    )
  }

  const renderEventTables = () => {
    const videoEvents = events.filter(e => e.source === 'video');
    const audioEvents = events.filter(e => e.source === 'audio');

    const videoColumns = [
      { title: '时间', dataIndex: 'time_seconds', key: 'time', render: (t: number) => `${t}s`, width: 80 },
      { 
        title: '动作类型', 
        dataIndex: 'event_type', 
        key: 'type',
        render: (type: string) => <Tag color="blue">{type}</Tag>
      },
      { 
        title: '置信度', 
        dataIndex: 'confidence', 
        key: 'confidence',
        render: (c: number) => `${(c * 100).toFixed(1)}%`,
        width: 100
      }
    ];

    const audioColumns = [
      { title: '时间', dataIndex: 'time_seconds', key: 'time', render: (t: number) => `${t}s`, width: 80 },
      { 
        title: '规则/关键词', 
        key: 'rule',
        render: (_: unknown, record: ExamEvent) => {
          const ruleCode = record.event_data?.rule_code as string;
          return <Tag color="green">{ruleCode || record.event_type}</Tag>
        }
      },
      { 
        title: '识别文本', 
        key: 'text',
        render: (_: unknown, record: ExamEvent) => {
          const text = record.event_data?.text as string;
          return <span className="text-gray-600">{text || '-'}</span>
        }
      }
    ];

    const videoEventCounts = videoEvents.reduce((acc, event) => {
      acc[event.event_type] = (acc[event.event_type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title={`视频动作评估 (${videoEvents.length})`} className="shadow-sm" bodyStyle={{ padding: 0 }}>
          <div className="p-4 border-b border-gray-100 flex flex-wrap gap-2">
            {Object.entries(videoEventCounts).map(([type, count]) => (
              <Tag key={type} color="blue">{type}: {count}</Tag>
            ))}
          </div>
          <Table 
            dataSource={videoEvents} 
            columns={videoColumns} 
            rowKey="id"
            size="small"
            pagination={{ pageSize: 5 }}
            scroll={{ y: 240 }}
          />
        </Card>
        <Card title={`语音评估 (${audioEvents.length})`} className="shadow-sm" bodyStyle={{ padding: 0 }}>
          <Table 
            dataSource={audioEvents} 
            columns={audioColumns} 
            rowKey="id"
            size="small"
            pagination={{ pageSize: 5 }}
            scroll={{ y: 240 }}
          />
        </Card>
      </div>
    )
  }

  const renderDebugPanel = () => {
    const columns = [
      { title: '时间', dataIndex: 'time_seconds', key: 'time', render: (t: number) => `${t}s` },
      { title: '来源', dataIndex: 'source', key: 'source', 
        filters: [
          { text: 'Video', value: 'video' },
          { text: 'Audio', value: 'audio' },
          { text: 'Sensor', value: 'sensor' },
        ],
        onFilter: (value: unknown, record: ExamEvent) => record.source === value,
        render: (s: string) => <Tag color={s === 'video' ? 'blue' : s === 'audio' ? 'green' : 'orange'}>{s}</Tag>
      },
      { title: '类型', dataIndex: 'event_type', key: 'type' },
      { title: '置信度', dataIndex: 'confidence', key: 'confidence', render: (c: number) => c.toFixed(3) },
      { title: '数据', dataIndex: 'event_data', key: 'data', render: (d: Record<string, unknown> | null) => <pre className="text-xs m-0 max-w-xs overflow-x-auto">{JSON.stringify(d)}</pre> }
    ];

    return (
      <Collapse className="bg-white">
        <Panel header="调试数据视图 (Debug Data)" key="1">
          <div className="space-y-6">
            <div>
              <h4 className="font-medium mb-2">原始评分数据 (Raw Score Items)</h4>
              <div className="bg-gray-50 p-4 rounded overflow-x-auto">
                <pre className="text-xs m-0">{JSON.stringify(scoreResult?.items, null, 2)}</pre>
              </div>
            </div>
            <div>
              <h4 className="font-medium mb-2">原始事件数据 (Raw Events - Top 50)</h4>
              <Table 
                dataSource={events.slice(0, 50)} 
                columns={columns} 
                rowKey="id"
                size="small"
                pagination={false}
                scroll={{ y: 400 }}
              />
            </div>
          </div>
        </Panel>
      </Collapse>
    )
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
            stage={status.stage}
            substep={status.substep}
            detail={status.detail}
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
        <div className="space-y-6">
          {renderScoreOverview()}

          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-800 m-0">评分阶段明细</h3>
            {renderPhaseCards()}
          </div>

          {scoreResult && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <RadarChart phaseScores={scoreResult.phase_scores} />
              {renderSensorData()}
            </div>
          )}

          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-800 m-0">事件时间轴与评估明细</h3>
            <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
              <VideoPlayer 
                src={`/api/v1/exam/${examId}/video`} 
                currentTime={currentTime}
                onTimeUpdate={handleTimeUpdate}
              />
              <div className="mt-4">
                <Timeline 
                  events={events} 
                  duration={videoDuration} 
                  currentTime={currentTime}
                  onEventClick={handleEventClick}
                />
              </div>
            </div>
            {renderEventTables()}
          </div>

          {renderDebugPanel()}
        </div>
      )}
    </div>
  )
}

export default ExamDetail
