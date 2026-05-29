import React from 'react'
import { Radar } from '@ant-design/charts'

interface RadarChartProps {
  phaseScores: Record<string, { score: number; max_score: number }>
}

// 阶段编码 → 显示名称
const PHASE_NAMES: Record<string, string> = {
  phase1_before_arrival: '到达现场前',
  phase2_arrival_step1: '到达现场(一)',
  phase3_arrival_step2: '到达现场(二)',
  phase4_arrival_step3: '到达现场(三)',
  phase5_arrival_step4: '到达现场(四)',
  phase6_arrival_step5: '到达现场(五)',
  objective_compression: '按压质量',
  objective_ventilation: '有效通气',
  objective_ccf: 'CCF按压分数',
}

const RadarChart: React.FC<RadarChartProps> = ({ phaseScores }) => {
  // 数据字段直接用中文，确保 tooltip / 坐标轴显示中文
  const data = Object.entries(phaseScores).map(([key, value]) => {
    const percent = value.max_score > 0 ? (value.score / value.max_score) * 100 : 0
    return {
      阶段: PHASE_NAMES[key] || key,
      得分率: Number(percent.toFixed(1)),
    }
  })

  const config = {
    data,
    xField: '阶段',
    yField: '得分率',
    meta: {
      得分率: {
        min: 0,
        max: 100,
        formatter: (v: number) => `${v}%`,
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
    tooltip: {
      formatter: (datum: { 阶段: string; 得分率: number }) => ({
        name: datum.阶段,
        value: `${datum.得分率}%`,
      }),
    },
  }

  return (
    <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
      <h3 className="text-lg font-medium text-gray-800 mb-6 text-center">各阶段得分率分析</h3>
      <div className="h-100">
        <Radar {...config} />
      </div>
    </div>
  )
}

export default RadarChart
