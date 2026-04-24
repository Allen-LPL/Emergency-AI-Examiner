import React from 'react'
import { Radar } from '@ant-design/charts'

interface RadarChartProps {
  phaseScores: Record<string, { score: number; max_score: number }>
}

const RadarChart: React.FC<RadarChartProps> = ({ phaseScores }) => {
  const phaseNames: Record<string, string> = {
    phase1_before_arrival: '到达前准备',
    phase2_arrival_step1: '到达现场(一)',
    phase3_arrival_step2: '到达现场(二)',
    phase4_arrival_step3: '到达现场(三)',
    phase5_arrival_step4: '到达现场(四)',
    phase6_arrival_step5: '到达现场(五)',
  }

  const data = Object.entries(phaseScores).map(([key, value]) => {
    const percent = value.max_score > 0 ? (value.score / value.max_score) * 100 : 0
    return {
      name: phaseNames[key] || key,
      score: percent,
    }
  })

  const config = {
    data,
    xField: 'name',
    yField: 'score',
    meta: {
      score: {
        alias: '得分率(%)',
        min: 0,
        max: 100,
      },
    },
    xAxis: {
      line: null,
      tickLine: null,
      grid: {
        line: {
          style: {
            lineDash: null,
          },
        },
      },
    },
    yAxis: {
      line: null,
      tickLine: null,
      grid: {
        line: {
          type: 'line',
          style: {
            lineDash: null,
          },
        },
      },
    },
    point: {
      size: 4,
    },
    area: {
      style: {
        fillOpacity: 0.2,
      },
    },
  }

  return (
    <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
      <h3 className="text-lg font-medium text-gray-800 mb-6 text-center">各阶段得分率分析</h3>
      <div className="h-[400px]">
        <Radar {...config} />
      </div>
    </div>
  )
}

export default RadarChart
