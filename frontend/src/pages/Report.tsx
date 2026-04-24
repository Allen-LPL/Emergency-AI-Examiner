import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Spin, Result, Collapse, Table, Tag } from 'antd'
import { ArrowLeftOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { getExamResult } from '../api'
import type { ScoreResult } from '../types'
import ScoreCard from '../components/ScoreCard'
import RadarChart from '../components/RadarChart'

const { Panel } = Collapse

const Report: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const examId = parseInt(id || '0', 10)
  
  const [result, setResult] = useState<ScoreResult | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchResult = async () => {
      if (!examId) return
      try {
        const data = await getExamResult(examId)
        setResult(data)
      } catch (error) {
        console.error('Failed to fetch exam result:', error)
      } finally {
        setLoading(false)
      }
    }
    
    fetchResult()
  }, [examId])

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spin size="large" tip="生成报告中..." />
      </div>
    )
  }

  if (!result) {
    return <Result status="404" title="未找到考核报告" />
  }

  const phaseNames: Record<string, string> = {
    phase1_before_arrival: '到达前准备',
    phase2_arrival_step1: '到达现场(一)',
    phase3_arrival_step2: '到达现场(二)',
    phase4_arrival_step3: '到达现场(三)',
    phase5_arrival_step4: '到达现场(四)',
    phase6_arrival_step5: '到达现场(五)',
  }

  const columns = [
    {
      title: '评分项',
      dataIndex: 'rule_name',
      key: 'rule_name',
      width: '40%',
    },
    {
      title: '得分',
      key: 'score',
      width: '15%',
      render: (_: any, record: any) => {
        const isFull = record.actual_score === record.max_score
        const isZero = record.actual_score === 0
        return (
          <Tag color={isFull ? 'success' : isZero ? 'error' : 'warning'}>
            {record.actual_score} / {record.max_score}
          </Tag>
        )
      },
    },
    {
      title: '扣分原因',
      dataIndex: 'deduction_reason',
      key: 'deduction_reason',
      render: (text: string | null) => text ? <span className="text-red-500">{text}</span> : <span className="text-gray-400">-</span>,
    },
  ]

  const groupedItems = result.items.reduce((acc, item) => {
    if (!acc[item.phase]) {
      acc[item.phase] = []
    }
    acc[item.phase].push(item)
    return acc
  }, {} as Record<string, typeof result.items>)

  const deductions = result.items.filter(item => item.actual_score < item.max_score)

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/exam/${examId}`)}>返回视频</Button>
          <h2 className="text-2xl font-bold m-0">考核分析报告</h2>
        </div>
        <Button type="primary" icon={<VideoCameraOutlined />} onClick={() => navigate('/')}>
          返回首页
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <ScoreCard totalScore={result.total_score} maxScore={result.max_total} />
        </div>
        <div className="md:col-span-2">
          <RadarChart phaseScores={result.phase_scores} />
        </div>
      </div>

      {deductions.length > 0 && (
        <div className="bg-red-50 p-6 rounded-lg border border-red-100">
          <h3 className="text-lg font-bold text-red-800 mb-4">主要扣分项汇总</h3>
          <ul className="list-disc pl-5 space-y-2">
            {deductions.map((item, idx) => (
              <li key={idx} className="text-red-700">
                <span className="font-medium">[{phaseNames[item.phase] || item.phase}]</span> {item.rule_name}: 
                扣除 {item.max_score - item.actual_score} 分 - {item.deduction_reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="text-xl font-bold text-gray-800 mb-4">详细评分明细</h3>
        <Collapse defaultActiveKey={Object.keys(groupedItems)}>
          {Object.entries(groupedItems).map(([phase, items]) => {
            const phaseScore = result.phase_scores[phase]
            const header = (
              <div className="flex justify-between w-full pr-4">
                <span className="font-bold">{phaseNames[phase] || phase}</span>
                <span>
                  得分: <span className={phaseScore.score === phaseScore.max_score ? 'text-green-600' : 'text-red-600'}>
                    {phaseScore.score}
                  </span> / {phaseScore.max_score}
                </span>
              </div>
            )
            
            return (
              <Panel header={header} key={phase}>
                <Table 
                  columns={columns} 
                  dataSource={items} 
                  rowKey="rule_code" 
                  pagination={false}
                  size="small"
                />
              </Panel>
            )
          })}
        </Collapse>
      </div>
    </div>
  )
}

export default Report
